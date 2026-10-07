"""data/review.json·conflicts.json 을 검토 페이지(site/review.html)에 넣는다."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SITE = ROOT / "site"

review = json.loads((DATA / "review.json").read_text(encoding="utf-8"))
conflicts = json.loads((DATA / "conflicts.json").read_text(encoding="utf-8"))

kos = json.loads((DATA / "kos.json").read_text(encoding="utf-8"))
refs = json.loads((DATA / "references.json").read_text(encoding="utf-8"))

notes = [
    "조류 국명은 한국조류목록 2025가 국가생물종목록보다 먼저입니다. 두 목록의 국명이 다르면 2025 이름을 씁니다.",
    "아종 단위로 합쳐진 종(미국쇠오리, 줄무늬노랑발갈매기, 쇠홍방울새)은 상위 종 페이지에 아종 국명으로 표시합니다.",
    "국명 이동은 시트가 한국 개체군을 다른 학명으로 본 경우입니다. 해당 국명을 그 학명으로 옮겨 썼습니다.",
]

data = dict(review=review, conflicts=conflicts, kos=kos, refs=refs, notes=notes,
            built=datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M KST"))
tpl = (SITE / "review.template.html").read_text(encoding="utf-8")
out = tpl.replace("/*DATA*/null", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
(SITE / "review.html").write_text(out, encoding="utf-8")
print("site/review.html", len(out) // 1024, "KB")
