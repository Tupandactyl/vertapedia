"""조류 법정 관리종 목록 → data/moe_birds.json

원본(저장소에 올리지 않는다, 경로를 인자로 준다):
  --cites     「국제적멸종위기종 목록」 별표 (기후에너지환경부고시 제2026-63호) .hwpx
  --white     「백색목록 지정」 별표 (기후에너지환경부고시 제2025-55호, 지정관리 야생동물) .hwpx
  --inflow    「유입주의 생물 지정 고시」 별표 (기후에너지환경부고시 제2025-72호) .hwpx
  --export    야생생물법 시행규칙 [별표 8] 수출ㆍ수입등 허가대상인 야생생물 .pdf
  --facility  야생생물법 시행령 [별표 1의3] 사육시설 등록대상인 국제적 멸종위기종 .pdf
  --nibr      국립생물자원관(2018) 「국가지정 주요 관리대상 생물종의 국명·영명 부여」 최종보고서 .pdf

종 단위(이명법)로 지정된 것만 담는다. 목·과·속 전종(spp.)과 아종 지정은 뺀다.
결과: [{"sci", "lists": {"cites": "I"|"II"|"III", "white"|"inflow"|"export"|"facility": "Y"}, "names": {목록: 국명}, "nibr": {"old", "new"}}]

    python scripts/parse_moe_birds.py --cites a.hwpx --white b.hwpx --inflow c.hwpx --export d.pdf --facility e.pdf --nibr f.pdf
"""
import argparse
import json
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

import pypdf

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
BINOM = re.compile(r"^([A-Z][a-z]+) ([a-z]+)$")


def hwpx_rows(path):
    """HWPX 표의 행: [[칸 글자, ...], ...]"""
    z, rows = zipfile.ZipFile(path), []
    for n in sorted(x for x in z.namelist() if re.match(r"Contents/section\d+\.xml", x)):
        for tr in ET.fromstring(z.read(n)).iter():
            if tr.tag.endswith("}tr"):
                rows.append([" ".join("".join(t.text or "" for t in p.iter() if t.tag.endswith("}t"))
                                      for p in tc.iter() if p.tag.endswith("}p")).strip()
                             for tc in tr if tc.tag.endswith("}tc")])
    return rows


def pdf_text(path):
    return "\n".join(p.extract_text() or "" for p in pypdf.PdfReader(str(path)).pages)


def genera():
    names = json.loads((DATA / "names.json").read_text(encoding="utf-8"))
    old = {"Ixobrychus"}  # 지금은 다른 속으로 옮겨진, 법령에만 남은 속명
    return sorted({t["sci"].split()[0] for t in names if t["group"] == "AVES"} | old, key=len, reverse=True)


GENERA = None


def split_sci(s):
    """PDF 에서 붙어 나온 학명(Gaviaadamsii)을 속명·종소명으로 나눈다."""
    s = re.sub(r"\s+", " ", s).strip()
    if BINOM.match(s) or " " in s:
        return s
    for g in GENERA:
        if s.startswith(g) and len(s) > len(g) and s[len(g)].islower():
            return f"{g} {s[len(g):]}"
    return s


ENTRY = re.compile(r"([가-힣][가-힣 ()·\-]*?)\s+([A-Z][a-z]+(?:\s+[a-z]+){1,2})(?=\s|$|\()")


def cites(path):
    rows = hwpx_rows(path)
    a = next(i for i, r in enumerate(rows) if r and r[0].startswith("기러기목"))
    b = next(i for i in range(a, len(rows)) if rows[i] and rows[i][0].startswith("악어목"))
    out = []
    for r in rows[a:b]:
        if len(r) < 3:
            continue
        cols = r[-3:]
        for app, cell in zip(("I", "II", "III"), cols):
            for m in ENTRY.finditer(cell):
                out.append((m[2], re.sub(r"\s+", "", m[1]), app))
    return out


def white(path):
    rows = hwpx_rows(path)
    # 두 번째 표(조류): 번호·학명·비고(국명)
    heads = [i for i, r in enumerate(rows) if r[:2] == ["번호", "학명"]]
    a, b = heads[1], heads[2]
    return [(r[1].strip(), r[2].strip()) for r in rows[a + 1:b] if len(r) >= 3 and r[0].isdigit()]


def inflow(path):
    rows = hwpx_rows(path)
    a = next(i for i, r in enumerate(rows) if r and r[0] == "조류")
    out = []
    for r in rows[a:]:
        if r and r[0] not in ("조류",) and len(r) == 3:
            break  # 다음 분류군(어류 등)
        sci, ko = r[-2], r[-1]
        if BINOM.match(sci.strip()):
            out.append((sci.strip(), ko.strip()))
    return out


def numbered(text, start, end):
    """'번호 국명 학명' 줄 목록 (PDF)"""
    a = text.index(start)
    b = text.index(end, a)
    out = []
    for line in text[a:b].splitlines():
        m = re.match(r"^(\d+) (.+?) ([A-Z][a-z]+(?: ?[a-z]+)*)\s*$", line.strip().replace("　", " ").strip())
        if m:
            out.append((split_sci(m[3]), re.sub(r"\s+", "", m[2])))
    return out


def nibr(path):
    """CITES 국명 재검토(조류 340~591번), 위해우려종(11~15번), 신규 국명(20~23번)"""
    pages = [p.extract_text() or "" for p in pypdf.PdfReader(str(path)).pages]
    han = r"[가-힣()·\-]+(?: 전종)?"
    out = {}
    review = "\n".join(pages[575:672])
    # 기존 국명이 칸 폭을 넘으면 마지막 한두 글자가 다음 줄로 넘어간다(검은허벅다리가다랭이잡 / 이 검은등얼가니새)
    for m in re.finditer(rf"^(\d+) 조류 ([A-Z][a-z]+)\s+([a-z]+)\s+({han}(?:\n[가-힣]{{1,2}}(?= [가-힣]))?)\s+({han})", review, re.M):
        out[f"{m[2]} {m[3]}"] = dict(old=m[4].replace("\n", ""), new=m[5])
    new = "\n".join(pages[48:54])
    for m in re.finditer(rf"^(\d+) 조류 ([A-Z][a-z]+)\s+([a-z]+)\s+({han})", new, re.M):
        out.setdefault(f"{m[2]} {m[3]}", dict(old=None, new=m[4]))
    return out


def main():
    global GENERA
    ap = argparse.ArgumentParser()
    for k in ("cites", "white", "inflow", "export", "facility", "nibr"):
        ap.add_argument("--" + k, required=True)
    a = ap.parse_args()
    GENERA = genera()
    rec = {}

    def add(sci, lst, val, ko):
        sci = re.sub(r"\s+", " ", sci).strip()
        if not BINOM.match(sci):
            return  # 아종·속 이상 지정은 뺀다
        r = rec.setdefault(sci, dict(sci=sci, lists={}, names={}, nibr=None))
        r["lists"][lst] = val
        if ko:
            r["names"][lst] = ko

    for sci, ko, app in cites(a.cites):
        add(sci, "cites", app, ko)
    for sci, ko in white(a.white):
        add(sci, "white", "Y", ko)
    for sci, ko in inflow(a.inflow):
        add(sci, "inflow", "Y", ko)
    ex = pdf_text(a.export)
    for sci, ko in numbered(ex, "3.조류", "4.파충류"):
        add(sci, "export", "Y", ko)
    fa = pdf_text(a.facility)
    for sci, ko in numbered(fa, "나. 조류", "다. 파충류"):
        add(sci, "facility", "Y", ko)
    nb = nibr(a.nibr)
    for sci, v in nb.items():
        if sci in rec:
            rec[sci]["nibr"] = v
        elif BINOM.match(sci):
            rec[sci] = dict(sci=sci, lists={}, names={}, nibr=v)
    out = sorted(rec.values(), key=lambda r: r["sci"])
    (DATA / "moe_birds.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    from collections import Counter
    c = Counter(k for r in out for k in r["lists"])
    print(len(out), "종 ·", dict(c), "· 보고서", sum(1 for r in out if r["nibr"]))


if __name__ == "__main__":
    main()
