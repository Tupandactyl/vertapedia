"""data/names.json·data/media 에서 사이트 자료를 만든다.

- site/data/names.min.json : 검색용 가벼운 목록
- site/data/tree.json      : 목 > 과 > 속 > 종 분류 나무 (시트 순서)
- site/data/random.json    : 첫 화면에서 고를 종 (국명과 사진이 있는 종)
- site/sp/<학명>.json      : 종 페이지 하나에 필요한 모든 것 (시트 기준 이전·다음 종 포함)
- site/{index,find,sp}.html
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
ebird_fam = load("ebird_families.json", {})
media = {}
for f in (DATA / "media").glob("*.json"):
    m = json.loads(f.read_text(encoding="utf-8"))
    media[m["sci"]] = m
G = {"AVES": "A", "REPTILIA": "R"}
UNPLACED = "(분류 미정)"


def first_by(rank):
    out = {}
    for t in names:
        if t["rank"] == rank:
            out.setdefault((t["group"], t["sci"]), t)
    return out


orders, families, genera = first_by("order"), first_by("family"), first_by("genus")
species = [t for t in names if t["rank"] == "species"]
has_pic = lambda sci: bool(media.get(sci, {}).get("photos"))


def short(t):
    return dict(sci=t["sci"], name=t.get("name"), status=t["status"]) if t else None


def order_of(t):
    fam = families.get((t["group"], t.get("family")))
    o = (fam or {}).get("order") or (ebird_fam.get(t.get("family")) if t["group"] == "AVES" else None)
    return o


# --- 분류 나무 (시트 순서를 지킨다) ---
tree = {}
for t in species:
    g, o, f, ge = t["group"], order_of(t) or UNPLACED, t.get("family") or UNPLACED, t["sci"].split()[0]
    tree.setdefault(g, {}).setdefault(o, {}).setdefault(f, {}).setdefault(ge, []).append(t)


def node(rank_map, g, sci):
    x = rank_map.get((g, sci))
    return [sci, x.get("name") if x else None]


tree_out = {}
for g, os_ in tree.items():
    tree_out[G[g]] = [
        node(orders, g, o) + [[node(families, g, f) + [[node(genera, g, ge) + [[
            [s["sci"], s.get("name"), s.get("en"), 1 if has_pic(s["sci"]) else 0] for s in sps]]
            for ge, sps in gens.items()]] for f, gens in fams.items()]]
        for o, fams in os_.items()]
(SITE / "data").mkdir(parents=True, exist_ok=True)
dump = lambda obj: json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
(SITE / "data" / "tree.json").write_text(dump(tree_out), encoding="utf-8")

# --- 검색 목록 ---
rows = []
for t in names:
    if t["rank"] not in ("order", "family", "genus", "species"):
        continue
    ssp = [[s["sci"], s.get("ko"), s.get("note")] for s in t.get("subspecies", []) if s.get("ko")]
    fam = families.get((t["group"], t.get("family")))
    rows.append([G[t["group"]], t["rank"][0], t["sci"], t.get("name"), t.get("en"),
                 t["status"], t.get("family"), ssp or None, (fam or {}).get("name"), 1 if has_pic(t["sci"]) else 0])
(SITE / "data" / "names.min.json").write_text(dump(rows), encoding="utf-8")

# --- 첫 화면에 띄울 종 ---
pool = [t["sci"] for t in species if t.get("name") and has_pic(t["sci"])]
(SITE / "data" / "random.json").write_text(dump(pool), encoding="utf-8")

# --- 종 페이지 자료 ---
shutil.rmtree(SITE / "sp", ignore_errors=True)
(SITE / "sp").mkdir(parents=True)
seq = {g: [t for t in species if t["group"] == g] for g in G}
for g, lst in seq.items():
    for i, t in enumerate(lst):
        fam = families.get((g, t.get("family")))
        o = order_of(t)
        gen = genera.get((g, t["sci"].split()[0]))
        m = media.get(t["sci"], {})
        nb = lambda j: short(lst[j]) if 0 <= j < len(lst) else None
        rec = dict(
            group=g, sci=t["sci"], name=t.get("name"), status=t["status"], en=t.get("en"),
            author=t.get("author"),
            rationale=t.get("rationale") if t["status"] in ("consensus", "proposal") else None,
            review=t.get("review"), synonyms=t.get("synonyms"),
            order=short(orders.get((g, o))) or ({"sci": o} if o else None),
            family=short(fam) or ({"sci": t.get("family")} if t.get("family") else None),
            genus=short(gen) or {"sci": t["sci"].split()[0]},
            subspecies=[s for s in t.get("subspecies", []) if s.get("ko")],
            kos=dict(category=t["kos"].get("category")) if t.get("kos") else None,
            refs=dict(official=t.get("official") if t["status"] != "official" else None,
                      moe=t.get("moe"), trade=t.get("trade")),
            ebird=ebird.get(t["sci"]),
            inat=m.get("inat"), photos=m.get("photos", []), wiki=m.get("wiki"), fetched=m.get("fetched"),
            prev=nb(i - 1), next=nb(i + 1), pos=[i + 1, len(lst)],
        )
        (SITE / "sp" / (t["sci"].replace(" ", "_") + ".json")).write_text(dump(rec), encoding="utf-8")

# --- 페이지 ---
stats = {g: dict(total=len(seq[g]), named=sum(1 for t in seq[g] if t.get("name")),
                 photos=sum(1 for t in seq[g] if has_pic(t["sci"]))) for g in G}
meta = dict(stats=stats, built=datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M KST"))
for name in ("index", "find", "sp"):
    tpl = (SITE / f"{name}.template.html").read_text(encoding="utf-8")
    (SITE / f"{name}.html").write_text(tpl.replace("/*META*/null", json.dumps(meta, ensure_ascii=False)), encoding="utf-8")
print("검색 목록", len(rows), "· 종 페이지", len(species), "· 첫 화면 후보", len(pool))
