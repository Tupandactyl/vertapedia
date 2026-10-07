"""편집진 구글 시트 두 개를 xlsx 로 내려받는다(링크 공유 상태여야 한다)."""
import sys
import urllib.request
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"

SHEETS = {
    "birds.xlsx": "1TPAgkLflsX0GjkcQdcRhrYSnJ7bvscmVESK5wyIVfxA",
    "reptiles.xlsx": "1YC9IBMxBf1wBsbiXj7umJ6k0HD1eY3GsKCGGTxDlPD4",
}

for name, sid in SHEETS.items():
    url = f"https://docs.google.com/spreadsheets/d/{sid}/export?format=xlsx"
    with urllib.request.urlopen(url, timeout=120) as r:
        body = r.read()
    if not body.startswith(b"PK"):
        sys.exit(f"{name}: xlsx 가 아닌 응답을 받았다. 시트 공유 설정(링크가 있는 모든 사용자 보기)을 확인할 것.")
    (DATA / name).write_bytes(body)
    print(name, len(body) // 1024, "KB")
