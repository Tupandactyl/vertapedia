"""조류 시트 v2026 탭의 서식을 본보기 탭(편집진이 만든 '고악류 v2026')과 같게 맞춘다.

- 조건부 서식(RANK가 family·genus면 행 배경, 해설 값에 따른 글자색)을 그대로 복사
- 머리 행 서식(가운데·위 정렬, Calibri 11 굵게), 본문 글꼴, 열 너비, 첫 행 고정

    python scripts/copy_bird_format.py
"""
import time

import requests

from sheets_api import API, Sheet

TEMPLATE = "고악류 v2026"
SKIP = {"과단위 v2026", "남극해 조류 번역", "남극해 조류 스플릿 정리", "캐나다 조류 번역", "v2026 변경 대조"}


def main():
    sh = Sheet("birds")
    full = requests.get(API + sh.id, headers=sh._h(), timeout=120, params={
        "fields": "sheets(properties(sheetId,title,gridProperties),conditionalFormats)"}).json()["sheets"]
    tpl = next(s for s in full if s["properties"]["title"] == TEMPLATE)
    tid = tpl["properties"]["sheetId"]
    meta = requests.get(API + sh.id, headers=sh._h(), timeout=60, params={
        "ranges": f"'{TEMPLATE}'!A1:J2", "includeGridData": "true",
        "fields": "sheets.data(columnMetadata.pixelSize,rowData.values.userEnteredFormat)"}).json()
    d = meta["sheets"][0]["data"][0]
    widths = [c.get("pixelSize", 120) for c in d["columnMetadata"]]
    head_fmt = d["rowData"][0]["values"][0].get("userEnteredFormat", {})
    rules = tpl.get("conditionalFormats", [])
    for s in full:
        p = s["properties"]
        if p["title"] in SKIP or p["title"] == TEMPLATE or not p["title"].endswith("v2026"):
            continue
        sid, rows, cols = p["sheetId"], p["gridProperties"]["rowCount"], p["gridProperties"]["columnCount"]
        reqs = [{"deleteConditionalFormatRule": {"sheetId": sid, "index": i}}
                for i in range(len(s.get("conditionalFormats", [])) - 1, -1, -1)]
        for i, r in enumerate(rules):
            rule = {k: v for k, v in r.items() if k != "ranges"}
            rule["ranges"] = [{"sheetId": sid, "startRowIndex": 0, "endRowIndex": rows, "startColumnIndex": 0,
                               "endColumnIndex": max(10, cols)}]
            reqs.append({"addConditionalFormatRule": {"rule": rule, "index": i}})
        reqs += [
            {"repeatCell": {"range": {"sheetId": sid, "startRowIndex": 1, "endRowIndex": rows},
                            "cell": {"userEnteredFormat": {"textFormat": {"fontFamily": "Arial"}, "verticalAlignment": "TOP"}},
                            "fields": "userEnteredFormat.textFormat.fontFamily,userEnteredFormat.verticalAlignment"}},
            {"repeatCell": {"range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": 1},
                            "cell": {"userEnteredFormat": head_fmt}, "fields": "userEnteredFormat"}},
            {"updateSheetProperties": {"properties": {"sheetId": sid, "gridProperties": {"frozenRowCount": 1}},
                                       "fields": "gridProperties.frozenRowCount"}},
        ]
        for c in range(cols):
            reqs.append({"updateDimensionProperties": {
                "range": {"sheetId": sid, "dimension": "COLUMNS", "startIndex": c, "endIndex": c + 1},
                "properties": {"pixelSize": widths[c] if c < len(widths) else 200}, "fields": "pixelSize"}})
        requests.post(API + sh.id + ":batchUpdate", headers=sh._h(), json={"requests": reqs}, timeout=300).raise_for_status()
        print("서식:", p["title"], flush=True)
        time.sleep(1.2)


if __name__ == "__main__":
    main()
