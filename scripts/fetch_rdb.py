"""Reptile Database 최신 종 목록(checklist)을 받아 data/rdb_checklist.xlsx 로 둔다.

Reptile Database는 1년에 두세 번 목록을 낸다. 새 판이 나오면 이것을 돌리고
scripts/import_names.py 의 RDB_LABEL 을 그 판으로 고친다.

    python scripts/fetch_rdb.py
"""
import re
import urllib.request
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
BASE = "http://www.reptile-database.org/data/"
UA = {"User-Agent": "Vertapedia/0.1 (https://github.com/Tupandactyl/vertapedia)"}


def main():
    html = urllib.request.urlopen(urllib.request.Request(BASE, headers=UA), timeout=60).read().decode("utf-8", "replace")
    files = set(re.findall(r"reptile_checklist_(\d{4})_(\d{2})(v\d+)?\.xlsx", html, re.I))
    y, m, v = max(files, key=lambda f: (f[0], f[1], f[2]))
    name = f"reptile_checklist_{y}_{m}{v}.xlsx"
    data = urllib.request.urlopen(urllib.request.Request(BASE + name, headers=UA), timeout=300).read()
    (DATA / "rdb_checklist.xlsx").write_bytes(data)
    print(f"{name} ({len(data) // 1024} KB) → data/rdb_checklist.xlsx · 판 표기: Reptile Database {y}-{m}")


if __name__ == "__main__":
    main()
