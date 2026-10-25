"""분포 지도용 세계지도(data/world.geojson)와 GBIF 행정구역 → 지역 표(data/gadm_regions.json)를 만든다.

- 기본: Natural Earth 50m 나라 경계. 나라마다 코드(두 글자)를 붙인다.
- 생물지리적으로 크게 갈리는 나라는 Natural Earth 10m 행정구역(1단계)을 지역으로 묶어 따로 그린다
  (하와이·알래스카, 파푸아·월리시아, 카나리아, 아조레스·마데이라, 갈라파고스, 오키나와, 러시아 아시아 쪽,
   중국 동북·서부, 태즈메이니아, 안다만·니코바르)
- 본국과 한 덩어리로 그려지는 해외 영토(프랑스령 기아나·레위니옹 등, 스발바르, 네덜란드령 카리브)는 떼어 내
  GBIF 와 같은 나라 코드를 붙인다.
- GBIF 기록의 행정구역(GADM 1단계) 코드를 같은 규칙으로 지역 코드에 잇는다.

Natural Earth 원본(셰이프 파일)은 저장소에 올리지 않는다:
    python scripts/build_world_map.py <ne_50m_admin_0_countries 폴더> <ne_10m_admin_1_states_provinces 폴더>
"""
import difflib
import json
import sys
import unicodedata
import urllib.request
from pathlib import Path

import shapefile
from shapely.geometry import mapping, shape
from shapely.ops import unary_union

try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

DATA = Path(__file__).resolve().parent.parent / "data"
TOL = 0.08  # 단순화(도)

SPLIT = {"USA": "US", "IDN": "ID", "ESP": "ES", "PRT": "PT", "ECU": "EC", "JPN": "JP", "RUS": "RU", "CHN": "CN",
         "AUS": "AU", "IND": "IN"}
# 해외 영토: (코드, 서경·동경 최소, 최대, 위도 최소, 최대)
OVERSEAS = {"FRA": [("GF", -55, -51, 1, 6.5), ("GP", -62, -60.9, 15.8, 16.6), ("MQ", -61.3, -60.7, 14.3, 15),
                    ("RE", 55, 56, -21.5, -20.7), ("YT", 44.9, 45.4, -13.1, -12.5)],
            "NOR": [("SJ", -10, 40, 74, 82)],
            "NLD": [("BQ", -69, -62, 11.5, 18.5)]}
NAMES = {"US": "United States", "US-HI": "Hawaii", "US-AK": "Alaska", "ID": "Indonesia", "ID-PAP": "Papua (Indonesia)",
         "ID-WAL": "Wallacea (Sulawesi, Maluku, Nusa Tenggara)", "ES": "Spain", "ES-CN": "Canary Islands", "PT": "Portugal",
         "PT-AC": "Azores", "PT-MA": "Madeira", "EC": "Ecuador", "EC-GAL": "Galápagos", "JP": "Japan", "JP-OKI": "Okinawa",
         "RU": "Russia (Europe)", "RU-AS": "Russia (Asia)", "CN": "China", "CN-NE": "Northeast China", "CN-W": "Western China",
         "AU": "Australia", "AU-TAS": "Tasmania", "IN": "India", "IN-AN": "Andaman and Nicobar Islands"}


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return "".join(ch for ch in s if ch.isalnum())


def region(iso3, name, lon=None, lat=None):
    """행정구역 이름(·중심점) → 지역 코드"""
    base, n = SPLIT[iso3], norm(name)
    if iso3 == "USA":
        return "US-HI" if n == "hawaii" else "US-AK" if n == "alaska" else base
    if iso3 == "IDN":
        if "papua" in n:
            return "ID-PAP"
        if any(k in n for k in ("sulawesi", "gorontalo", "maluku", "nusatenggara")):
            return "ID-WAL"
        return base
    if iso3 == "ESP":
        return "ES-CN" if "canari" in n or (lat is not None and lat < 30) else base
    if iso3 == "PRT":
        if "azore" in n or "acore" in n or (lon is not None and lon < -22):
            return "PT-AC"
        if "madeira" in n or (lat is not None and lat < 34 and lon is not None and lon < -15):
            return "PT-MA"
        return base
    if iso3 == "ECU":
        return "EC-GAL" if "galapagos" in n or (lon is not None and lon < -85) else base
    if iso3 == "JPN":
        return "JP-OKI" if "okinawa" in n else base
    if iso3 == "CHN":
        if any(k in n for k in ("heilongjiang", "jilin", "liaoning", "neimongol", "innermongol")):
            return "CN-NE"
        if any(k in n for k in ("xinjiang", "xizang", "tibet", "qinghai", "gansu", "ningxia")):
            return "CN-W"
        return base
    if iso3 == "AUS":
        return "AU-TAS" if "tasmania" in n else base
    if iso3 == "IND":
        return "IN-AN" if "andaman" in n else base
    if iso3 == "RUS":
        asia = ("chukot", "zabaykal", "chita", "agabury", "altay", "amur", "buryat", "irkutsk", "kamchat", "kemerovo",
                "khabarov", "khakas", "khantymans", "krasnoyar", "kurgan", "magadan", "novosibir", "omsk", "primor",
                "sakha", "sakhalin", "sverdlov", "tomsk", "tuva", "tyumen", "yamal", "yevrey", "jewish", "chelyabin")
        if any(k in n for k in asia):
            return "RU-AS"
        return "RU-AS" if lon is not None and (lon >= 60 or lon < -160) else base
    return base


def main(adm0_dir, adm1_dir):
    feats = {}

    def add(code, geom, name):
        g = geom.simplify(TOL, preserve_topology=True)
        if g.is_empty:
            return
        if code in feats:
            feats[code]["geom"] = unary_union([feats[code]["geom"], g])
        else:
            feats[code] = dict(geom=g, name=name)

    r0 = shapefile.Reader(str(next(Path(adm0_dir).glob("*.shp"))), encoding="utf-8")
    f0 = [f[0] for f in r0.fields[1:]]
    for sr in r0.iterShapeRecords():
        rec = dict(zip(f0, sr.record))
        a3, code = rec["ADM0_A3"], rec.get("ISO_A2_EH") or rec.get("ISO_A2")
        if a3 in SPLIT:
            continue
        geom = shape(sr.shape.__geo_interface__)
        if code in (None, "", "-99"):
            code = "X-" + a3
        parts = list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]
        for p in parts:
            c = code
            for oc, x0, x1, y0, y1 in OVERSEAS.get(a3, []):
                cx, cy = p.centroid.x, p.centroid.y
                if x0 <= cx <= x1 and y0 <= cy <= y1:
                    c = oc
            add(c, p, rec["NAME"])

    r1 = shapefile.Reader(str(next(Path(adm1_dir).glob("*.shp"))), encoding="utf-8")
    f1 = [f[0] for f in r1.fields[1:]]
    ne_names = {}
    for sr in r1.iterShapeRecords():
        rec = dict(zip(f1, sr.record))
        a3 = rec.get("adm0_a3")
        if a3 not in SPLIT:
            continue
        geom = shape(sr.shape.__geo_interface__)
        c = geom.representative_point()
        code = region(a3, rec.get("name") or rec.get("name_en") or "", c.x, c.y)
        add(code, geom, NAMES.get(code, code))
        ne_names.setdefault(a3, []).append((norm(rec.get("name") or ""), code))

    out = {"type": "FeatureCollection", "features": []}
    for code, f in sorted(feats.items()):
        gj = mapping(f["geom"])
        gj = json.loads(json.dumps(gj), parse_float=lambda x: round(float(x), 1))
        out["features"].append({"type": "Feature", "properties": {"c": code, "n": f["name"]}, "geometry": gj})
    (DATA / "world.geojson").write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    print("지도 지역", len(out["features"]), "·", round((DATA / "world.geojson").stat().st_size / 1024), "KB")

    # GBIF 행정구역(GADM) → 지역 코드. 러시아는 이름이 Natural Earth 와 달라 비슷한 이름의 지역을 따른다
    gadm = {}
    UA = {"User-Agent": "Vertapedia/0.1 (https://github.com/Tupandactyl/vertapedia)"}
    for a3 in SPLIT:
        subs = json.load(urllib.request.urlopen(urllib.request.Request(
            f"https://api.gbif.org/v1/geocode/gadm/{a3}/subdivisions", headers=UA), timeout=60))
        for s in subs:
            name = s["name"]
            code = region(a3, name)
            if a3 == "RUS" and code == SPLIT[a3]:  # 이름 목록에 없으면 비슷한 이름의 Natural Earth 지역을 따른다
                cand = {n: c for n, c in ne_names.get(a3, [])}
                near = difflib.get_close_matches(norm(name), list(cand), 1, 0.6)
                code = cand[near[0]] if near else SPLIT[a3]
            gadm[s["id"]] = code
    (DATA / "gadm_regions.json").write_text(json.dumps(gadm, ensure_ascii=False, indent=0, sort_keys=True), encoding="utf-8")
    from collections import Counter
    print("행정구역 → 지역", len(gadm), Counter(gadm.values()))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
