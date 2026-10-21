"""GitHub Releases updater. Only packaged Windows builds check for updates."""
import base64
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

VERSION = '1.0.2'
REPOSITORY = 'pdkstorywork/PixcelCafe'
ASSET_NAME = 'PixelCafe.exe'
MAX_DOWNLOAD = 512 * 1024 * 1024


def _version(value):
    match = re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)', value)
    if not match:
        raise ValueError('Use a stable version such as v1.0.1')
    return tuple(map(int, match.groups()))


def _message(text, question=False):
    # MB_SETFOREGROUND | MB_TOPMOST, plus yes/no or information icon.
    return ctypes.windll.user32.MessageBoxW(
        None, text, 'PixelCafe 업데이트', 0x50000 | (0x24 if question else 0x40))


def _latest():
    request = urllib.request.Request(
        f'https://api.github.com/repos/{REPOSITORY}/releases/latest',
        headers={'Accept': 'application/vnd.github+json',
                 'User-Agent': f'PixelCafe/{VERSION}'})
    with urllib.request.urlopen(request, timeout=3) as response:
        release = json.loads(response.read(1024 * 1024))
    if release.get('draft') or release.get('prerelease'):
        return None
    if _version(release['tag_name']) <= _version(VERSION):
        return None
    prefix = f'https://github.com/{REPOSITORY}/releases/download/'
    for asset in release.get('assets', []):
        digest = asset.get('digest') or ''
        size = asset.get('size', 0)
        if (asset.get('name') == ASSET_NAME
                and asset.get('state') == 'uploaded'
                and asset.get('browser_download_url', '').startswith(prefix)
                and re.fullmatch(r'sha256:[0-9a-fA-F]{64}', digest)
                and isinstance(size, int) and 0 < size <= MAX_DOWNLOAD):
            return release['tag_name'], asset
    return None


def _download(asset, destination):
    checksum = hashlib.sha256()
    size = 0
    deadline = time.monotonic() + 180
    request = urllib.request.Request(asset['browser_download_url'],
                                     headers={'User-Agent': f'PixelCafe/{VERSION}'})
    with urllib.request.urlopen(request, timeout=15) as response:
        with open(destination, 'wb') as output:
            while chunk := response.read(256 * 1024):
                size += len(chunk)
                if size > asset['size'] or size > MAX_DOWNLOAD or time.monotonic() > deadline:
                    raise ValueError('Download exceeded its size or time limit')
                checksum.update(chunk)
                output.write(chunk)
    if size != asset['size'] or checksum.hexdigest() != asset['digest'][7:].lower():
        raise ValueError('Download checksum mismatch')
    with open(destination, 'rb') as stream:
        if stream.read(2) != b'MZ':
            raise ValueError('Download is not a Windows executable')


def _replacement_script(target, staged, parent_pid, digest):
    def quote(value):
        return "'" + str(value).replace("'", "''") + "'"

    # The helper runs outside the PyInstaller process and waits for its file lock.
    # Backups live next to the EXE so renames stay on the same volume.
    return r'''
$ErrorActionPreference = 'Stop'
$target = TARGET
$staged = STAGED
$backup = $target + '.' + [guid]::NewGuid().ToString('N') + '.bak'
$moved = $false
$completed = $false
try {
    $parent = Get-Process -Id PARENT_PID -ErrorAction SilentlyContinue
    if ($parent -and -not $parent.WaitForExit(60000)) { throw 'Game did not exit' }
    $sha = [Security.Cryptography.SHA256]::Create()
    $stream = [IO.File]::OpenRead($staged)
    try { $actual = [BitConverter]::ToString($sha.ComputeHash($stream)).Replace('-', '').ToLowerInvariant() }
    finally { $stream.Dispose(); $sha.Dispose() }
    if ($actual -ne DIGEST) {
        throw 'Checksum mismatch'
    }
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        try {
            [IO.File]::Move($target, $backup)
            $moved = $true
            break
        } catch { Start-Sleep -Milliseconds 500 }
    }
    if (-not $moved) { throw 'Cannot replace game; close other game windows and try again' }
    [IO.File]::Copy($staged, $target, $false)
    $env:PIXELCAFE_SKIP_UPDATE = '1'
    $env:PYINSTALLER_RESET_ENVIRONMENT = '1'
    Start-Process -FilePath $target -WorkingDirectory ([IO.Path]::GetDirectoryName($target))
    $completed = $true
} catch {
    $failure = $_.Exception.Message
    if ($moved) {
        try {
            if ([IO.File]::Exists($target)) { [IO.File]::Delete($target) }
            [IO.File]::Move($backup, $target)
            $moved = $false
        } catch { $failure += "`nBackup: $backup" }
    }
    Add-Type -AssemblyName System.Windows.Forms
    [void][System.Windows.Forms.MessageBox]::Show(
        "업데이트를 완료하지 못했습니다. 기존 게임을 다시 실행해 주세요.`n$failure", 'PixelCafe 업데이트')
    exit 1
} finally {
    if ($completed -and [IO.File]::Exists($backup)) {
        try { [IO.File]::Delete($backup) } catch {}
    }
    try { [IO.File]::Delete($staged); [IO.Directory]::Delete([IO.Path]::GetDirectoryName($staged)) } catch {}
}
'''.replace('TARGET', quote(target)).replace('STAGED', quote(staged)).replace(
        'PARENT_PID', str(int(parent_pid))).replace('DIGEST', quote(digest.lower()))


def _launch_helper(target, staged, digest):
    script = _replacement_script(target, staged, os.getpid(), digest)
    encoded = base64.b64encode(script.encode('utf-16le')).decode('ascii')
    powershell = Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    # Do not pass PyInstaller's bundled DLL search directory to system PowerShell.
    ctypes.windll.kernel32.SetDllDirectoryW(None)
    try:
        subprocess.Popen(
            [str(powershell), '-NoProfile', '-NonInteractive', '-WindowStyle', 'Hidden',
             '-EncodedCommand', encoded],
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            close_fds=True, cwd=str(target.parent))
    finally:
        if getattr(sys, '_MEIPASS', None):
            ctypes.windll.kernel32.SetDllDirectoryW(sys._MEIPASS)


def check_for_updates():
    if os.environ.pop('PIXELCAFE_SKIP_UPDATE', None) == '1':
        return
    if sys.platform != 'win32' or not getattr(sys, 'frozen', False):
        return
    # Offline, private repository, no Releases, invalid metadata or rate limit:
    # continue to the game without a blocking error dialog.
    try:
        latest = _latest()
    except Exception:
        return
    if latest is None:
        return
    version, asset = latest
    if _message(f'새 버전 {version.lstrip("v")}이 있습니다.\n현재 버전: {VERSION}\n\n'
                '업데이트를 다운로드하고 게임을 다시 실행할까요?\n'
                '저장 데이터는 유지됩니다.\n\n'
                '다운로드 중에는 잠시 기다려 주세요.', question=True) != 6:
        return
    folder = None
    try:
        folder = Path(tempfile.mkdtemp(prefix='PixelCafe-update-'))
        staged = folder / ASSET_NAME
        _download(asset, staged)
        _launch_helper(Path(sys.executable).resolve(), staged, asset['digest'][7:])
    except Exception:
        if folder is not None:
            shutil.rmtree(folder, ignore_errors=True)
        _message('업데이트를 다운로드하거나 준비하지 못했습니다.\n'
                 '현재 버전으로 실행합니다. 다음 실행 시 다시 시도할 수 있습니다.')
        return
    raise SystemExit(0)
