"""data/names.json·data/media 에서 사이트 자료를 만든다.

- site/data/names.min.json : 검색용 가벼운 목록
- site/sp/<학명>.json      : 종 페이지 하나에 필요한 모든 것
- site/index.html          : 첫 화면(통계 넣기)
"""
import json
import shutil
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SITE = ROOT / "site"

names = json.loads((DATA / "names.json").read_text(encoding="utf-8"))
ebird = json.loads((DATA / "ebird_codes.json").read_text(encoding="utf-8")) if (DATA / "ebird_codes.json").exists() else {}
media = {}
for f in (DATA / "media").glob("*.json"):
    m = json.loads(f.read_text(encoding="utf-8"))
    media[m["sci"]] = m
G = {"AVES": "A", "REPTILIA": "R"}
key = lambda t: (t["group"], t["sci"])
families = {key(t): t for t in names if t["rank"] == "family"}
genera = {key(t): t for t in names if t["rank"] == "genus"}


def short(t):
    return dict(sci=t["sci"], name=t.get("name"), status=t["status"]) if t else None


# --- 검색 목록 ---
rows = []
for t in names:
    if t["rank"] not in ("family", "genus", "species"):
        continue
    ssp = [[s["sci"], s.get("ko"), s.get("note")] for s in t.get("subspecies", []) if s.get("ko")]
    fam = families.get((t["group"], t.get("family")))
    rows.append([G[t["group"]], t["rank"][0], t["sci"], t.get("name"), t.get("en"),
                 t["status"], t.get("family"), ssp or None, (fam or {}).get("name"),
                 1 if t["sci"] in media and media[t["sci"]]["photos"] else 0])
(SITE / "data").mkdir(parents=True, exist_ok=True)
(SITE / "data" / "names.min.json").write_text(json.dumps(rows, ensure_ascii=False, separators=(",", ":")),
                                               encoding="utf-8")

# --- 종 페이지 자료 ---
shutil.rmtree(SITE / "sp", ignore_errors=True)
(SITE / "sp").mkdir(parents=True)
for t in names:
    if t["rank"] != "species":
        continue
    fam = families.get((t["group"], t.get("family")))
    gen = genera.get((t["group"], t["sci"].split()[0]))
    m = media.get(t["sci"], {})
    rec = dict(
        group=t["group"], sci=t["sci"], name=t.get("name"), status=t["status"], en=t.get("en"),
        author=t.get("author") or (t.get("kos") or {}).get("author"),
        rationale=t.get("rationale") if t["status"] in ("consensus", "proposal") else None,
        review=t.get("review"), synonyms=t.get("synonyms"),
        order=(fam or {}).get("order"), family=short(fam) or ({"sci": t.get("family")} if t.get("family") else None),
        genus=short(gen) or {"sci": t["sci"].split()[0]},
        subspecies=[s for s in t.get("subspecies", []) if s.get("ko")],
        kos=dict(category=t["kos"].get("category")) if t.get("kos") else None,
        refs=dict(official=t.get("official") if t["status"] != "official" else None,
                  moe=t.get("moe"), trade=t.get("trade")),
        ebird=ebird.get(t["sci"]),
        inat=m.get("inat"), photos=m.get("photos", []), wiki=m.get("wiki"), fetched=m.get("fetched"),
    )
    (SITE / "sp" / (t["sci"].replace(" ", "_") + ".json")).write_text(
        json.dumps(rec, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

# --- 첫 화면 ---
sp = [t for t in names if t["rank"] == "species"]
stats = {g: dict(total=sum(1 for t in sp if t["group"] == g),
                 named=sum(1 for t in sp if t["group"] == g and t.get("name")),
                 photos=sum(1 for t in sp if t["group"] == g and media.get(t["sci"], {}).get("photos")))
         for g in ("AVES", "REPTILIA")}
meta = dict(stats=stats, built=datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M KST"))
for name in ("index", "sp"):
    tpl = (SITE / f"{name}.template.html").read_text(encoding="utf-8")
    (SITE / f"{name}.html").write_text(tpl.replace("/*META*/null", json.dumps(meta, ensure_ascii=False)),
                                       encoding="utf-8")
print("검색 목록", len(rows), "· 종 페이지", len(sp), "· 사진 있는 종", sum(v["photos"] for v in stats.values()))
