"""data/names.json 에서 사이트용 가벼운 목록(site/data/names.min.json)과 첫 화면을 만든다."""
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SITE = ROOT / "site"

names = json.loads((DATA / "names.json").read_text(encoding="utf-8"))
G = {"AVES": "A", "REPTILIA": "R"}

rows = []
for t in names:
    if t["rank"] not in ("family", "genus", "species"):
        continue
    ssp = [[s["sci"], s.get("ko"), s.get("note")] for s in t.get("subspecies", []) if s.get("ko")]
    rows.append([G[t["group"]], t["rank"][0], t["sci"], t.get("name"), t.get("en"),
                 t["status"], t.get("family"), ssp or None])

(SITE / "data").mkdir(parents=True, exist_ok=True)
(SITE / "data" / "names.min.json").write_text(json.dumps(rows, ensure_ascii=False, separators=(",", ":")),
                                               encoding="utf-8")

sp = [t for t in names if t["rank"] == "species"]
stats = {g: dict(total=sum(1 for t in sp if t["group"] == g),
                 named=sum(1 for t in sp if t["group"] == g and t.get("name")))
         for g in ("AVES", "REPTILIA")}
meta = dict(stats=stats, built=datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M KST"),
            status=Counter(t["status"] for t in sp))
tpl = (SITE / "index.template.html").read_text(encoding="utf-8")
(SITE / "index.html").write_text(tpl.replace("/*META*/null", json.dumps(meta, ensure_ascii=False)), encoding="utf-8")
print("site/index.html,", len(rows), "분류군")
