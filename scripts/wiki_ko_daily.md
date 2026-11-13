# 종 위키 번역: 한 회차 절차

국명이 있는 종의 영문 위키백과 문서를 번역한다. 합의 국명 종을 먼저, 그다음 사이트에 실린 제안 국명 종(시트 순서). 순서는 `wiki_ko.py`가 정한다. 다른 작업의 사용량을 잡아먹지 않는 것이 최우선이다.

## 1. 시작 전 사용량 확인
다음 중 하나면 이번 회차를 건너뛴다.
- 5시간 한도 사용량 40% 이상
- 주간 한도 사용량이 허용치 이상. 허용치 = 25 + 8 × (이번 주 경과 일수), 최대 75
- `translation_review/LOCK` 파일이 있고 3시간이 안 됐다(다른 세션이 번역 중). 3시간이 넘은 LOCK은 지우고 진행한다.

주말 가속(2026-11-13 금 ~ 11-15 일, 한국 시간, 사용자 요청): 5시간 기준 60%(새 에이전트는 70%), 주간 허용치 = 30 + 10 × 경과 일수, 최대 60. 이 기간에는 `next --chars 600000`으로 준비하고 예약은 1시간마다 돈다. 11-16 월요일부터는 위 기본값으로 돌아간다.

이 기준은 사람의 다른 작업이 쓴 양까지 포함하므로, 다른 작업이 많은 날은 번역이 저절로 줄어든다.

## 2. 준비
- 시작할 때 `translation_review/LOCK`에 현재 시각을 쓰고, 4단계가 끝나면 지운다.
- `python scripts/wiki_ko.py status`: 남은 양. 0종이면 끝낸다.
- `git pull --rebase --autostash`, `python scripts/fetch_sheets.py`, `python scripts/import_names.py`
- `python scripts/wiki_ko.py next --chars 300000`: 묶음은 `translation_review/batches.json`. 글자 수의 30%는 파충류, 나머지는 조류(각각 시트 순서). 한쪽이 끝나면 다른 쪽이 전부 쓴다.

## 3. 번역
- 묶음마다 서브에이전트(model: sonnet)를 하나씩, 동시에 최대 4개. 지침은 `scripts/wiki_ko_brief.md`.
- 새 에이전트를 띄우기 전마다 사용량을 다시 보고, 5시간 55% 이상이거나 주간 허용치를 넘으면 더 띄우지 않는다.

## 4. 합치기와 배포
- `python scripts/wiki_ko.py check`: 오류 난 문서는 다음 회차의 `next`가 빠진 문단만 다시 준비한다.
- `data/wiki_ko`만 커밋하고 `git pull --rebase --autostash` 후 push하면 사이트가 배포된다.

시범 측정(2026-11-06): 6.2만 자에 약 12만 토큰, 약 5분, 5시간 한도의 약 1%.
