"""iNaturalist 의 나라별 토착/도입 표시(listed taxa, establishment means)를 받아 data/establishment.json 에 둔다
→ {학명: {"introduced": [나라코드], "native": [나라코드]}}

지도에서는 '서식국으로 잡힌 나라(기록이 충분)' 가운데 iNaturalist 가 도입(introduced)으로 표시한 곳만
도입 정착지 색으로 칠한다. iNaturalist 도입 표시에는 탈출 개체만 기록된 나라도 있으므로 단독으로는 쓰지 않는다.
원래 서식권과 떨어진 서식국인데 목록(100개에서 잘림)에 표시가 없으면, 그 나라의 '도입' 표시 관찰이 있는지
나라별로 한 번 더 묻는다. iNaturalist 권고(1초에 한 번 이하)를 지킨다. 이미 받은 종은 건너뛴다.

    python scripts/fetch_establishment.py
"""
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

import pycountry

import distrule

try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

DATA = Path(__file__).resolve().parent.parent / "data"
OUT = DATA / "establishment.json"
UA = {"User-Agent": "Vertapedia/0.1 (https://github.com/Tupandactyl/vertapedia)"}
FIX = {"Hong Kong": "HK", "Taiwan": "TW", "Macau": "MO", "Kosovo": "XK", "Saint-Barthélemy": "BL", "Russia": "RU",
       "South Korea": "KR", "North Korea": "KP", "Laos": "LA", "Vietnam": "VN", "Iran": "IR", "Syria": "SY",
       "Bolivia": "BO", "Venezuela": "VE", "Tanzania": "TZ", "Moldova": "MD", "Brunei": "BN", "Czech Republic": "CZ",
       "Democratic Republic of the Congo": "CD", "Republic of the Congo": "CG", "Ivory Coast": "CI", "Côte d'Ivoire": "CI",
       "Micronesia": "FM", "Palestine": "PS", "Cape Verde": "CV", "East Timor": "TL", "Swaziland": "SZ", "Turkey": "TR"}
_iso = {}


def iso2(name):
    if name in FIX:
        return FIX[name]
    if name not in _iso:
        try:
            _iso[name] = pycountry.countries.lookup(name).alpha_2
        except LookupError:
            try:
                _iso[name] = pycountry.countries.search_fuzzy(name)[0].alpha_2
            except LookupError:
                _iso[name] = None
    return _iso[name]


def get(url):
    for attempt in range(5):
        try:
            return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60))
        except Exception:
            time.sleep(10 * (attempt + 1))
    return None


PLACES = DATA / "inat_places.json"  # 나라코드 → iNaturalist 나라 place id


def place_id(code, cache):
    if code in cache:
        return cache[code]
    common = {v: k for k, v in FIX.items()}  # KR → South Korea 등 흔히 쓰는 이름 먼저
    c = pycountry.countries.get(alpha_2=code)
    names = [n for n in (common.get(code), getattr(c, "common_name", None), getattr(c, "name", None)) if n]
    pid = None
    for name in names:
        r = get("https://api.inaturalist.org/v1/places/autocomplete?" + urllib.parse.urlencode({"q": name}))
        pid = next((p["id"] for p in (r or {}).get("results", []) if p.get("admin_level") == 0), None)
        time.sleep(1.05)
        if pid:
            break
    cache[code] = pid
    return pid


def main():
    dist = json.loads((DATA / "distribution.json").read_text(encoding="utf-8"))
    geo = json.loads((DATA / "geo.json").read_text(encoding="utf-8"))
    places = json.loads(PLACES.read_text(encoding="utf-8")) if PLACES.exists() else {}
    out = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    todo = []
    for f in sorted((DATA / "media").glob("*.json")):
        m = json.loads(f.read_text(encoding="utf-8"))
        d = dist.get(m["sci"]) or {}
        c = d.get("w") or d.get("c") or {}
        if m.get("inat") and m["sci"] not in out and len([k for k in c if k != "ZZ"]) >= 2:
            todo.append((m["sci"], m["inat"]["id"]))
    print("받을 종:", len(todo), flush=True)
    last = 0.0
    for n, (sci, tid) in enumerate(todo, 1):
        wait = 1.05 - (time.time() - last)
        if wait > 0:
            time.sleep(wait)
        last = time.time()
        r = get(f"https://api.inaturalist.org/v1/taxa/{tid}")
        lt = ((r or {}).get("results") or [{}])[0].get("listed_taxa") or []
        rec = {"introduced": set(), "native": set()}
        for x in lt:
            p = x.get("place") or {}
            if p.get("admin_level") != 0:
                continue
            em = (x.get("establishment_means") or "").lower()
            k = iso2(p.get("name", ""))
            if k and em in ("introduced", "naturalised", "invasive", "managed"):
                rec["introduced"].add(k)
            elif k and em in ("native", "endemic"):
                rec["native"].add(k)
        # 원래 서식권과 떨어진 서식국인데 표시가 없으면(목록이 100개에서 잘림) 그 나라에 도입 표시 관찰이 있는지 묻는다
        c = distrule.counts(dist.get(sci))
        major = distrule.habitat(c, geo)
        home = distrule.home_range(major, c, rec["introduced"], rec["native"], geo) if major else set()
        for k in sorted(major - home - rec["introduced"] - rec["native"]):
            pid = place_id(k, places)
            if not pid:
                continue
            time.sleep(1.05)
            q = get("https://api.inaturalist.org/v1/observations?" + urllib.parse.urlencode(
                dict(taxon_id=tid, place_id=pid, introduced="true", per_page=0)))
            if (q or {}).get("total_results", 0) > 0:
                rec["introduced"].add(k)
        out[sci] = {k: sorted(v) for k, v in rec.items()}
        if n % 200 == 0:
            OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            PLACES.write_text(json.dumps(places, ensure_ascii=False), encoding="utf-8")
            print(f"토착·도입 {n}/{len(todo)}", flush=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    PLACES.write_text(json.dumps(places, ensure_ascii=False), encoding="utf-8")
    print("토착·도입 받은 종:", len(todo), flush=True)


if __name__ == "__main__":
    main()
