# -*- mode: python ; coding: utf-8 -*-
# Rebuild the editable launcher/rules with the recovered Python 3.13 runtime.
a = Analysis(
    ['PixelCafe.py'],
    pathex=[],
    binaries=[],
    datas=[('PixelCafe.pyc', '.'),
           ('assets/PixelCafe.ico', 'assets'),
           ('assets/decor-icons.png', 'assets'),
           ('assets/decor-icons.json', 'assets'),
           ('assets/manifest.json', 'assets'),
           ('assets/window-seasons.png', 'assets'),
           ('assets/pixelcafe-atlas.png', 'assets'),
           ('assets/pixelcafe-atlas-2x.png', 'assets'),
           ('assets/pixelcafe-atlas-3x.png', 'assets'),
           ('assets/guests', 'assets/guests')] + [
               (f'assets/themes/{t}/native', f'assets/themes/{t}/native')
               for t in ('spring', 'summer', 'autumn', 'winter', 'golden')],
    hiddenimports=['pygame', 'small', 'mini', 'art_runtime', 'chars', 'detail_render', 'props',
                   'specials', 'window_scenery', 'themes', 'ctypes', 'ctypes.wintypes',
                   'atexit', 'copy', 'random', 'math', 'time', 'json'],
    hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[],
    noarchive=False, optimize=0,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name='PixelCafe',
          debug=False, bootloader_ignore_signals=False, strip=False,
          upx=True, upx_exclude=[], runtime_tmpdir=None, console=False,
          disable_windowed_traceback=False, argv_emulation=False,
          target_arch=None, codesign_identity=None, entitlements_file=None,
          icon=['assets/PixelCafe.ico'])
