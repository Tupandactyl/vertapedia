"""파충류 시트에서 큰 속(data/subgenus.json 에 아속 배정이 있는 속)의 종 행을 아속별로 정렬하고,
아속마다 머리 줄(옅은 분홍)을 넣는다. 속 줄(연두색, add_genus_rows.py)과 같은 모양:
학명 열에 아속 이름만(「Odatria」), 행 전체 배경 #FCE4EC. 아속을 못 정한 종은 맨 뒤 「(아속 미정)」 아래에 둔다.
아속 줄은 속 줄처럼 한 단어지만, 속 줄 아래 그 속 종들 사이에 있다는 것으로 구별한다(import_names.py 도 같은 규칙).

정렬: 아속 이름 알파벳 순, 아속 안에서는 종소명 순. 아종 행(세 단어)은 그 종 바로 뒤에 붙어 다닌다.
행은 moveDimension으로 옮기므로 서식·메모가 그대로 따라간다. 다시 돌리면 기존 아속 줄을 지우고 새로 만든다.
사이트(import_names.py)와 시트 동기화(sync_reptile_sheet.py)는 아속 줄을 건너뛴다.

    python scripts/add_subgenus_rows.py          # 미리보기(data/subgenus_preview.csv)
    python scripts/add_subgenus_rows.py --apply  # 시트에 쓴다
    python scripts/add_subgenus_rows.py Varanus --apply   # 그 속만
"""
import csv
import json
import re
import sys
from pathlib import Path

import requests

from sheets_api import API, Sheet

DATA = Path(__file__).resolve().parent.parent / "data"
PINK = {"red": 0.98823529, "green": 0.89411765, "blue": 0.9254902}  # #FCE4EC
SKIP_TABS = {"과단위 번역", "지정관리종목록", "통합목록"}
UNPLACED = "아속 미정"
SUB_RE = re.compile(r"^([A-Z][a-z]+) \(([^)]+)\)$")


def cell(row, c):
    return (row[c] if len(row) > c else "").strip()


def is_sub_row(a):
    """아속 줄 모양: 아속 이름 한 단어(「Odatria」), 「(아속 미정)」, 옛 꼴 「Varanus (Odatria)」"""
    return bool(SUB_RE.match(a)) or a == f"({UNPLACED})" or (len(a.split()) == 1 and a[:1].isupper())


def find_block(values, off, genus):
    """속 줄 다음부터 그 속의 종·아종·아속 줄이 이어지는 구간 [s, e).
    한 단어 줄은 바로 다음 종 행이 이 속일 때만 아속 줄로 본다(아니면 다음 속 줄)."""
    for i, row in enumerate(values):
        if cell(row, off) == genus:
            s = e = i + 1
            while e < len(values):
                a = cell(values[e], off)
                if a.startswith(genus + " ") and not SUB_RE.match(a):
                    e += 1
                    continue
                if is_sub_row(a):
                    k = e + 1
                    while k < len(values) and is_sub_row(cell(values[k], off)):
                        k += 1
                    if k < len(values) and cell(values[k], off).startswith(genus + " "):
                        e += 1
                        continue
                if SUB_RE.match(a) and a.startswith(genus + " "):
                    e += 1
                    continue
                break
            return i, s, e
    return None


def units(values, off, s, e):
    """[(시작 행, 줄 수, 종 학명)] — 아속 줄은 따로 모은다."""
    out, subs = [], []
    for i in range(s, e):
        a = cell(values[i], off)
        if is_sub_row(a):
            subs.append(i)
        elif len(a.split()) == 2:
            out.append([i, 1, a])
        elif out and a.startswith(out[-1][2] + " "):  # 아종 행
            out[-1][1] += 1
        else:
            out.append([i, 1, a])
    return out, subs


def post(sh, reqs):
    for k in range(0, len(reqs), 400):
        requests.post(API + sh.id + ":batchUpdate", headers=sh._h(), json={"requests": reqs[k:k + 400]},
                      timeout=300).raise_for_status()


def sub_key(sub):
    return (sub == UNPLACED, sub)


def main(apply, only):
    data = json.loads((DATA / "subgenus.json").read_text(encoding="utf-8"))
    sh = Sheet("reptiles")
    tabs = [(p["properties"]["title"], p["properties"]["sheetId"], p["properties"]["gridProperties"]["columnCount"])
            for p in sh.meta()["sheets"] if p["properties"]["title"] not in SKIP_TABS]
    preview = []
    for tab, sid, ncols in tabs:
        values = sh.values(tab)
        h = values[0] if values else []
        off = h.index("학명") if "학명" in h else 0
        for genus, info in data.items():
            if only and genus not in only:
                continue
            assign = info["species"]
            blk = find_block(values, off, genus)
            if not blk:
                continue
            # 1) 기존 아속 줄 지우기
            _, s, e = blk
            us, old = units(values, off, s, e)
            if old and apply:
                post(sh, [{"deleteDimension": {"range": {"sheetId": sid, "dimension": "ROWS", "startIndex": i, "endIndex": i + 1}}}
                          for i in sorted(old, reverse=True)])
                values = sh.values(tab)
                _, s, e = find_block(values, off, genus)
                us, _ = units(values, off, s, e)
            elif old:
                print(f"{tab} {genus}: 기존 아속 줄 {len(old)}개는 --apply 때 지우고 다시 만든다")
                us = [u for u in us]
                shift = lambda i: i - sum(1 for o in old if o < i)
                us = [[shift(u[0]), u[1], u[2]] for u in us]
            # 2) 목표 순서
            sub_of = {u[2]: assign.get(u[2]) or UNPLACED for u in us}
            target = sorted(us, key=lambda u: (sub_key(sub_of[u[2]]), u[2].split()[-1]))
            reqs, cur, pos = [], list(us), s
            for k, u in enumerate(target):
                a = sum(x[1] for x in cur[:cur.index(u)]) + s
                if a != pos:
                    reqs.append({"moveDimension": {"source": {"sheetId": sid, "dimension": "ROWS", "startIndex": a,
                                                              "endIndex": a + u[1]}, "destinationIndex": pos}})
                cur.remove(u)
                cur.insert(k, u)
                pos += u[1]
            # 3) 아속 머리 줄: 아래부터 끼운다
            heads, pos, prev = [], s, None
            for u in target:
                if sub_of[u[2]] != prev:
                    heads.append((pos, sub_of[u[2]]))
                    prev = sub_of[u[2]]
                pos += u[1]
            for k, (p, sub) in enumerate(sorted(heads, reverse=True)):
                reqs.append({"insertDimension": {"range": {"sheetId": sid, "dimension": "ROWS", "startIndex": p,
                                                           "endIndex": p + 1}, "inheritFromBefore": False}})
            n = min(ncols, 12)
            for k, (p, sub) in enumerate(heads):
                r = p + k
                label = f"({UNPLACED})" if sub == UNPLACED else sub
                cells = [{"userEnteredValue": {"stringValue": label}} if c == off else {} for c in range(n)]
                reqs.append({"updateCells": {"range": {"sheetId": sid, "startRowIndex": r, "endRowIndex": r + 1,
                                                       "startColumnIndex": 0, "endColumnIndex": n},
                                             "rows": [{"values": [dict(c, userEnteredFormat={"backgroundColor": PINK,
                                                                                            "textFormat": {"bold": False}})
                                                                  for c in cells]}],
                                             "fields": "userEnteredValue,userEnteredFormat.backgroundColor,"
                                                       "userEnteredFormat.textFormat.bold"}})
            counts = {}
            for u in target:
                counts[sub_of[u[2]]] = counts.get(sub_of[u[2]], 0) + 1
            print(f"{tab} {genus}: 종 {len(us)} · 옮김 {sum(1 for r in reqs if 'moveDimension' in r)} · 아속 {len(heads)} {counts}")
            for u in target:
                preview.append(dict(tab=tab, genus=genus, subgenus=sub_of[u[2]], species=u[2]))
            if apply:
                post(sh, reqs)
                values = sh.values(tab)
    with open(DATA / "subgenus_preview.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["tab", "genus", "subgenus", "species"])
        w.writeheader()
        w.writerows(preview)
    print("미리보기: data/subgenus_preview.csv", "" if apply else "(시트는 그대로)")


if __name__ == "__main__":
    main("--apply" in sys.argv, [a for a in sys.argv[1:] if not a.startswith("--")])
