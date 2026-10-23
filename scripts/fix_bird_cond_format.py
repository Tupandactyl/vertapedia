"""조류 시트 v2026 탭 조건부 서식 손보기.

1) 맞춤 수식의 열 참조 =$I… 를 =$J… 로 (해설 열이 J)
2) SCIENTIFIC NAME 열(D)에서 RANK 가 genus·species 인 행은 기울임체(규칙으로 걸어 새 행에도 적용).
   한 칸에는 맞는 규칙 중 첫 번째만 적용되므로 D열 규칙을 맨 앞에 두고, 속 행은 연두 배경을 함께 준다.

    python scripts/fix_bird_cond_format.py
"""
import re
import time

import requests

from sheets_api import API, Sheet

ITALIC = '=OR($A1="genus",$A1="species")'  # 예전 규칙(지운다)
GENUS_D = '=$A2="genus"'
SPECIES_D = '=$A2="species"'
GREEN = {"red": 0.8509804, "green": 0.91764706, "blue": 0.827451}


def main():
    sh = Sheet("birds")
    sheets = requests.get(API + sh.id, headers=sh._h(), timeout=120, params={
        "fields": "sheets(properties(sheetId,title,gridProperties),conditionalFormats)"}).json()["sheets"]
    for s in sheets:
        p = s["properties"]
        if not p["title"].endswith("v2026") or p["title"].startswith("과단위"):
            continue
        sid, rows = p["sheetId"], p["gridProperties"]["rowCount"]
        rules = s.get("conditionalFormats", [])
        reqs = []
        for i, r in enumerate(rules):
            cond = (r.get("booleanRule") or {}).get("condition", {})
            vals = cond.get("values", [])
            f = vals[0].get("userEnteredValue", "") if vals else ""
            nf = re.sub(r"\$I(\d)", r"$J\1", f)
            if nf != f:
                r2 = {k: v for k, v in r.items()}
                r2["booleanRule"] = dict(r["booleanRule"], condition=dict(cond, values=[{"userEnteredValue": nf}]))
                reqs.append({"updateConditionalFormatRule": {"sheetId": sid, "index": i, "rule": r2}})
        # 한 칸에는 맞는 규칙 가운데 첫 번째만 적용되므로, D열 기울임 규칙을 맨 앞에 둔다(속 행은 연두 배경도 함께)
        for i in [i for i, r in enumerate(rules) if (r.get("booleanRule") or {}).get("condition", {}).get("values", [{}])[0]
                  .get("userEnteredValue", "") in (ITALIC, GENUS_D, SPECIES_D)][::-1]:
            reqs.append({"deleteConditionalFormatRule": {"sheetId": sid, "index": i}})
        d_col = [{"sheetId": sid, "startRowIndex": 1, "endRowIndex": rows, "startColumnIndex": 3, "endColumnIndex": 4}]
        reqs.append({"addConditionalFormatRule": {"index": 0, "rule": {"ranges": d_col, "booleanRule": {
            "condition": {"type": "CUSTOM_FORMULA", "values": [{"userEnteredValue": SPECIES_D}]},
            "format": {"textFormat": {"italic": True}}}}}})
        reqs.append({"addConditionalFormatRule": {"index": 0, "rule": {"ranges": d_col, "booleanRule": {
            "condition": {"type": "CUSTOM_FORMULA", "values": [{"userEnteredValue": GENUS_D}]},
            "format": {"textFormat": {"italic": True}, "backgroundColor": GREEN}}}}})
        if reqs:
            requests.post(API + sh.id + ":batchUpdate", headers=sh._h(), json={"requests": reqs}, timeout=300).raise_for_status()
            print(p["title"], len(reqs), flush=True)
            time.sleep(1)


if __name__ == "__main__":
    main()
