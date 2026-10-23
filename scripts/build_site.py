"""data/names.json·data/media 에서 사이트 자료를 만든다.

- site/data/names.min.json : 검색용 가벼운 목록
- site/data/tree.json      : 목 > (아목) > (상과) > 과 > (아과) > 속 > 종 분류군 (시트 순서)
- site/data/random.json    : 첫 화면에서 고를 종 (국명과 사진이 있는 종)
- site/sp/<학명>.json      : 종 문서 (시트 기준 이전·다음 종 포함)
- site/fam/<학명>.json     : 과 문서 — 명칭 근거와 포함 속·종 목록
- site/{index,find,sp,fam}.html
"""
import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ko_link import Linker

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SITE = ROOT / "site"


def load(name, default=None):
    f = DATA / name
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else default


names = load("names.json")
dist = load("distribution.json", {})
bird_iucn = load("bird_iucn.json", {})  # 조류 IUCN 등급(AviList v2026). 파충류는 distribution.json 의 GBIF 값  # GBIF 나라별 기록 수 (scripts/fetch_distribution.py)


def dist_of(sci):
    """주요 기록국(전체의 0.2% 이상·3건 이상)과 드문 기록국. ZZ(나라 모름)는 뺀다."""
    d = dist.get(sci)
    if not d or not d.get("c"):
        return None
    c = {k: v for k, v in d["c"].items() if k != "ZZ"}
    tot = sum(c.values()) or 1
    major = sorted(k for k, v in c.items() if v >= 3 and v / tot >= 0.002)
    rare = sorted(k for k in c if k not in major)
    return dict(m=major, r=rare, n=tot, key=d.get("key"))


ebird = load("ebird_codes.json", {})
ebird.update(load("bird_codes.json", {}))  # AviList v2026 의 eBird 종 코드가 먼저
ebird_ord = load("ebird_families.json", {})
media = {}
for f in (DATA / "media").glob("*.json"):
    m = json.loads(f.read_text(encoding="utf-8"))
    media[m["sci"]] = m
# 파충류는 시트에 영명이 없으면 iNaturalist 영명을 쓴다
for t in names:
    if t["group"] == "REPTILIA" and t["rank"] == "species" and not t.get("en"):
        t["en"] = ((media.get(t["sci"]) or {}).get("inat") or {}).get("common")
G = {"AVES": "A", "REPTILIA": "R"}
NOFAM = "(과 미정)"


def first_by(*ranks):
    out = {}
    for t in names:
        if t["rank"] in ranks:
            out.setdefault((t["group"], t["sci"]), t)
    return out


orders, families, genera = first_by("order", "suborder"), first_by("family"), first_by("genus")
subfams = first_by("subfamily")
# 참새목 아목·상과 (data/bird_higher.json). 국명은 모식과 국명의 '과'를 '아목'·'상과'로 바꿔 만든다.
BH = load("bird_higher.json", {})
bird_auth = load("bird_authority.json", {})  # 조류 명명자·연도 (AviList v2025, scripts/fetch_avilist.py)
_ranks = {}
for _f, (_so, _sp) in BH.get("family", {}).items():
    _ranks[_so] = "suborder"
    if _sp:
        _ranks[_sp] = "superfamily"
for _sci, _rk in _ranks.items():
    _tf = families.get(("AVES", BH.get("type_family", {}).get(_sci)), {})
    _ko = BH.get("names", {}).get(_sci)
    if not _ko and (_tf.get("name") or "").endswith("과"):
        _ko = _tf["name"][:-1] + ("아목" if _rk == "suborder" else "상과")
    orders.setdefault(("AVES", _sci), dict(group="AVES", rank=_rk, sci=_sci, name=_ko,
                                         status="derived" if _ko and _sci not in BH.get("names", {}) else ("consensus" if _ko else "none")))
# 파충류 속 → 아과 (Reptile Database 종 문서의 Higher Taxa, scripts/fetch_rdb.py --subfamilies)
sub_of = {("REPTILIA", g): sf for g, sf in load("rdb_subfamily.json", {}).items() if sf}
# 한 과의 모든 속이 같은 아과 하나뿐이면 과와 겹치는 단계라 뺀다
# (시트는 보아과를 여러 과로 나누는데 Reptile Database는 그들을 Boidae의 아과로 둔다: Erycidae → Erycinae 등)
_fam_of_genus = {}
for t in names:
    if t["group"] == "REPTILIA" and t["rank"] == "species":
        _fam_of_genus.setdefault(t["sci"].split()[0], t.get("family"))
_subs_in_fam = {}
for g, f in _fam_of_genus.items():
    _subs_in_fam.setdefault(f, set()).add(sub_of.get(("REPTILIA", g)))
for g, f in _fam_of_genus.items():
    if len(_subs_in_fam[f]) == 1:
        sub_of.pop(("REPTILIA", g), None)
subfamilies = [t for t in names if t["rank"] == "subfamily"]
species = [t for t in names if t["rank"] == "species"]
linker = Linker(names)


def pics(m):
    """대표 사진(iNaturalist 큐레이터 선정) 하나를 맨 앞에, 그 뒤로 관찰 사진. 같은 사진은 한 번만."""
    cover = [dict(c, cover=1) for c in (m.get("curated") or [])[:1]]
    pid = lambda p: p["url"].split("/photos/")[-1].split("/")[0]
    seen = {pid(c) for c in cover}
    return cover + [p for p in m.get("photos", []) if pid(p) not in seen]


has_pic = lambda sci: bool(media.get(sci, {}).get("photos") or media.get(sci, {}).get("curated"))
# 속 → 모식종: 파충류는 Reptile Database 표시, 조류(와 표시 없는 파충류 속)는 data/type_species.json (AviList 등)
type_of = {(t["group"], t["sci"].split()[0]): t["sci"] for t in names if t["rank"] == "species" and t.get("type_species")}
_sp_group = {t["sci"]: t["group"] for t in names if t["rank"] == "species"}
for gname, tsci in load("type_species.json", {}).items():
    if tsci and not gname.startswith("_") and tsci in _sp_group:
        type_of.setdefault((_sp_group[tsci], gname), tsci)


def wiki_of(t, m):
    """위키 문서가 종이 아니라 속 문서이면 표시해 둔다(iNaturalist가 속 문서를 걸어 둔 경우)."""
    w = linker.wiki(m.get("wiki"))
    if w and len(w.get("title", "").split()) == 1:
        w = dict(w, genus_doc=True)
    return w
dump = lambda obj: json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
fname = lambda sci: sci.replace(" ", "_") + ".json"


def short(t):
    return dict(sci=t["sci"], name=t.get("name"), status=t["status"]) if t else None


def lineage(t):
    """(목, 아목, 상과) — 과 행에 적힌 것, 없으면 eBird 과 → 목, 분류미정 탭이면 그 탭의 목·아목.
    조류 참새목은 data/bird_higher.json 의 아목·상과."""
    fam = families.get((t["group"], t.get("family"))) or {}
    o = fam.get("order") or t.get("order_hint") or (ebird_ord.get(t.get("family")) if t["group"] == "AVES" else None)
    so = fam.get("suborder") or t.get("suborder_hint")
    sp = None
    if t["group"] == "AVES" and t.get("family") in BH.get("family", {}):
        so, sp = BH["family"][t["family"]]
    return o, so, sp


def taxon(rank_map, g, sci):
    x = rank_map.get((g, sci))
    return short(x) if x else ({"sci": sci} if sci else None)


# --- 분류군: 내부 마디 [계급, 학명, 국명, 자식들], 종 [학명, 국명, 영명, 사진] ---
tree = {}
for t in species:
    g = t["group"]
    o, so, sup = lineage(t)
    sf = sub_of.get((g, t["sci"].split()[0]))
    path = [("o", o or "(목 미정)")] + ([("u", so)] if so else []) + ([("p", sup)] if sup else []) +         [("f", t.get("family") or NOFAM)] +         ([("s", sf)] if sf else []) + [("g", t["sci"].split()[0])]
    node = tree.setdefault(g, {})
    for key in path:
        node = node.setdefault(key, {})
    node.setdefault("_sp", []).append(t)


def emit(g, d):
    out = []
    for key, child in d.items():
        if key == "_sp":
            continue
        rank, sci = key
        src = {"o": orders, "u": orders, "p": orders, "f": families, "s": subfams, "g": genera}[rank]
        x = src.get((g, sci))
        kids = [[s["sci"], s.get("name"), s.get("en"), 1 if has_pic(s["sci"]) else 0] for s in child["_sp"]] \
            if rank == "g" else emit(g, child)
        out.append([rank, sci, x.get("name") if x else None, kids] + ([type_of[(g, sci)]] if rank == "g" and (g, sci) in type_of else []))
    return out


(SITE / "data").mkdir(parents=True, exist_ok=True)
(SITE / "data" / "tree.json").write_text(dump({G[g]: emit(g, d) for g, d in tree.items()}), encoding="utf-8")

# --- 검색 목록 ---
rows = []
for t in names:
    if t["rank"] not in ("order", "suborder", "family", "genus", "species"):
        continue
    ssp = [[s["sci"], s.get("ko"), s.get("note")] for s in t.get("subspecies", []) if s.get("ko")]
    fam = families.get((t["group"], t.get("family")))
    rk = "u" if t["rank"] == "suborder" else t["rank"][0]
    rows.append([G[t["group"]], rk, t["sci"], t.get("name"), t.get("en"),
                 t["status"], t.get("family"), ssp or None, (fam or {}).get("name"), 1 if has_pic(t["sci"]) else 0])
(SITE / "data" / "names.min.json").write_text(dump(rows), encoding="utf-8")

# --- 첫 화면에 띄울 종 ---
pool = [t["sci"] for t in species if t.get("name") and has_pic(t["sci"])]
(SITE / "data" / "random.json").write_text(dump(pool), encoding="utf-8")

# --- 종 문서 ---
shutil.rmtree(SITE / "sp", ignore_errors=True)
(SITE / "sp").mkdir(parents=True)
seq = {g: [t for t in species if t["group"] == g] for g in G}
for g, lst in seq.items():
    for i, t in enumerate(lst):
        o, so, sup = lineage(t)
        m = media.get(t["sci"], {})
        nb = lambda j: short(lst[j]) if 0 <= j < len(lst) else None
        rec = dict(
            group=g, sci=t["sci"], name=t.get("name"), status=t["status"], en=t.get("en"),
            author=t.get("author") or (bird_auth.get(t["sci"]) if g == "AVES" else None),
            rationale=t.get("rationale") if t["status"] in ("consensus", "proposal") else None,
            review=t.get("review") if "국가생물종목록" not in (t.get("review") or "") else None,
            synonyms=t.get("synonyms"),
            order=taxon(orders, g, o), suborder=taxon(orders, g, so), superfamily=taxon(orders, g, sup),
            family=taxon(families, g, t.get("family")),
            genus=dict(taxon(genera, g, t["sci"].split()[0]), type=type_of.get((g, t["sci"].split()[0]))),
            type_species=type_of.get((g, t["sci"].split()[0])) == t["sci"],
            subfamily=taxon(subfams, g, sub_of.get((g, t["sci"].split()[0]))),
            subspecies=[s for s in t.get("subspecies", []) if s.get("ko") or t["group"] == "REPTILIA"],
            kos=dict(category=t["kos"].get("category")) if t.get("kos") else None, kr=t.get("kr"),
            refs=dict(official=None,  # 국가생물종목록은 쓰지 않는다
                      moe=t.get("moe"), trade=t.get("trade")),
            ebird=ebird.get(t["sci"]),
            dist=dist_of(t["sci"]),
            iucn=(bird_iucn.get(t["sci"]) if g == "AVES" else None) or (dist.get(t["sci"]) or {}).get("iucn"),
            inat=m.get("inat"), photos=pics(m), wiki=wiki_of(t, m), fetched=m.get("fetched"),
            prev=nb(i - 1), next=nb(i + 1), pos=[i + 1, len(lst)],
        )
        (SITE / "sp" / fname(t["sci"])).write_text(dump(rec), encoding="utf-8")

# --- 과 문서: 명칭 근거 + 포함 속·종 ---
shutil.rmtree(SITE / "fam", ignore_errors=True)
(SITE / "fam").mkdir(parents=True)
fam_seq = {g: [] for g in G}
for t in species:  # 종이 실제로 있는 과만, 시트 순서대로
    k = (t["group"], t.get("family"))
    if t.get("family") and k in families and families[k] not in fam_seq[t["group"]]:
        fam_seq[t["group"]].append(families[k])
for g, lst in fam_seq.items():
    for i, f in enumerate(lst):
        sps = [t for t in seq[g] if t.get("family") == f["sci"]]
        gens = {}
        for s in sps:
            gens.setdefault(s["sci"].split()[0], []).append(s)
        o, so, sup = lineage(sps[0])
        nb = lambda j: short(lst[j]) if 0 <= j < len(lst) else None
        rec = dict(
            group=g, sci=f["sci"], name=f.get("name"), status=f["status"], en=f.get("en"),
            rationale=f.get("rationale"),
            refs=dict(official=None,
                      kos=(f.get("kos") or {}).get("ko") if f["status"] != "kos" else None),
            order=taxon(orders, g, o), suborder=taxon(orders, g, so), superfamily=taxon(orders, g, sup),
            subfamilies=[dict(sci=x["sci"], name=x.get("name"), en=x.get("en"), rationale=x.get("rationale"))
                         for x in subfamilies if x["group"] == g and x.get("family") == f["sci"]],
            genera=[dict(sci=ge, name=(genera.get((g, ge)) or {}).get("name"), subfamily=sub_of.get((g, ge)),
                         type=type_of.get((g, ge)),
                         status=(genera.get((g, ge)) or {}).get("status"),
                         rationale=(genera.get((g, ge)) or {}).get("rationale"),
                         species=[[s["sci"], s.get("name"), s.get("en"), s["status"], 1 if has_pic(s["sci"]) else 0]
                                  for s in ss]) for ge, ss in gens.items()],
            counts=dict(genera=len(gens), species=len(sps), named=sum(1 for s in sps if s.get("name"))),
            prev=nb(i - 1), next=nb(i + 1), pos=[i + 1, len(lst)],
        )
        (SITE / "fam" / fname(f["sci"])).write_text(dump(rec), encoding="utf-8")

# --- 분포 지도용 나라 코드 표(GBIF 두 글자 → 세계지도 숫자) ---
shutil.copy(DATA / "iso2num.json", SITE / "data" / "iso2num.json")

# --- 페이지 ---
stats = {g: dict(total=len(seq[g]), named=sum(1 for t in seq[g] if t.get("name")),
                 photos=sum(1 for t in seq[g] if has_pic(t["sci"]))) for g in G}
meta = dict(stats=stats, built=datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M KST"))
for name in ("index", "find", "sp", "fam"):
    tpl = (SITE / f"{name}.template.html").read_text(encoding="utf-8")
    (SITE / f"{name}.html").write_text(tpl.replace("/*META*/null", json.dumps(meta, ensure_ascii=False)), encoding="utf-8")
print("검색 목록", len(rows), "· 종 문서", len(species), "· 과 문서", sum(len(v) for v in fam_seq.values()),
      "· 첫 화면 후보", len(pool))
