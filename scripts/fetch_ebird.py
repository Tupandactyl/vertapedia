"""eBird 분류표에서 학명 → eBird 종 코드 표를 만든다(data/ebird_codes.json). 키 없이 받을 수 있다."""
import csv
import io
import json
import urllib.request
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
URL = "https://api.ebird.org/v2/ref/taxonomy/ebird?fmt=csv&cat=species"
req = urllib.request.Request(URL, headers={"User-Agent": "Vertapedia/0.1 (https://github.com/Tupandactyl/vertapedia)"})
with urllib.request.urlopen(req, timeout=120) as r:
    rows = list(csv.DictReader(io.StringIO(r.read().decode("utf-8"))))
codes = {r["SCIENTIFIC_NAME"]: r["SPECIES_CODE"] for r in rows}
(DATA / "ebird_codes.json").write_text(json.dumps(codes, ensure_ascii=False, sort_keys=True, indent=0), encoding="utf-8")
print("eBird 종 코드", len(codes))
