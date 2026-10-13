"""파충류 구글 시트를 Reptile Database 기준(scripts/rdb.py 결과)에 맞춰 고친다.

먼저 import_names.py 를 돌려 data/rdb.json 이 있어야 한다.
과별 탭만 고친다(통합목록·과단위 번역·지정관리종목록은 건드리지 않음). 행은 지우지 않는다.

  - 학명 변경 : 학명·속명·종명·Author 를 새 학명으로, 비고에 이전 학명
  - 아종 통합·목록에 없음 : 비고에만 적는다(행은 그대로)
  - 새 종 : 같은 속 마지막 행 뒤(없으면 같은 과에서 속 이름 순서 자리)에 행을 끼워 넣는다
  - Subspecies 열 : Reptile Database 아종 목록과 다르면 고친다
  - 영명 열 : 비어 있으면 iNaturalist 영명으로 채운다

    python scripts/sync_reptile_sheet.py           # 미리보기만(data/sheet_sync_preview.csv)
    python scripts/sync_reptile_sheet.py --apply   # 시트에 쓴다
"""
import csv
import json
import re
import sys
from datetime import date
from pathlib import Path

import rdb
from sheets_api import Sheet

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SKIP_TABS = {"과단위 번역", "지정관리종목록", "통합목록"}
COL = dict(sci=0, genus=1, ep=2, ssp=7, author=8)
EN_H, NOTE_H = "영명", "비고 (Reptile Database 대조)"
TODAY = date.today().isoformat()


def col_letter(i):
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def author_fmt(a):
    return re.sub(r",\s*(\d{4})", r" \1", a or "").strip()


def ssp_text(lst):
    return "\n".join(f"{x['sci']} {author_fmt(x.get('author'))}".strip() for x in lst)


def main(apply):
    log = json.loads((DATA / "rdb.json").read_text(encoding="utf-8"))
    names = json.loads((DATA / "names.json").read_text(encoding="utf-8"))
    cur, _, _ = rdb.current_list(DATA)
    media_en = {}
    for f in (DATA / "media").glob("*.json"):
        m = json.loads(f.read_text(encoding="utf-8"))
        if (m.get("inat") or {}).get("common"):
            media_en[m["sci"]] = m["inat"]["common"]
    fam_of = {t["sci"]: t.get("family") for t in names if t["group"] == "REPTILIA" and t["rank"] == "species"}

    sh = Sheet("reptiles")
    meta = sh.meta()
    tabs = [(p["properties"]["title"], p["properties"]["sheetId"]) for p in meta["sheets"]
            if p["properties"]["title"] not in SKIP_TABS]
    grid = {t: sh.values(t) for t, _ in tabs}

    renamed = {r["old"]: r for r in log["renamed"]}
    merged = {r["old"]: r for r in log["merged"]}
    dropped = {r["sci"] for r in log["dropped"]}
    plan, cells, rows_at = [], [], []  # rows_at: (탭, 시트id, 이 행 뒤에, [행 값], 학명)

    def put(tab, r, c, old, new, why):
        if (old or "") == (new or ""):
            return
        cells.append(dict(range=f"'{tab}'!{col_letter(c)}{r + 1}", values=[[new]]))
        plan.append(dict(tab=tab, row=r + 1, col=col_letter(c), old=old, new=new, why=why))

    rows = []  # (탭, 행 번호, 행, 과)
    for tab, _ in tabs:
        g = grid[tab]
        h = g[0] if g else []
        ncol = max(len(h), 10)
        en_c = h.index(EN_H) if EN_H in h else ncol
        note_c = h.index(NOTE_H) if NOTE_H in h else (en_c + 1 if en_c >= ncol else ncol)
        if EN_H not in h:
            put(tab, 0, en_c, "", EN_H, "열 추가")
        if NOTE_H not in h:
            put(tab, 0, note_c, "", NOTE_H, "열 추가")
        off = h.index("학명") if "학명" in h else 0  # 분류미정 뱀 탭은 B열부터
        C = {k: v + off for k, v in COL.items()}
        grid[tab] = (g, en_c, note_c, off)
        fam = None
        for i, row in enumerate(g[1:], start=1):
            a = (row[off] if len(row) > off else "").strip()
            m = re.match(r"^([A-Z][a-z]+idae)\b", (row[0] if row else "").strip())
            if m:
                fam = m.group(1)
                continue
            if len(a.split()) != 2:
                continue
            rows.append((tab, i, a, fam))
            cell = lambda c: row[c] if len(row) > c else ""
            sci = a
            new = sci
            if sci in renamed:
                r = renamed[sci]
                new = r["new"]
                ng, ne = new.split()
                put(tab, i, C["sci"], sci, new, "학명 변경")
                put(tab, i, C["genus"], cell(C["genus"]), ng, "학명 변경")
                put(tab, i, C["ep"], cell(C["ep"]), ne, "학명 변경")
                if cur.get(new, {}).get("author"):
                    put(tab, i, C["author"], cell(C["author"]), author_fmt(cur[new]["author"]), "학명 변경")
                put(tab, i, note_c, cell(note_c), f"{TODAY} 학명 변경: 이전 {sci} ({r['how']})", "학명 변경")
            elif sci in merged:
                r = merged[sci]
                put(tab, i, note_c, cell(note_c),
                    f"{TODAY} {r['into']}에 통합" + (f" (아종 {r['ssp']})" if r["ssp"] else " (이명)"), r["how"])
                continue
            elif sci in dropped:
                put(tab, i, note_c, cell(note_c), f"{TODAY} Reptile Database 종 목록에 없음 (이명 처리 추정)", "목록에 없음")
                continue
            if new in cur:
                want = ssp_text(cur[new]["subspecies"])
                if want != cell(C["ssp"]).strip():
                    put(tab, i, C["ssp"], cell(C["ssp"]), want, "아종 목록")
            if not cell(en_c) and media_en.get(new):
                put(tab, i, en_c, "", media_en[new], "영명(iNaturalist)")

    # 새 종: 같은 속 마지막 행 뒤, 없으면 같은 과에서 속 이름 순서 자리
    by_tab_id = dict(tabs)
    for a in log["added"]:
        s = a["sci"]
        g = s.split()[0]
        fam = fam_of.get(s) or a.get("family")
        same_g = [x for x in rows if x[2].split()[0] == g]
        if same_g:
            at = same_g[-1]
        else:
            same_f = [x for x in rows if x[3] == fam]
            before = [x for x in same_f if x[2].split()[0] < g]
            at = (before or same_f or [None])[-1]
        if at is None:
            plan.append(dict(tab="?", row="", col="", old="", new=s, why="새 종 — 넣을 자리를 못 찾음"))
            continue
        tab = at[0]
        _, en_c, note_c, off = grid[tab]
        vals = [""] * (max(en_c, note_c) + 1)
        if off:
            vals[0] = fam or ""
        vals[COL["sci"] + off], vals[COL["genus"] + off], vals[COL["ep"] + off] = s, g, s.split()[1]
        vals[COL["ssp"] + off] = ssp_text(cur.get(s, {}).get("subspecies", []))
        vals[COL["author"] + off] = author_fmt(cur.get(s, {}).get("author"))
        vals[en_c] = media_en.get(s, "")
        vals[note_c] = f"{TODAY} Reptile Database 새 종 ({a.get('change') or '추가'})"
        rows_at.append((tab, by_tab_id[tab], at[1], vals, s))
        plan.append(dict(tab=tab, row=f"{at[1] + 1} 뒤", col="행 추가", old="", new=s, why="새 종"))

    out = DATA / "sheet_sync_preview.csv"
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["why", "tab", "row", "col", "old", "new"])
        w.writeheader()
        w.writerows(plan)
    from collections import Counter
    print("미리보기:", out)
    for k, v in Counter(p["why"] for p in plan).most_common():
        print(f"  {k}: {v}")
    if not apply:
        return

    import requests
    from sheets_api import API
    # 0) 영명·비고 열이 들어갈 자리가 없으면 열을 늘린다
    ncols = {p["properties"]["title"]: p["properties"]["gridProperties"].get("columnCount", 0) for p in meta["sheets"]}
    grow = []
    for tab, sid in tabs:
        _, en_c, note_c, _ = grid[tab]
        need = max(en_c, note_c) + 1
        if ncols[tab] < need:
            grow.append({"appendDimension": {"sheetId": sid, "dimension": "COLUMNS", "length": need - ncols[tab]}})
    if grow:
        requests.post(API + sh.id + ":batchUpdate", headers=sh._h(), json={"requests": grow}, timeout=300).raise_for_status()
    # 1) 칸 고치기(원래 행 번호 기준이므로 행을 끼우기 전에)
    for k in range(0, len(cells), 2000):
        sh.update(cells[k:k + 2000])
    # 2) 행 끼우기: 탭마다 아래쪽부터
    data = []
    # 같은 자리에 여럿이면 뒤에 넣은 것이 위로 오므로 학명 역순으로 넣어 알파벳 순서를 지킨다
    rows_at_sorted = sorted(rows_at, key=lambda x: (x[0], -x[2], [-ord(c) for c in x[4]]))
    reqs = [{"insertDimension": {"range": {"sheetId": sid, "dimension": "ROWS", "startIndex": after + 1, "endIndex": after + 2},
                                 "inheritFromBefore": True}} for tab, sid, after, vals, s in rows_at_sorted]
    for k in range(0, len(reqs), 200):
        r = requests.post(API + sh.id + ":batchUpdate", headers=sh._h(), json={"requests": reqs[k:k + 200]}, timeout=300)
        r.raise_for_status()
    # 끼운 뒤 각 새 행의 실제 위치: 같은 탭에서 그보다 위에 끼운 행 수만큼 밀린다
    for tab, sid, after, vals, s in rows_at_sorted:
        above = sum(1 for t2, _, a2, _, s2 in rows_at if t2 == tab and (a2 < after or (a2 == after and s2 < s)))
        data.append(dict(range=f"'{tab}'!A{after + 2 + above}", values=[vals]))
    for k in range(0, len(data), 1000):
        sh.update(data[k:k + 1000])
    print("시트에 썼습니다:", len(cells), "칸 ·", len(rows_at), "행 추가")


if __name__ == "__main__":
    main("--apply" in sys.argv)
