"""파충류 시트의 큰 과 탭들(도마뱀과 1~4, 뱀과 1~4)을 사이트처럼 아과별로 묶는다.

속 묶음(속 줄 + 그 속의 종·아종 행)을 아과(data/rdb_subfamily.json, Reptile Database) 순서로 다시 늘어놓고,
아과마다 머리 줄을 넣는다. 머리 줄 모양: 학명 열에 「Eugongylinae (뱀눈도마뱀아과)」(국명이 없으면 학명만),
A~J 열 병합, 배경 #FCE5CD, 굵게. 아과를 못 정한 속은 맨 뒤 「Incertae sedis (아과 미정)」 아래에 둔다.
아과 안에서는 속 이름 순서(지금 시트 순서)를 그대로 둔다. 탭 나누기는 PLAN 을 따른다.

서식·병합까지 옮겨 쓴다(줄무늬 범위는 그대로)(셀 값·서식·메모·데이터 확인). 다시 돌리면 기존 아과 줄을 지우고 새로 만든다.
사이트(import_names.py)·시트 동기화(sync_reptile_sheet.py)·속 줄/아속 줄 스크립트는 아과 줄을 건너뛴다.

    python scripts/group_subfamily_rows.py Colubridae           # 미리보기(탭별 아과·속·행 수). 과를 빼면 Scincidae
    python scripts/group_subfamily_rows.py Colubridae --apply   # 먼저 .secrets/backup 에 xlsx 백업 후 시트에 쓴다
"""
import json
import re
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

import requests

from sheets_api import API, SHEETS, Sheet

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
# 과마다 탭과 탭별 아과(알파벳 순). 여기 없는 아과·미정은 마지막 탭 끝에 붙는다.
CONFIGS = {
    "Scincidae": (["도마뱀과 1", "도마뱀과 2", "도마뱀과 3", "도마뱀과 4"],
                  [["Acontiinae", "Egerniinae", "Eugongylinae"],
                   ["Lygosominae", "Mabuyinae", "Ristellinae"],
                   ["Scincinae"],
                   ["Sphenomorphinae"]]),
    "Colubridae": (["뱀과 1", "뱀과 2", "뱀과 3", "뱀과 4"],
                   [["Calamariinae", "Chrysopeleinae", "Colubrinae"],
                    ["Dipsadinae"],
                    ["Grayiinae", "Natricinae"],
                    ["Pseudoxenodontinae", "Sibynophiinae"]]),
    # 「이구아나과, 아가마과 1」은 이구아나과 다음 아가마과 머리 줄 아래부터만 다룬다
    "Agamidae": (["이구아나과, 아가마과 1", "아가마과 2"],
                 [["Agaminae", "Amphibolurinae"],
                  ["Draconinae", "Hydrosaurinae", "Leiolepidinae", "Uromastycinae"]]),
}
FAMILY = "Scincidae"
TABS, PLAN = CONFIGS[FAMILY]
UNPLACED = "Incertae sedis"
SUBFAM_RE = re.compile(r"^(?:[A-Z][a-z]+inae|Incertae sedis)\b")
ORANGE = {"red": 0.98823529, "green": 0.89803922, "blue": 0.80392157}  # #FCE5CD
FIELDS = "userEnteredValue,userEnteredFormat,note,dataValidation,textFormatRuns"
MERGE_COLS = 10  # 과 머리 줄과 같이 A~J


def text(v):
    return ((v or {}).get("userEnteredValue") or {}).get("stringValue", "").strip()


def ko_names():
    names = json.loads((DATA / "names.json").read_text(encoding="utf-8"))
    return {t["sci"]: t.get("name") for t in names
            if t["group"] == "REPTILIA" and t["rank"] == "subfamily" and t.get("family") == FAMILY}


def read(sh):
    params = [("ranges", f"'{t}'") for t in TABS] + [
        ("includeGridData", "true"),
        ("fields", "sheets(properties(sheetId,title,gridProperties),merges,"
                   f"data(rowData(values({FIELDS}))))")]
    r = requests.get(API + sh.id, headers=sh._h(), params=params, timeout=300)
    r.raise_for_status()
    return {s["properties"]["title"]: s for s in r.json()["sheets"]}


def start_row(rows):
    """이 과 머리 줄(「Agamidae (아가마과)」) 다음 행(0부터). 한 탭에 여러 과가 있으면 그 과 부분만 다룬다."""
    for i, row in enumerate(rows):
        vals = row.get("values", [])
        if vals and re.match(rf"^{FAMILY}\b", text(vals[0])):
            return i + 1
    raise SystemExit(f"{FAMILY} 머리 줄을 못 찾았다")


def first_word_after(rows, i):
    for row in rows[i + 1:]:
        vals = row.get("values", [])
        a = text(vals[0]) if vals else ""
        if a:
            return a
    return ""


def blocks(rows, start=2):
    """[(속, [행...])] — 과 머리 줄 다음부터. 기존 아과 줄과 빈 줄 꼬리는 버린다.
    아속 줄(한 단어·「미분류」)은 바로 다음 종 행이 지금 속이면 그 속 묶음에 넣는다(속 이름과 같은 아속 줄 포함)."""
    out = []
    for i in range(start, len(rows)):
        row = rows[i]
        vals = row.get("values", [])
        a = text(vals[0]) if vals else ""
        if not a:
            continue
        if SUBFAM_RE.match(a):
            continue
        w = a.split()
        if (len(w) == 1 or a == "미분류") and out and first_word_after(rows, i).startswith(out[-1][0] + " "):
            out[-1][1].append(row)
            continue
        if len(w) == 1 or not out or w[0] != out[-1][0]:
            out.append((w[0], [row]))
        else:
            out[-1][1].append(row)
    return out


def merge(allb):
    """같은 속이 여러 곳(다른 탭 포함)에 나뉘어 있으면 하나로 합친다. 속 줄은 하나만 남기고,
    합친 속은 종 행을 학명 순으로 정렬한다(아종 행은 그 종 바로 뒤에 붙어 다닌다)."""
    order, got, dropped = [], {}, []
    for g, rows in allb:
        if g not in got:
            got[g] = []
            order.append(g)
        got[g].append(rows)
    out = []
    for g in order:
        parts = got[g]
        if len(parts) == 1:
            out.append((g, parts[0]))
            continue
        dropped.append(f"{g}({len(parts)}곳)")
        heads = [r[0] for r in parts if len(text(r[0]["values"][0]).split()) == 1]
        units = []
        for rows in parts:
            for row in rows:
                a = text(row["values"][0]) if row.get("values") else ""
                w = a.split()
                if len(w) == 1:
                    continue
                if len(w) == 2 or not units or not a.startswith(units[-1][0] + " "):
                    units.append((a, [row]))
                else:
                    units[-1][1].append(row)
        units.sort(key=lambda u: u[0])
        out.append((g, heads[:1] + [r for _, rs in units for r in rs]))
    return out, dropped


def header_row(sf, ko):
    label = f"{UNPLACED} (아과 미정)" if sf == UNPLACED else (f"{sf} ({ko})" if ko else sf)
    fmt = {"backgroundColor": ORANGE, "verticalAlignment": "TOP",
           "textFormat": {"fontFamily": "Calibri", "fontSize": 11, "bold": True}}
    return {"values": [{"userEnteredValue": {"stringValue": label}, "userEnteredFormat": fmt}]
            + [{"userEnteredFormat": fmt} for _ in range(MERGE_COLS - 1)]}


def main(apply):
    sf_of = json.loads((DATA / "rdb_subfamily.json").read_text(encoding="utf-8"))
    ko = ko_names()
    sh = Sheet("reptiles")
    grid = read(sh)
    allb, starts = [], {}
    for t in TABS:
        rd = grid[t]["data"][0].get("rowData", [])
        starts[t] = start_row(rd)
        allb += blocks(rd, starts[t])
    allb, dropped = merge(allb)
    n_old = sum(len(b[1]) for b in allb)
    if dropped:
        print("겹친 속 줄을 하나로 합쳤다:", ", ".join(dropped))
    by_sf = {}
    for g, rows in allb:
        by_sf.setdefault(sf_of.get(g) or UNPLACED, []).append((g, rows))
    planned = [s for p in PLAN for s in p]
    extra = sorted(s for s in by_sf if s not in planned and s != UNPLACED) + ([UNPLACED] if UNPLACED in by_sf else [])
    plan = [list(p) for p in PLAN]
    plan[-1] += extra

    new = {}
    for t, sfs in zip(TABS, plan):
        rows = []
        for s in sfs:
            if s not in by_sf:
                continue
            rows.append(header_row(s, ko.get(s)))
            for g, rs in by_sf[s]:
                rows += rs
        new[t] = rows
        print(f"{t}: " + ", ".join(f"{s}({ko.get(s) or '-'}) 속 {len(by_sf.get(s, []))}"
                                    f"·행 {sum(len(r) for _, r in by_sf.get(s, []))}" for s in sfs if s in by_sf)
              + f" → 데이터 행 {len(rows)}")
    moved = sum(len(r) for r in new.values()) - sum(1 for r in new.values() for x in r if SUBFAM_RE.match(text(x['values'][0])))
    print(f"속 묶음 {len(allb)} · 옮길 행 {moved} (원래 {n_old})")
    assert moved == n_old
    print("합친 뒤 행", n_old)
    if not apply:
        return

    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    bk = ROOT / ".secrets" / "backup" / f"reptiles_before_subfamily_rows_{FAMILY}_{stamp}.xlsx"
    with urllib.request.urlopen(f"https://docs.google.com/spreadsheets/d/{SHEETS['reptiles']}/export?format=xlsx",
                                timeout=180) as r:
        body = r.read()
    assert body.startswith(b"PK"), "백업 실패"
    bk.write_bytes(body)
    print("백업:", bk.name, len(body) // 1024, "KB")

    reqs = []
    for t in TABS:
        s = grid[t]
        sid = s["properties"]["sheetId"]
        old_len = len(s["data"][0].get("rowData", []))
        rows = new[t]
        st = starts[t]
        end = st + len(rows)
        cap = s["properties"]["gridProperties"]["rowCount"]
        if end > cap:
            reqs.append({"appendDimension": {"sheetId": sid, "dimension": "ROWS", "length": end - cap + 20}})
        for m in s.get("merges", []):  # 과 머리 줄(행 1) 말고 데이터 칸 병합은 풀었다가 아과 줄에만 다시 건다
            if m["startRowIndex"] >= st:
                reqs.append({"unmergeCells": {"range": m}})
        reqs.append({"updateCells": {"start": {"sheetId": sid, "rowIndex": st, "columnIndex": 0},
                                     "rows": rows, "fields": FIELDS}})
        if old_len > end:  # 줄어든 탭: 새 목록 아래 예전 행을 비운다(빈 행을 rows 로 보내면 무시된다)
            reqs.append({"updateCells": {"range": {"sheetId": sid, "startRowIndex": end, "endRowIndex": old_len},
                                         "fields": FIELDS}})
        for i, row in enumerate(rows):
            if SUBFAM_RE.match(text(row["values"][0])):
                reqs.append({"mergeCells": {"mergeType": "MERGE_ALL", "range": {
                    "sheetId": sid, "startRowIndex": st + i, "endRowIndex": st + i + 1,
                    "startColumnIndex": 0, "endColumnIndex": MERGE_COLS}}})
    r = requests.post(API + sh.id + ":batchUpdate", headers=sh._h(), timeout=600, json={"requests": reqs})
    if not r.ok:
        sys.exit(r.text[:2000])
    print("시트에 썼다:", len(reqs), "요청")


if __name__ == "__main__":
    fam = next((a for a in sys.argv[1:] if a in CONFIGS), "Scincidae")
    FAMILY = fam
    TABS, PLAN = CONFIGS[fam]
    main("--apply" in sys.argv)
