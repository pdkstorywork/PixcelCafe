# PixelCafe 빌드 지침

- 재빌드 시 EXE는 `dist/`가 아니라 **프로젝트 루트(`C:\PixcelCafe\PixelCafe.exe`)**에 저장한다.
- 빌드 명령:

  ```
  py -3.13 -m PyInstaller --noconfirm --clean --distpath . PixelCafe.spec
  ```

- 빌드 후 `dist/` 폴더는 만들지 않는다. 이미 생겼다면 삭제한다. `build/`는 중간 산출물이므로 커밋하지 않는다.
- `PixelCafe.spec`의 아이콘 원본이 루트의 `PixelCafe.exe`라 빌드하면 같은 파일을 덮어쓴다. 의도된 동작이다.
- 릴리스에는 루트의 `PixelCafe.exe`를 그대로 첨부한다.
