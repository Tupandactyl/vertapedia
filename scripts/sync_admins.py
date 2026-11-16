"""의견창 관리자 목록 동기화: 편집진 시트(조류·파충류)의 편집자·소유자 메일 → 댓글 서버.

메일 원문은 보내지 않고 SHA-256 해시만 보낸다(서버는 로그인한 구글 메일의 해시와 맞춘다).
필요: 서비스 계정(.secrets/sheets-key.json 또는 GOOGLE_SHEETS_KEY), 구글 클라우드 프로젝트에서 Drive API 사용 설정,
      동기화 토큰(COMMENTS_SYNC_TOKEN 또는 .secrets/comments.json 의 sync_token).

    python scripts/sync_admins.py
"""
import hashlib
import json
import os
import sys
from pathlib import Path

import requests

try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass
from google.auth.transport.requests import Request
from google.oauth2 import service_account

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from sheets_api import SHEETS  # noqa: E402

API = os.environ.get("COMMENTS_API", "https://api.vertapedia.org")


def main():
    if os.environ.get("GITHUB_ACTIONS") and not (os.environ.get("COMMENTS_SYNC_TOKEN") and os.environ.get("GOOGLE_SHEETS_KEY")):
        print("비밀값(COMMENTS_SYNC_TOKEN·GOOGLE_SHEETS_KEY)이 없어 건너뜀")
        return
    raw = os.environ.get("GOOGLE_SHEETS_KEY")
    info = json.loads(raw) if raw else json.loads((ROOT / ".secrets" / "sheets-key.json").read_text(encoding="utf-8"))
    cred = service_account.Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/drive.metadata.readonly"])
    cred.refresh(Request())
    emails = set()
    for which, fid in SHEETS.items():
        r = requests.get(f"https://www.googleapis.com/drive/v3/files/{fid}/permissions", timeout=60,
                         params={"fields": "permissions(role,type,emailAddress)", "supportsAllDrives": "true"},
                         headers={"Authorization": "Bearer " + cred.token})
        r.raise_for_status()
        got = {p["emailAddress"].lower() for p in r.json().get("permissions", [])
               if p.get("type") == "user" and p.get("role") in ("owner", "organizer", "fileOrganizer", "writer") and p.get("emailAddress")}
        got = {e for e in got if not e.endswith(".iam.gserviceaccount.com")}
        print(which, "편집자", len(got), "명")
        emails |= got
    if not emails:
        raise SystemExit("편집자 메일을 하나도 받지 못했습니다")
    tok = os.environ.get("COMMENTS_SYNC_TOKEN")
    if not tok:
        tok = json.loads((ROOT / ".secrets" / "comments.json").read_text(encoding="utf-8"))["sync_token"]
    hashes = sorted(hashlib.sha256(e.encode()).hexdigest() for e in emails)
    r = requests.post(API + "/admins", json={"hashes": hashes}, headers={"Authorization": "Bearer " + tok}, timeout=60)
    print("댓글 서버:", r.status_code, r.text[:200])
    r.raise_for_status()


if __name__ == "__main__":
    main()
