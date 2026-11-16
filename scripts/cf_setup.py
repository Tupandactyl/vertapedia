"""vertapedia.org 연결과 의견(댓글) 서버 설정 — Cloudflare API.

필요: .secrets/cloudflare.json {"token": "...", "account_id": "..."} (저장소에 올리지 않는다)
만드는 것(이미 있으면 그대로 쓴다):
  - DNS: vertapedia.org → GitHub Pages(A·AAAA), www → tupandactyl.github.io (프록시 끔: GitHub가 인증서를 발급하도록)
  - D1 데이터베이스 vertapedia-comments + 표(workers/comments/schema.sql)
  - Turnstile(자동 등록 방지) 위젯
  - Worker vertapedia-comments + 주소 api.vertapedia.org
비밀값(IP 솔트, 동기화 토큰, Turnstile 비밀 키)은 .secrets/comments.json 에 둔다.

    python scripts/cf_setup.py dns          # 사이트 주소 연결
    python scripts/cf_setup.py comments     # 댓글 서버 만들기·고치기 (worker.js 바꾼 뒤에도 이것)
    python scripts/cf_setup.py comments --google <OAuth 클라이언트 ID>
"""
import json
import secrets
import sys
from pathlib import Path

import requests

try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

ROOT = Path(__file__).resolve().parent.parent
SEC = ROOT / ".secrets"
CF = json.loads((SEC / "cloudflare.json").read_text(encoding="utf-8"))
ACC = CF["account_id"]
API = "https://api.cloudflare.com/client/v4"
H = {"Authorization": "Bearer " + CF["token"]}
DOMAIN = "vertapedia.org"
WORKER = "vertapedia-comments"
DBNAME = "vertapedia-comments"
ORIGINS = ["https://vertapedia.org", "https://www.vertapedia.org", "https://tupandactyl.github.io"]


def cf(method, path, **kw):
    r = requests.request(method, API + path, headers={**H, **kw.pop("headers", {})}, timeout=120, **kw)
    j = r.json() if r.headers.get("content-type", "").startswith("application/json") else {"success": r.ok, "raw": r.text}
    if not j.get("success", r.ok):
        raise SystemExit(f"{method} {path} 실패: {json.dumps(j.get('errors', j), ensure_ascii=False)[:600]}")
    return j.get("result")


def zone_id():
    z = cf("GET", "/zones", params={"name": DOMAIN})
    if not z:
        raise SystemExit(f"{DOMAIN} 영역(zone)을 찾지 못했습니다. 토큰의 Zone 권한을 확인하세요.")
    return z[0]["id"]


def dns():
    zid = zone_id()
    have = cf("GET", f"/zones/{zid}/dns_records", params={"per_page": 200})
    want = [("A", DOMAIN, ip) for ip in ("185.199.108.153", "185.199.109.153", "185.199.110.153", "185.199.111.153")]
    want += [("AAAA", DOMAIN, ip) for ip in ("2606:50c0:8000::153", "2606:50c0:8001::153", "2606:50c0:8002::153", "2606:50c0:8003::153")]
    want += [("CNAME", "www." + DOMAIN, "tupandactyl.github.io")]
    for t, name, content in want:
        same = [r for r in have if r["type"] == t and r["name"] == name and r["content"].rstrip(".") == content]
        clash = [r for r in have if r["name"] == name and r["type"] in (("CNAME", "A", "AAAA") if t == "CNAME" else ("CNAME",))]
        for r in clash:
            print("지움:", r["type"], r["name"], r["content"])
            cf("DELETE", f"/zones/{zid}/dns_records/{r['id']}")
        if same:
            if same[0].get("proxied"):
                cf("PATCH", f"/zones/{zid}/dns_records/{same[0]['id']}", json={"proxied": False})
            print("있음:", t, name, content)
            continue
        cf("POST", f"/zones/{zid}/dns_records", json={"type": t, "name": name, "content": content, "proxied": False, "ttl": 1})
        print("만듦:", t, name, content)


def secrets_file():
    p = SEC / "comments.json"
    s = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    s.setdefault("ip_salt", secrets.token_hex(32))
    s.setdefault("sync_token", secrets.token_urlsafe(32))
    p.write_text(json.dumps(s, indent=1), encoding="utf-8")
    return s, p


def comments(google=None):
    s, p = secrets_file()
    if google:
        s["google_client_id"] = google
    zid = zone_id()
    # D1
    dbs = cf("GET", f"/accounts/{ACC}/d1/database", params={"name": DBNAME})
    db = next((d for d in dbs or [] if d["name"] == DBNAME), None) or cf("POST", f"/accounts/{ACC}/d1/database", json={"name": DBNAME})
    dbid = db["uuid"]
    schema = (ROOT / "workers" / "comments" / "schema.sql").read_text(encoding="utf-8")
    cf("POST", f"/accounts/{ACC}/d1/database/{dbid}/query", json={"sql": schema})
    print("D1:", DBNAME)
    # Turnstile
    if not s.get("turnstile_secret"):
        ws = cf("GET", f"/accounts/{ACC}/challenges/widgets") or []
        w = next((x for x in ws if x["name"] == "Vertapedia 의견"), None)
        if w:
            w = cf("GET", f"/accounts/{ACC}/challenges/widgets/{w['sitekey']}")
        else:
            w = cf("POST", f"/accounts/{ACC}/challenges/widgets",
                   json={"name": "Vertapedia 의견", "domains": [DOMAIN, "www." + DOMAIN], "mode": "managed"})
        s["turnstile_sitekey"], s["turnstile_secret"] = w["sitekey"], w["secret"]
    print("Turnstile 사이트 키:", s["turnstile_sitekey"])
    p.write_text(json.dumps(s, indent=1), encoding="utf-8")
    # Worker
    meta = {
        "main_module": "worker.js",
        "compatibility_date": "2025-01-01",
        "bindings": [
            {"type": "d1", "name": "DB", "id": dbid},
            {"type": "plain_text", "name": "ORIGINS", "text": ",".join(ORIGINS)},
            {"type": "plain_text", "name": "GOOGLE_CLIENT_ID", "text": s.get("google_client_id", "")},
            {"type": "secret_text", "name": "IP_SALT", "text": s["ip_salt"]},
            {"type": "secret_text", "name": "SYNC_TOKEN", "text": s["sync_token"]},
            {"type": "secret_text", "name": "TURNSTILE_SECRET", "text": s["turnstile_secret"]},
        ],
    }
    code = (ROOT / "workers" / "comments" / "worker.js").read_bytes()
    cf("PUT", f"/accounts/{ACC}/workers/scripts/{WORKER}", files={
        "metadata": (None, json.dumps(meta), "application/json"),
        "worker.js": ("worker.js", code, "application/javascript+module"),
    })
    print("Worker:", WORKER)
    cf("PUT", f"/accounts/{ACC}/workers/domains",
       json={"hostname": "api." + DOMAIN, "service": WORKER, "zone_id": zid, "environment": "production"})
    print("주소: https://api." + DOMAIN)
    print("사이트 설정값 → site/comments.js: turnstile =", s["turnstile_sitekey"], "· google =", s.get("google_client_id", "(아직 없음)"))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "dns":
        dns()
    elif cmd == "comments":
        g = sys.argv[sys.argv.index("--google") + 1] if "--google" in sys.argv else None
        comments(g)
    else:
        print(__doc__)
