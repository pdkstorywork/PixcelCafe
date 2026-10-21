# 손님 에셋 위치표

손님 그림은 두 곳에 나뉘어 있다. 새 손님은 아래 규칙대로 추가한다.

| 구분 | 위치 | 크기 | 비고 |
|---|---|---|---|
| 일반 손님 (동물: cat/dog/rabbit/bear/hamster/mouse/fox) | `assets/pixelcafe-atlas*.png` (`animal/*`) | 아틀라스 | 1x/2x/3x 각각 원화 |
| 기본 희귀 손님 (chiikawa, usagi, hachiware, kitty, melody, kuromi, cinna, purin, ganadi, loopy, ryan, apeach, pororo, pikachu, chunsik) | `assets/pixelcafe-atlas*.png` (`rare/*`) | 아틀라스 | 전설 3종 = hachiware, chiikawa, usagi |
| 가족 손님 외형 1~9 | `assets/pixelcafe-atlas*.png` (`family/variant01~09`) | 아틀라스 | |
| 추가 희귀 손님 (totoro, stitch, pooh, rilakkuma, snoopy, kaonashi, kumamon, gudetama) | `assets/guests/<id>.png` | 22x26 | 큰 이미지는 축소됨 |
| 가족 손님 계절·기념일 오버레이 | `assets/guests/family_<계절·기념일>.png` | 24x34 투명 | 계절·기념일: spring summer autumn winter newyear valentine halloween christmas |
| 외형별 오버레이 (선택) | `assets/guests/family_<1-9>_<계절·기념일>.png` | 24x34 투명 | 있으면 위 파일보다 우선 |
| 이름 있는 가족 손님 (도야니, 셔니) | `assets/guests/named_<이름>.png` | 24x34 | `collection.py`의 `NAMED_FAMILY`에 등록 |

## 새 손님 추가 규칙
- 추가 희귀 손님: `<id>.png`를 이 폴더에 넣고, `collection.py`의 `NEW_RARE`(이름), `PLACEHOLDER`(임시 색), `GUEST_HINT`(힌트 문구)에 id를 추가한다.
- 이름 있는 가족 손님: `named_<이름>.png`를 넣고 `NAMED_FAMILY`에 `'이름': (외형번호, 'named_이름.png')`을 추가한다.
- 아틀라스 손님은 아틀라스와 `manifest.json`을 다시 만들어야 하므로, 신규는 가급적 이 폴더에 개별 PNG로 추가한다.
- 파일이 없으면 코드가 그린 임시 그림이 나오지만, 이름 있는 가족 손님은 파일이 없으면 오류가 난다.
