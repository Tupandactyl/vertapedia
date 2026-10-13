"""구글 시트 읽기·쓰기 (서비스 계정).

키: .secrets/sheets-key.json (저장소에 올리지 않는다) 또는 환경 변수 GOOGLE_SHEETS_KEY(키 JSON 내용, Actions용).
서비스 계정 이메일을 시트에 편집자로 공유해 두어야 한다.
"""
import json
import os
import urllib.parse
from pathlib import Path

import requests

try:  # 회사·기관망처럼 인증서를 중간에서 바꿔 끼우는 곳: 운영체제 인증서 저장소를 쓴다(검증은 그대로)
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass
from google.auth.transport.requests import Request
from google.oauth2 import service_account

ROOT = Path(__file__).resolve().parent.parent
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
API = "https://sheets.googleapis.com/v4/spreadsheets/"
SHEETS = {"birds": "1TPAgkLflsX0GjkcQdcRhrYSnJ7bvscmVESK5wyIVfxA",
          "reptiles": "1YC9IBMxBf1wBsbiXj7umJ6k0HD1eY3GsKCGGTxDlPD4"}


class Sheet:
    def __init__(self, which):
        raw = os.environ.get("GOOGLE_SHEETS_KEY")
        info = json.loads(raw) if raw else json.loads((ROOT / ".secrets" / "sheets-key.json").read_text(encoding="utf-8"))
        self.cred = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
        self.id = SHEETS.get(which, which)

    def _h(self):
        if not self.cred.valid:
            self.cred.refresh(Request())
        return {"Authorization": "Bearer " + self.cred.token}

    def meta(self):
        r = requests.get(API + self.id, headers=self._h(), params={"fields": "properties.title,sheets.properties"}, timeout=60)
        r.raise_for_status()
        return r.json()

    def values(self, tab):
        r = requests.get(API + self.id + "/values/" + urllib.parse.quote(f"'{tab}'"), headers=self._h(), timeout=120)
        r.raise_for_status()
        return r.json().get("values", [])

    def update(self, data):
        """data: [{"range": "'탭'!A1", "values": [[...]]}, ...] — 한 번에 쓴다."""
        r = requests.post(API + self.id + "/values:batchUpdate", headers=self._h(), timeout=300,
                          json={"valueInputOption": "RAW", "data": data})
        r.raise_for_status()
        return r.json()

    def append(self, tab, rows):
        r = requests.post(API + self.id + "/values/" + urllib.parse.quote(f"'{tab}'!A1") + ":append", headers=self._h(),
                          params={"valueInputOption": "RAW", "insertDataOption": "INSERT_ROWS"}, json={"values": rows}, timeout=300)
        r.raise_for_status()
        return r.json()


if __name__ == "__main__":
    for which in SHEETS:
        try:
            m = Sheet(which).meta()
            print(which, "읽기 OK:", m["properties"]["title"], "· 탭", len(m["sheets"]))
        except Exception as e:
            print(which, "실패:", e)
