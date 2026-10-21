"""국명·학명 근거 대조(한국조류목록 2025, 한국양서파충류학회 2025, Reptile Database)를 검토 페이지(site/review.html)에 넣는다."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SITE = ROOT / "site"

kshr = json.loads((DATA / "kshr.json").read_text(encoding="utf-8"))
rdb = json.loads((DATA / "rdb.json").read_text(encoding="utf-8"))

kos = json.loads((DATA / "kos.json").read_text(encoding="utf-8"))
refs = json.loads((DATA / "references.json").read_text(encoding="utf-8"))

notes = [
    "조류 국명은 한국조류목록 2025를 먼저 쓰고, 없으면 시트 합의본, 그다음 모든 편집자가 같은 이름을 낸 개인 제안을 씁니다.",
    "파충류 국명은 한국양서파충류학회 파충류 종 목록(2025년 4월)을 먼저 쓰고, 없으면 시트 합의본을 씁니다.",
    "아종 단위로 합쳐진 종은 상위 종 페이지에 아종 국명으로 표시합니다.",
]

data = dict(kos=kos, kshr=kshr, rdb=rdb, refs=refs, notes=notes,
            built=datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M KST"))
tpl = (SITE / "review.template.html").read_text(encoding="utf-8")
out = tpl.replace("/*DATA*/null", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
(SITE / "review.html").write_text(out, encoding="utf-8")
print("site/review.html", len(out) // 1024, "KB")
