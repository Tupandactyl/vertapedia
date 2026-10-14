"""한국양서파충류학회 「우리나라 파충류 종 목록」(5차 개정 2025년 4월) PDF → data/kshr2025.json

- ☆ 줄은 학회 수정의견. 같은 국명의 ☆ 없는 줄(국가생물종목록 기준)은 대체된 것으로 본다.
- * 는 북한에 서식하는 종.
PDF 원본은 저장소에 올리지 않는다.

    python scripts/parse_kshr.py "C:/.../reptile_file.pdf"
"""
import json
import re
import sys
from pathlib import Path

import pypdf

DATA = Path(__file__).resolve().parent.parent / "data"
LINE = re.compile(r"^\s*(\d+)\s*(☆)?\.?\s+([A-Z][a-z]+ [a-z]+(?: [a-z]+)?)\s+\(?([^)\[]*?\d{4})\)?\s+(\S+)\s*(?:\[([^\]]*)\])?\s*(\*)?\s*$")


def main(pdf):
    text = "\n".join(p.extract_text() for p in pypdf.PdfReader(pdf).pages)
    rows = []
    for line in text.splitlines():
        if "Genus" in line or "Family" in line or "Order" in line:
            continue
        m = LINE.match(line)
        if m:
            no, star, sci, author, ko, en, nk = m.groups()
            rows.append(dict(no=int(no), revised=bool(star), sci=sci, author=author.strip(), ko=ko, en=en, north=bool(nk)))
    # 같은 국명에 ☆ 줄이 있으면 ☆ 없는 줄은 대체됨
    revised = {r["ko"] for r in rows if r["revised"]}
    for r in rows:
        r["superseded"] = not r["revised"] and r["ko"] in revised
    out = DATA / "kshr2025.json"
    out.write_text(json.dumps(dict(source="한국양서파충류학회 우리나라 파충류 종 목록 (5차 개정, 2025년 4월)", species=rows),
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print(len(rows), "줄 →", out, "· 쓰는 것", sum(1 for r in rows if not r["superseded"]))


if __name__ == "__main__":
    main(sys.argv[1])
