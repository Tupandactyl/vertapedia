"""종마다 iNaturalist 사진·영문 위키백과 본문을 받아 data/media/<학명>.json 에 둔다.

- 사진은 재사용 가능한 라이선스(CC0, CC BY, CC BY-SA, CC BY-NC, CC BY-NC-SA)만 받는다.
- iNaturalist 권고에 맞춰 1초에 한 번 이하로 부른다.
- 이미 받은 종은 --max-age 일이 지나기 전에는 다시 받지 않는다.

    python scripts/fetch_media.py                 # 국명이 있는 한국 출현종
    python scripts/fetch_media.py --limit 200     # 이번에 새로 받을 최대 종 수
"""
import argparse
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = DATA / "media"
UA = {"User-Agent": "Vertapedia/0.1 (https://github.com/Tupandactyl/vertapedia)"}
LICENSES = "cc0,cc-by,cc-by-sa,cc-by-nc,cc-by-nc-sa"
PER_SPECIES = 8

_last = [0.0]


def get(url, params=None):
    if params:
        url += "?" + urllib.parse.urlencode(params)
    wait = 1.05 - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    for attempt in range(4):
        _last[0] = time.time()
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if e.code in (429, 500, 502, 503) and attempt < 3:
                time.sleep(10 * (attempt + 1))
                continue
            raise
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
            if attempt < 3:  # 연결이 끊기면 잠깐 쉬고 다시
                time.sleep(15 * (attempt + 1))
                continue
            raise


def inat_taxon(sci):
    d = get("https://api.inaturalist.org/v1/taxa", dict(q=sci, is_active="true", per_page=10))
    for t in (d or {}).get("results", []):
        if t["name"] == sci:
            return t
    for t in (d or {}).get("results", []):  # 학명이 이명으로만 걸린 경우
        if sci in (t.get("matched_term") or "") and t["rank"] in ("species", "subspecies"):
            return t
    return None


def inat_photos(taxon_id):
    d = get("https://api.inaturalist.org/v1/observations", dict(
        taxon_id=taxon_id, quality_grade="research", photos="true", photo_license=LICENSES,
        order_by="votes", per_page=PER_SPECIES * 2))
    out, seen_users = [], {}
    for o in (d or {}).get("results", []):
        for p in o.get("photos", [])[:1]:
            if not p.get("license_code"):
                continue
            user = (o.get("user") or {}).get("login")
            if seen_users.get(user, 0) >= 2:  # 한 사람 사진이 갤러리를 채우지 않게
                continue
            seen_users[user] = seen_users.get(user, 0) + 1
            out.append(dict(url=p["url"].replace("/square.", "/{size}."), license=p["license_code"],
                            attribution=p.get("attribution"), obs=o["id"], place=o.get("place_guess"),
                            date=o.get("observed_on")))
        if len(out) >= PER_SPECIES:
            break
    return out


SKIP_SECTIONS = {"references", "external links", "see also", "further reading", "notes", "sources",
                 "bibliography", "gallery", "footnotes", "citations", "cited sources", "works cited"}


def wiki_full(url):
    """영문 위키백과 본문 전체(일반 텍스트)를 절 단위로 받는다. 참고문헌·바깥 링크 절은 뺀다."""
    if not url:
        return None
    title = urllib.parse.unquote(url.rsplit("/wiki/", 1)[-1]).replace("_", " ")
    d = get("https://en.wikipedia.org/w/api.php", dict(
        action="query", prop="extracts|info|pageprops", explaintext=1, exsectionformat="wiki",
        redirects=1, titles=title, format="json", formatversion=2))
    pages = (d or {}).get("query", {}).get("pages", [])
    if not pages or pages[0].get("missing") or "disambiguation" in pages[0].get("pageprops", {}):
        return None
    pg = pages[0]
    text = pg.get("extract") or ""
    sections, cur = [], dict(h=None, level=1, text=[])
    for line in text.splitlines():
        m = re.match(r"^(={2,5})\s*(.*?)\s*\1$", line.strip())
        if m:
            sections.append(cur)
            cur = dict(h=m.group(2), level=len(m.group(1)), text=[])
        else:
            cur["text"].append(line)
    sections.append(cur)
    out, skip_level = [], None
    for sec in sections:
        if skip_level is not None and sec["level"] > skip_level:
            continue
        skip_level = None
        if sec["h"] and sec["h"].strip().lower() in SKIP_SECTIONS:
            skip_level = sec["level"]
            continue
        paras = [p.strip() for p in sec["text"] if p.strip()]
        if paras or sec["h"]:
            out.append(dict(h=sec["h"], level=sec["level"], paras=paras))
    out = [s for i, s in enumerate(out) if s["paras"] or (i + 1 < len(out) and out[i + 1]["level"] > s["level"])]
    return dict(title=pg["title"], url="https://en.wikipedia.org/wiki/" + urllib.parse.quote(pg["title"].replace(" ", "_")),
                revision=pg.get("lastrevid"), sections=out)


def targets(include_all=False):
    names = json.loads((DATA / "names.json").read_text(encoding="utf-8"))
    sp = [t for t in names if t["rank"] == "species"]
    korean = [t for t in sp if t["status"] in ("kos", "official")]
    rest = [t for t in sp if t not in korean and t.get("name")] if include_all else []
    return korean + rest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=10_000)
    ap.add_argument("--max-age", type=int, default=60, help="이보다 오래된 자료만 다시 받는다(일)")
    ap.add_argument("--all-named", action="store_true", help="국명이 있는 모든 종까지")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    cutoff = (date.today() - timedelta(days=a.max_age)).isoformat()
    done = 0
    for t in targets(a.all_named):
        f = OUT / (t["sci"].replace(" ", "_") + ".json")
        old = json.loads(f.read_text(encoding="utf-8")) if f.exists() else None
        if old and old.get("fetched", "") >= cutoff:
            # 예전 형식(요약만 있음)이면 위키백과 본문만 새로 받는다
            if old.get("inat") and (old.get("wiki") or {}).get("sections") is None and old["inat"].get("wikipedia_url"):
                if done >= a.limit:
                    break
                old["wiki"] = wiki_full(old["inat"]["wikipedia_url"])
                f.write_text(json.dumps(old, ensure_ascii=False, indent=1), encoding="utf-8")
                done += 1
                print(f"{done:4} {t['sci']:34} 위키 본문 {'O' if old['wiki'] else '-'}", flush=True)
            continue
        if done >= a.limit:
            break
        tx = inat_taxon(t["sci"])
        rec = dict(sci=t["sci"], fetched=date.today().isoformat(), inat=None, photos=[], wiki=None)
        if tx:
            rec["inat"] = dict(id=tx["id"], name=tx["name"], observations=tx.get("observations_count"),
                               wikipedia_url=tx.get("wikipedia_url"))
            rec["photos"] = inat_photos(tx["id"])
            rec["wiki"] = wiki_full(tx.get("wikipedia_url"))
        f.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
        done += 1
        print(f"{done:4} {t['sci']:34} 사진 {len(rec['photos'])} 위키 {'O' if rec['wiki'] else '-'}", flush=True)
    print("새로 받은 종:", done)


if __name__ == "__main__":
    main()
