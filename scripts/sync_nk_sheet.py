"""시트에 북한명 반영 (data/nk_names.json → 구글 시트)

출처: 국립생물자원관(2012) 국가 생물종 목록집(북한지역 척추동물).
- 종 탭(조류 '… v2026', 파충류 과 탭)과 파충류 '통합목록'의 '환경부 지정명' 바로 왼쪽에 '북한명' 열을 만들고 열 그룹으로 접는다.
  법정 목록 대조용인 '지정관리종목록'은 건드리지 않는다.
- 학명은 시트 학명에 맞췄다(nk_names.json 의 list_sci 가 원문, why 가 바꾼 까닭). 종이 나뉜 것은 한국 개체군의 종에 넣는다.

    python scripts/sync_nk_sheet.py           # 미리보기
    python scripts/sync_nk_sheet.py --apply   # 시트에 쓴다(먼저 .secrets/backup 에 xlsx 백업)
"""
import json
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

from sheets_api import Sheet

ROOT = Path(__file__).resolve().parent.parent
HEAD, NEXT = "북한명", "환경부 지정명"
NK = json.loads((ROOT / "data" / "nk_names.json").read_text(encoding="utf-8"))


def letter(c):
    s = ""
    c += 1
    while c:
        c, r = divmod(c - 1, 26)
        s = chr(65 + r) + s
    return s


def run(which, group, apply):
    want = {x["sci"]: x["ko"] for x in NK["species"] if x["group"] == group}
    alt = {x["sheet_sci"]: x["sci"] for x in NK["species"] if x.get("sheet_sci")}  # 시트 행의 학명이 사이트 학명과 다른 종
    sh = Sheet(which)
    tabs = [s["properties"] for s in sh.meta()["sheets"] if s["properties"]["title"] != "지정관리종목록"]
    val = sh.values_many([p["title"] for p in tabs])
    cols, cells, found = [], [], {}
    for p in tabs:
        rows = val[p["title"]]
        h = rows[0] if rows else []
        if NEXT not in h:
            continue
        has = HEAD in h
        c = h.index(HEAD) if has else h.index(NEXT)
        sci_c = next(h.index(k) for k in ("SCIENTIFIC NAME", "학명") if k in h)
        cols.append((p, c, has))
        for i, r in enumerate(rows[1:], start=2):
            s = (r[sci_c] if len(r) > sci_c else "").strip()
            s = alt.get(s, s)
            if s in want:
                cells.append((p["title"], c, i, want[s]))
                if p["title"] != "통합목록":
                    found.setdefault(s, []).append(p["title"])
    print(which, "탭", len(cols), "(열이 이미 있음", sum(x[2] for x in cols), ") · 칸", len(cells), "· 종", len(found), "/", len(want))
    print("  못 찾음:", [s for s in want if s not in found], "· 두 번 이상:", {s: t for s, t in found.items() if len(t) > 1})
    if not apply:
        return
    with urllib.request.urlopen(f"https://docs.google.com/spreadsheets/d/{sh.id}/export?format=xlsx", timeout=180) as r:
        body = r.read()
    if not body.startswith(b"PK"):
        sys.exit("백업 실패: xlsx 가 아닌 응답")
    bk = ROOT / ".secrets" / "backup" / f"{which}_before_nk_{datetime.now():%Y%m%d_%H%M}.xlsx"
    bk.write_bytes(body)
    print("  백업:", bk.name, len(body) // 1024, "KB")

    def rng(p, c):
        return dict(sheetId=p["sheetId"], dimension="COLUMNS", startIndex=c, endIndex=c + 1)

    new = [(p, c) for p, c, has in cols if not has]
    if new:  # 서식은 오른쪽(환경부 지정명) 열을 따른다
        sh.batch([{"insertDimension": {"range": rng(p, c), "inheritFromBefore": False}} for p, c in new])
    data = [dict(range=f"'{p['title']}'!{letter(c)}1", values=[[HEAD]]) for p, c in new]
    data += [dict(range=f"'{t}'!{letter(c)}{i}", values=[[v]]) for t, c, i, v in cells]
    sh.update(data)
    reqs = []
    for p, c in new:
        reqs += [{"updateCells": {"rows": [{"values": [{"note": NK["source"]}]}], "fields": "note",
                                  "start": dict(sheetId=p["sheetId"], rowIndex=0, columnIndex=c)}},
                 {"addDimensionGroup": {"range": rng(p, c)}},
                 {"updateDimensionGroup": {"dimensionGroup": dict(range=rng(p, c), depth=1, collapsed=True), "fields": "collapsed"}}]
    if reqs:
        sh.batch(reqs)
    print("  시트에 반영: 열", len(new), "· 칸", len(cells))


if __name__ == "__main__":
    only = [a for a in sys.argv[1:] if not a.startswith("-")]
    for w, g in (("birds", "AVES"), ("reptiles", "REPTILIA")):
        if not only or w in only:
            run(w, g, "--apply" in sys.argv)
