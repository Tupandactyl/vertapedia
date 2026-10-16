"""파충류 시트의 유린목 탭에 속 줄(연두색)을 넣는다. 악어목·거북목 탭과 같은 모양:
A열(분류미정 탭은 학명 열)에 속 학명, 행 전체 배경 #D9EAD3. 같은 속이 처음 나오는 종 행 바로 위에 넣는다.
이미 속 줄이 있는 속은 건너뛴다.

    python scripts/add_genus_rows.py 살모사과        # 탭 하나만
    python scripts/add_genus_rows.py --all           # 유린목 탭 전부
    (뒤에 --dry 를 붙이면 넣을 자리만 센다)
"""
import sys

import requests

from sheets_api import API, Sheet

NOT_SQUAMATA = {"과단위 번역", "지정관리종목록", "통합목록", "악어목", "마타마타과, 가로목거북과, 옆목펄거북과",
                "자라,바다거북,진흙거북,늪거북", "남생이과,땅거북과"}
GREEN = {"red": 0.8509804, "green": 0.91764706, "blue": 0.827451}


def plan_tab(values):
    h = values[0] if values else []
    off = h.index("학명") if "학명" in h else 0
    have, out, prev = set(), [], None
    for i, row in enumerate(values[1:], start=1):
        a = (row[off] if len(row) > off else "").strip()
        w = a.split()
        if len(w) == 1 and a[:1].isupper() and not a.endswith(")"):
            have.add(a)  # 이미 있는 속 줄
            prev = a
            continue
        if len(w) != 2 or not (w[1].isalpha() and w[1].islower()):  # 과 머리줄 「Viperidae (살모사과)」 등
            prev = None
            continue
        g = w[0]
        if g != prev and g not in have:
            out.append((i, g))  # i 번째 행(0부터) 위에 넣는다
            have.add(g)
        prev = g
    return off, out


def apply_tab(sh, tab, sid, ncols, dry):
    values = sh.values(tab)
    off, plan = plan_tab(values)
    print(f"{tab}: 속 줄 {len(plan)}개", flush=True)
    if dry or not plan:
        return len(plan)
    reqs = []
    for i, g in sorted(plan, reverse=True):  # 아래부터 끼워야 위쪽 행 번호가 그대로다
        reqs.append({"insertDimension": {"range": {"sheetId": sid, "dimension": "ROWS", "startIndex": i, "endIndex": i + 1},
                                         "inheritFromBefore": False}})
    # 끼운 뒤 위치: 원래 i 위에 끼운 줄이 k개 있으면 i + k
    rows = sorted(plan)
    for k, (i, g) in enumerate(rows):
        r = i + k
        cells = [{"userEnteredValue": {"stringValue": g}} if c == off else {} for c in range(ncols)]
        reqs.append({"updateCells": {"range": {"sheetId": sid, "startRowIndex": r, "endRowIndex": r + 1,
                                               "startColumnIndex": 0, "endColumnIndex": ncols},
                                     "rows": [{"values": [dict(c, userEnteredFormat={"backgroundColor": GREEN,
                                                                                    "textFormat": {"bold": False}})
                                                          for c in cells]}],
                                     "fields": "userEnteredValue,userEnteredFormat.backgroundColor,userEnteredFormat.textFormat.bold"}})
    for k in range(0, len(reqs), 500):
        requests.post(API + sh.id + ":batchUpdate", headers=sh._h(), json={"requests": reqs[k:k + 500]},
                      timeout=300).raise_for_status()
    return len(plan)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry" in sys.argv
    sh = Sheet("reptiles")
    meta = sh.meta()
    tabs = [(p["properties"]["title"], p["properties"]["sheetId"], p["properties"]["gridProperties"]["columnCount"])
            for p in meta["sheets"]]
    todo = [t for t in tabs if t[0] not in NOT_SQUAMATA] if "--all" in sys.argv else [t for t in tabs if t[0] in args]
    total = sum(apply_tab(sh, tab, sid, min(ncols, 12), dry) for tab, sid, ncols in todo)
    print("속 줄 합계:", total, "(시험)" if dry else "")


if __name__ == "__main__":
    main()
