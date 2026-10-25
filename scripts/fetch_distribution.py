"""종마다 나라별 기록 수를 GBIF에서 받아 data/distribution.json 에 둔다
→ {학명: {"key": GBIF키, "n": 전체, "c": {나라코드: 기록 수}, "iucn": IUCN 등급}}

- GBIF 학명 대조(species/match, 조강·파충강으로 좁힘)로 키를 찾고, 그 키(하위 아종 포함)의 출현 기록을
  나라별로 센다(occurrence/search facet=country). 조류는 eBird 관찰 자료가 GBIF에 들어가 있어 촘촘하다.
- 이미 받은 종은 건너뛴다(이어 받기). 이 PC 또는 GitHub Actions에서 돌린다.

    python scripts/fetch_distribution.py                 # 전부(이어 받기)
    python scripts/fetch_distribution.py --limit 50      # 시험
    python scripts/fetch_distribution.py --retry         # 못 찾은 종도 다시
    python scripts/fetch_distribution.py --wild          # 야생 출처(eBird·iNaturalist·표본)만 센 나라별 기록 w 채우기
"""
import json
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

DATA = Path(__file__).resolve().parent.parent / "data"
OUT = DATA / "distribution.json"
UA = {"User-Agent": "Vertapedia/0.1 (https://github.com/Tupandactyl/vertapedia)"}
# GBIF 분류 체계는 파충강을 따로 두지 않고 유린목·거북목·악어목·훼두목을 각각 강으로 다룬다
CLASS = {"AVES": {"Aves"}, "REPTILIA": {"Reptilia", "Squamata", "Testudines", "Crocodylia", "Sphenodontia", "Rhynchocephalia"}}


def get(url, params):
    url += "?" + urllib.parse.urlencode(params)
    for attempt in range(5):
        try:
            return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60))
        except Exception:
            time.sleep(5 * (attempt + 1))
    return None


def one(t):
    sci, grp = t["sci"], t["group"]
    m = get("https://api.gbif.org/v1/species/match", dict(name=sci, kingdom="Animalia", strict="true"))
    if not m or m.get("matchType") not in ("EXACT", "FUZZY") or m.get("class") not in CLASS[grp]:
        return sci, None
    key = m.get("acceptedUsageKey") or m.get("usageKey")
    d = get("https://api.gbif.org/v1/occurrence/search", dict(
        taxon_key=key, limit=0, facet="country", facetLimit=300, occurrence_status="present"))
    if d is None:
        return sci, None
    facets = (d.get("facets") or [{}])[0].get("counts", [])
    return sci, dict(key=key, n=d.get("count", 0), c={f["name"]: f["count"] for f in facets}, iucn=iucn(key))


EBIRD = "4fa7b334-ce0d-4e88-aaae-2e0c138d049e"   # eBird 관찰(야생만)
INAT = "50c9509d-22c7-4a22-a47d-8c48425ef4a7"    # iNaturalist 연구등급(사육·재배 제외)


def wild(key):
    """야생 출처만 나라별로: eBird·iNaturalist 관찰 + 박물관 표본. 다른 관찰 기록 사이트의 동물원 기록을 뺀다."""
    base = dict(taxon_key=key, limit=0, facet="country", facetLimit=300, occurrence_status="present")
    url = "https://api.gbif.org/v1/occurrence/search"
    obs = get_multi(url, base, [("dataset_key", EBIRD), ("dataset_key", INAT)])
    spec = get(url, dict(base, basis_of_record="PRESERVED_SPECIMEN"))
    if obs is None or spec is None:
        return None
    out = {}
    for d in (obs, spec):
        for f in (d.get("facets") or [{}])[0].get("counts", []):
            out[f["name"]] = out.get(f["name"], 0) + f["count"]
    return out


def get_multi(url, params, extra):
    """같은 이름의 매개변수를 여러 번(dataset_key=…&dataset_key=…) 보낸다"""
    q = urllib.parse.urlencode(list(params.items()) + extra)
    for attempt in range(5):
        try:
            return json.load(urllib.request.urlopen(urllib.request.Request(url + "?" + q, headers=UA), timeout=60))
        except Exception:
            time.sleep(5 * (attempt + 1))
    return None


def iucn(key):
    """GBIF 가 IUCN 적색목록에서 가져온 등급(LC·NT·VU·EN·CR·EW·EX·DD). 없으면 None"""
    r = get(f"https://api.gbif.org/v1/species/{key}/iucnRedListCategory", {})
    return (r or {}).get("code")


def main():
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    names = json.loads((DATA / "names.json").read_text(encoding="utf-8"))
    out = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    # 예전에 받은 기록에 IUCN 등급이 없으면 등급만 채운다
    old = [s for s, v in out.items() if v and "iucn" not in v]
    if old:
        with ThreadPoolExecutor(max_workers=4) as ex:
            for s, code in zip(old, ex.map(lambda s: iucn(out[s]["key"]), old)):
                out[s]["iucn"] = code
        print("IUCN 등급 채움:", len(old), flush=True)
    if "--wild" in sys.argv:  # 받아 둔 종마다 야생 출처 나라별 기록(w)을 채운다
        todo_w = [s for s, v in out.items() if v and "w" not in v]
        done = 0
        with ThreadPoolExecutor(max_workers=4) as ex:
            for s, w in zip(todo_w, ex.map(lambda s: wild(out[s]["key"]), todo_w)):
                if w is not None:
                    out[s]["w"] = w
                done += 1
                if done % 500 == 0:
                    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
                    print(f"야생 {done}/{len(todo_w)}", flush=True)
        OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print("야생 기록 채운 종:", done, flush=True)
        return
    retry = "--retry" in sys.argv  # 못 찾은 종(None)도 다시
    todo = [t for t in names if t["rank"] == "species" and (t["sci"] not in out or (retry and out[t["sci"]] is None))]
    # 국명 있는 종부터
    todo.sort(key=lambda t: (not t.get("name"), t["group"] != "AVES"))
    if limit:
        todo = todo[:limit]
    done = 0
    with ThreadPoolExecutor(max_workers=4) as ex:
        for sci, rec in ex.map(one, todo):
            out[sci] = rec
            done += 1
            if done % 200 == 0:
                OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
                print(f"분포 {done}/{len(todo)}", flush=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print("분포 받은 종:", done, "· 전체", len(out), "· 못 찾음", sum(1 for v in out.values() if not v))


if __name__ == "__main__":
    main()
