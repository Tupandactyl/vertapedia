# Vertapedia

조류·파충류의 학명과 한국어 국명을 한곳에서 찾는 사전. 편집진이 구글 시트에 적은 국명 합의본·제안·명칭 근거를 공식 목록과 합쳐 보여 준다.

사이트: https://tupandactyl.github.io/vertapedia/ · 국명 검토: https://tupandactyl.github.io/vertapedia/review.html

## 이름을 정하는 순서

| | 학명 | 국명 |
|---|---|---|
| 조류 | 조류 시트(eBird/Clements·AviList) | 한국조류목록 2025 → 국가생물종목록 2019 → 시트 합의본 → 개인 제안(모두 같을 때) |
| 파충류 | 파충류 시트(The Reptile Database) | 국가생물종목록 2019 → 시트 합의본 |

- 국명이 없으면 영명을 표시한다.
- 개인 제안 국명이 다른 종과 겹치면 쓰지 않는다.
- 종이 나뉘어 공식 목록과 시트의 학명이 다르면, 공식 국명을 시트가 한국 개체군으로 본 학명에 붙인다.
- 자동으로 풀리지 않는 대응은 `data/overrides.json`에 손으로 적는다.

## 자료

| 파일 | 내용 |
|---|---|
| `data/nibr.json` | 국가생물종목록 Ⅱ(2019) PDF에서 뽑은 파충강·조강 학명과 국명 |
| `data/kos2025.xlsx` | 한국조류학회 한국조류목록 개정판 v2.1(2025) |
| `data/overrides.json` | 편집자가 직접 정한 학명 대응 |
| `data/references.json` | 참고문헌 |

편집진 시트 두 개는 저장소에 두지 않고, 배포할 때마다 내려받는다. 시트는 "링크가 있는 모든 사용자 보기"로 공유되어 있어야 한다.

## 자동 갱신

GitHub Actions(`.github/workflows/build.yml`)가 6시간마다 시트를 받아 국명을 다시 합치고 GitHub Pages에 배포한다. 바로 반영하려면 저장소의 Actions 탭 → "시트 반영과 배포" → Run workflow.

## 손으로 돌리기

```
pip install -r requirements.txt
python scripts/fetch_sheets.py
python scripts/import_names.py            # 국가생물종목록 PDF 경로를 주면 nibr.json 도 다시 만든다
python scripts/build_site.py
python scripts/build_review.py
python -m http.server 8123 --directory site
```

`design/species-mockup.html`은 종 페이지 디자인 시안이다.
