"""data/names.json·data/media 에서 사이트 자료를 만든다.

- site/data/names.min.json : 검색용 가벼운 목록
- site/data/tree.json      : 목 > (아목) > 과 > 속 > 종 분류군 (시트 순서)
- site/data/random.json    : 첫 화면에서 고를 종 (국명과 사진이 있는 종)
- site/sp/<학명>.json      : 종 문서 (시트 기준 이전·다음 종 포함)
- site/fam/<학명>.json     : 과 문서 — 명칭 근거와 포함 속·종 목록
- site/{index,find,sp,fam}.html
"""
import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SITE = ROOT / "site"


def load(name, default=None):
    f = DATA / name
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else default


names = load("names.json")
ebird = load("ebird_codes.json", {})
ebird_ord = load("ebird_families.json", {})
media = {}
for f in (DATA / "media").glob("*.json"):
    m = json.loads(f.read_text(encoding="utf-8"))
    media[m["sci"]] = m
G = {"AVES": "A", "REPTILIA": "R"}
NOFAM = "(과 미정)"


def first_by(*ranks):
    out = {}
    for t in names:
        if t["rank"] in ranks:
            out.setdefault((t["group"], t["sci"]), t)
    return out


orders, families, genera = first_by("order", "suborder"), first_by("family"), first_by("genus")
subfamilies = [t for t in names if t["rank"] == "subfamily"]
species = [t for t in names if t["rank"] == "species"]
has_pic = lambda sci: bool(media.get(sci, {}).get("photos"))
dump = lambda obj: json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
fname = lambda sci: sci.replace(" ", "_") + ".json"


def short(t):
    return dict(sci=t["sci"], name=t.get("name"), status=t["status"]) if t else None


def lineage(t):
    """(목, 아목) — 과 행에 적힌 것, 없으면 eBird 과 → 목, 분류미정 탭이면 그 탭의 목·아목"""
    fam = families.get((t["group"], t.get("family"))) or {}
    o = fam.get("order") or t.get("order_hint") or (ebird_ord.get(t.get("family")) if t["group"] == "AVES" else None)
    so = fam.get("suborder") or t.get("suborder_hint")
    return o, so


def taxon(rank_map, g, sci):
    x = rank_map.get((g, sci))
    return short(x) if x else ({"sci": sci} if sci else None)


# --- 분류군: 내부 마디 [계급, 학명, 국명, 자식들], 종 [학명, 국명, 영명, 사진] ---
tree = {}
for t in species:
    g = t["group"]
    o, so = lineage(t)
    path = [("o", o or "(목 미정)")] + ([("u", so)] if so else []) + [("f", t.get("family") or NOFAM),
                                                                     ("g", t["sci"].split()[0])]
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
        src = {"o": orders, "u": orders, "f": families, "g": genera}[rank]
        x = src.get((g, sci))
        kids = [[s["sci"], s.get("name"), s.get("en"), 1 if has_pic(s["sci"]) else 0] for s in child["_sp"]] \
            if rank == "g" else emit(g, child)
        out.append([rank, sci, x.get("name") if x else None, kids])
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
        o, so = lineage(t)
        m = media.get(t["sci"], {})
        nb = lambda j: short(lst[j]) if 0 <= j < len(lst) else None
        rec = dict(
            group=g, sci=t["sci"], name=t.get("name"), status=t["status"], en=t.get("en"),
            author=t.get("author"),
            rationale=t.get("rationale") if t["status"] in ("consensus", "proposal") else None,
            review=t.get("review"), synonyms=t.get("synonyms"),
            order=taxon(orders, g, o), suborder=taxon(orders, g, so),
            family=taxon(families, g, t.get("family")), genus=taxon(genera, g, t["sci"].split()[0]),
            subspecies=[s for s in t.get("subspecies", []) if s.get("ko")],
            kos=dict(category=t["kos"].get("category")) if t.get("kos") else None,
            refs=dict(official=t.get("official") if t["status"] != "official" else None,
                      moe=t.get("moe"), trade=t.get("trade")),
            ebird=ebird.get(t["sci"]),
            inat=m.get("inat"), photos=m.get("photos", []), wiki=m.get("wiki"), fetched=m.get("fetched"),
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
        o, so = lineage(sps[0])
        nb = lambda j: short(lst[j]) if 0 <= j < len(lst) else None
        rec = dict(
            group=g, sci=f["sci"], name=f.get("name"), status=f["status"], en=f.get("en"),
            rationale=f.get("rationale"),
            refs=dict(official=f.get("official") if f["status"] != "official" else None,
                      kos=(f.get("kos") or {}).get("ko") if f["status"] != "kos" else None),
            order=taxon(orders, g, o), suborder=taxon(orders, g, so),
            subfamilies=[dict(sci=x["sci"], name=x.get("name"), en=x.get("en"), rationale=x.get("rationale"))
                         for x in subfamilies if x["group"] == g and x.get("family") == f["sci"]],
            genera=[dict(sci=ge, name=(genera.get((g, ge)) or {}).get("name"),
                         status=(genera.get((g, ge)) or {}).get("status"),
                         rationale=(genera.get((g, ge)) or {}).get("rationale"),
                         species=[[s["sci"], s.get("name"), s.get("en"), s["status"], 1 if has_pic(s["sci"]) else 0]
                                  for s in ss]) for ge, ss in gens.items()],
            counts=dict(genera=len(gens), species=len(sps), named=sum(1 for s in sps if s.get("name"))),
            prev=nb(i - 1), next=nb(i + 1), pos=[i + 1, len(lst)],
        )
        (SITE / "fam" / fname(f["sci"])).write_text(dump(rec), encoding="utf-8")

# --- 페이지 ---
stats = {g: dict(total=len(seq[g]), named=sum(1 for t in seq[g] if t.get("name")),
                 photos=sum(1 for t in seq[g] if has_pic(t["sci"]))) for g in G}
meta = dict(stats=stats, built=datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M KST"))
for name in ("index", "find", "sp", "fam"):
    tpl = (SITE / f"{name}.template.html").read_text(encoding="utf-8")
    (SITE / f"{name}.html").write_text(tpl.replace("/*META*/null", json.dumps(meta, ensure_ascii=False)), encoding="utf-8")
print("검색 목록", len(rows), "· 종 문서", len(species), "· 과 문서", sum(len(v) for v in fam_seq.values()),
      "· 첫 화면 후보", len(pool))
