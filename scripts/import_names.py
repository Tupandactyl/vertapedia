"""국명 자료를 하나로 모은다.

- 국가생물종목록 Ⅱ (2019) PDF → 공식 국명
- 한국조류목록 2025 (한국조류학회) → 조류 국명 보충
- 조류·파충류 구글 시트(xlsx 내보내기) → 학명 체계, 합의본·개인 제안·명칭 근거
- data/overrides.json → 편집자가 직접 정한 대응

결과: data/names.json, data/report.txt
"""
import json, re, sys
from collections import Counter, defaultdict
from pathlib import Path

import openpyxl
import pypdf

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
PDF = Path(sys.argv[1]) if len(sys.argv) > 1 else None

RANKS = ["class", "order", "suborder", "family", "subfamily", "genus"]


def cell(r, i):
    return r[i] if i is not None and i < len(r) else None


def norm(v):
    """국명 비교용: 첫 줄의 괄호 앞부분만, 공백·물음표 없이."""
    if not v:
        return ""
    return re.split(r"[\n(（/]", str(v))[0].replace(" ", "").replace("?", "").strip()


def stem(ep):
    """라틴어 종소명의 성 어미를 떼어 낸다."""
    return re.sub(r"(us|um|a|is|e|er|ra|rum)$", "", ep)


def ko_keys(v):
    """한 칸에 적힌 이름과 괄호 속 이명을 모두 비교 열쇠로."""
    if not v:
        return set()
    parts = re.split(r"[\n()（）/;,]", str(v))
    return {p.replace(" ", "").replace("?", "").strip() for p in parts if re.search(r"[가-힣]", p)}


def clean(v):
    if v is None:
        return None
    v = str(v).strip()
    return v or None


# ---------- 국가생물종목록 ----------
def parse_nibr(pdf_path, first=155, last=215):
    reader = pypdf.PdfReader(str(pdf_path))
    text = "\n".join((reader.pages[i].extract_text() or "") for i in range(first, last))
    rank_re = re.compile(r"^(Class|Order|Suborder|Family|Subfamily|Genus)\s+(\S+)\s*(.*?)\s*([가-힣][가-힣()]*)?$")
    sp_re = re.compile(r"^([A-Z][a-z]+ [a-z\-]+(?: [a-z\-]+)?)\s+(.*?)\s*([가-힣][가-힣()]*)?$")
    out, cur, cls = [], {}, None
    for raw in text.splitlines():
        line = re.sub(r"\s+", " ", raw).strip()
        if not line or re.fullmatch(r"\d+", line) or "척삭동물문" in line:
            continue
        m = rank_re.match(line)
        if m:
            rk, name, author, ko = m.groups()
            rk = rk.lower()
            if rk == "class":
                cls = name.upper()
            if cls not in ("REPTILIA", "AVES"):
                continue
            # 하위 계급은 지운다
            for r in RANKS[RANKS.index(rk):]:
                cur.pop(r, None)
            cur[rk] = name
            out.append(dict(rank=rk, sci=name, author=author or None, ko=ko, group=cls, lineage=dict(cur)))
            continue
        if cls in ("REPTILIA", "AVES"):
            m = sp_re.match(line)
            if m:
                sci, author, ko = m.groups()
                out.append(dict(rank="species", sci=sci, author=author or None, ko=ko, group=cls, lineage=dict(cur)))
    return out


# ---------- 조류 시트 ----------
FAM_RE = re.compile(r"^([A-Z][a-z]+idae)\b\s*(?:\(([^)]*)\))?")


def parse_birds(path):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    taxa = []
    skip = {"남극해 조류 번역", "남극해 조류 스플릿 정리", "캐나다 조류 번역", "상사조과"}
    for ws in wb.worksheets:
        rows = [r for r in ws.iter_rows(values_only=True) if any(c is not None for c in r)]
        if not rows:
            continue
        if ws.title == "과단위 번역":
            h = [clean(c) for c in rows[0]]
            props = {i: c.replace(" 제안", "") for i, c in enumerate(h) if c and c.endswith("제안")}
            for r in rows[1:]:
                sci = clean(cell(r, 2 - 1 + 1)) if False else clean(cell(r, h.index("과")))
                # '과' 열에는 목 이름이 있고 실제 과 학명은 다음 열에 있다
                order = clean(cell(r, h.index("과")))
                fam = clean(cell(r, h.index("과(일반명)")))
                en = clean(cell(r, h.index("과(국명)")))
                if not fam or not FAM_RE.match(fam):
                    continue
                p = {props[i]: clean(cell(r, i)) for i in props if clean(cell(r, i))}
                cons = clean(cell(r, max(props) + 1)) if props else None
                taxa.append(dict(group="AVES", rank="family", sci=fam, en=en, order=order,
                                 consensus=cons, proposals=p, rationale=None, sheet=ws.title))
            continue
        if ws.title in skip:
            continue
        h = [clean(c) for c in rows[0]]
        props = {i: c.replace(" 제안", "") for i, c in enumerate(h) if c and c.endswith("제안")}
        cons_i = 2
        cons_label = h[2]
        # 머리글이 비어 있는 열이 근거 열이다 (0~7 사이에서 처음 나오는 빈 머리글)
        why_i = next((i for i in range(3, 8) if i >= len(h) or h[i] is None), None)
        family = None
        for r in rows[1:]:
            first = clean(cell(r, 0))
            if not first:
                continue
            m = FAM_RE.match(first)
            if m:
                family = m.group(1)
                ko = m.group(2)
                taxa.append(dict(group="AVES", rank="family", sci=family, en=None, consensus=ko,
                                 proposals={}, rationale=None, sheet=ws.title, from_header=True))
                continue
            words = first.split()
            rank = "genus" if len(words) == 1 else "species" if len(words) == 2 else "subspecies"
            p = {props[i]: clean(cell(r, i)) for i in props if clean(cell(r, i))}
            taxa.append(dict(group="AVES", rank=rank, sci=first, family=family,
                             en=clean(cell(r, 1)), consensus=clean(cell(r, cons_i)),
                             consensus_label=cons_label, proposals=p,
                             rationale=clean(cell(r, why_i)), sheet=ws.title))
    return taxa


# ---------- 파충류 시트 ----------
def parse_reptiles(path):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    taxa = []
    for ws in wb.worksheets:
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            continue
        h = [clean(c) for c in rows[0]]
        if ws.title == "과단위 번역":
            order = None
            for r in rows[1:]:
                fam, sub, en, ko, why, ordr = (clean(cell(r, i)) for i in range(6))
                if ordr:
                    order = ordr
                if fam and not fam.endswith("idae") and not sub:
                    continue
                sci = sub if (sub and sub != "-") else fam
                if not sci or sci == "-":
                    continue
                rank = "subfamily" if (sub and sub != "-") else ("family" if sci.endswith("idae") else "order")
                taxa.append(dict(group="REPTILIA", rank=rank, sci=sci, en=en, consensus=ko,
                                 proposals={}, rationale=why, sheet=ws.title))
            continue
        if ws.title in ("통합목록", "지정관리종목록") or "명칭 제안" not in h:
            continue
        ix = {k: h.index(k) for k in ("학명", "환경부 지정명", "국내 통용/유통명", "명칭 제안", "명칭 근거", "Author") if k in h}
        family = None
        for r in rows[1:]:
            sci = clean(cell(r, ix["학명"]))
            if not sci:
                continue
            m = FAM_RE.match(sci)
            if m:
                family = m.group(1)
                continue
            rank = "genus" if len(sci.split()) == 1 else "species"
            taxa.append(dict(group="REPTILIA", rank=rank, sci=sci, family=family,
                             author=clean(cell(r, ix.get("Author"))),
                             moe=clean(cell(r, ix.get("환경부 지정명"))),
                             trade=clean(cell(r, ix.get("국내 통용/유통명"))),
                             consensus=clean(cell(r, ix["명칭 제안"])), proposals={},
                             rationale=clean(cell(r, ix["명칭 근거"])), sheet=ws.title))
    return taxa


# ---------- 한국조류목록 2025 ----------
def parse_kos(path):
    """한국조류학회 한국조류목록 2025(개정판 v2.1). IOC v15.1 학명."""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    out = []
    for tab, held in (("공식목록", False), ("(참고) 보류종", True)):
        rows = list(wb[tab].iter_rows(values_only=True))
        h = [clean(c).replace(" ", "") if clean(c) else None for c in rows[0]]
        ix = {k: h.index(k) for k in ("분류", "범주", "국명", "학명", "명명자", "영명")}
        for r in rows[1:]:
            rank = (clean(cell(r, ix["분류"])) or "").lower()
            sci = clean(cell(r, ix["학명"]))
            if rank in ("family", "order") and sci:
                sci = sci.split()[-1].capitalize()
                out.append(dict(group="AVES", rank=rank, sci=sci, ko=clean(cell(r, ix["국명"])),
                                author=None, en=clean(cell(r, ix["영명"])), category=None, held=held))
                continue
            if rank not in ("species", "ssp") or not sci:
                continue
            out.append(dict(group="AVES", rank="species" if rank == "species" else "subspecies",
                            sci=sci, ko=clean(cell(r, ix["국명"])), author=clean(cell(r, ix["명명자"])),
                            en=clean(cell(r, ix["영명"])), category=clean(cell(r, ix["범주"])), held=held))
    return out


class Linker:
    """다른 목록의 학명을 시트(eBird·Reptile Database) 학명에 잇는다."""

    def __init__(self, sheet):
        self.sheet = [t for t in sheet if t["rank"] == "species"]
        self.keys = {(t["group"], t["sci"]): t for t in sheet}
        self.by_ep, self.by_ko, self.by_stem = defaultdict(list), defaultdict(list), defaultdict(list)
        for t in self.sheet:
            ep = t["sci"].split()[-1]
            self.by_ep[(t["group"], ep)].append(t)
            self.by_stem[(t["group"], stem(ep))].append(t)
            for k in {k for v in [t.get("consensus"), t.get("moe"), *t["proposals"].values()] for k in ko_keys(v)}:
                self.by_ko[(t["group"], k)].append(t)

    def link(self, group, sci, ko, family=None):
        """(시트 분류군, 연결 방법, 후보 학명들)"""
        if (group, sci) in self.keys:
            return self.keys[(group, sci)], "학명 일치", []
        ep = sci.split()[-1]
        e, s = self.by_ep[(group, ep)], self.by_stem[(group, stem(ep))]
        steps = [
            ("국명 일치", self.by_ko[(group, norm(ko))] if ko else []),
            ("같은 과·종소명", [c for c in e if family and c.get("family") == family]),
            ("종소명", e),
            ("같은 과·종소명 어간", [c for c in s if family and c.get("family") == family]),
            ("종소명 어간", s),
        ]
        cands = sorted({c["sci"] for _, cs in steps for c in cs})
        for how, cs in steps:
            if len(cs) == 1:
                return cs[0], how, cands
        return None, None, cands


def pick_name(t):
    """국명 우선순위: 한국조류목록 2025 > 국가생물종목록 > 시트 합의본 > 일치하는 개인 제안 > 없음(영명)."""
    if t.get("kos") and not t["kos"].get("held"):
        return t["kos"]["ko"], "kos"
    if t.get("official"):
        return t["official"], "official"
    if t.get("consensus"):
        return norm(t["consensus"]) or t["consensus"], "consensus"
    if t["proposals"]:
        distinct = {norm(v) for v in t["proposals"].values()}
        if len(distinct) == 1:
            return next(iter(t["proposals"].values())), "proposal"
        return None, "split"
    if t.get("kos"):  # 보류종 국명은 마지막 참고로만
        return t["kos"]["ko"], "kos_held"
    return None, "none"


def main():
    nibr_path = DATA / "nibr.json"
    if PDF:
        nibr = parse_nibr(PDF)
        nibr_path.write_text(json.dumps(nibr, ensure_ascii=False, indent=1), encoding="utf-8")
    nibr = json.loads(nibr_path.read_text(encoding="utf-8"))
    ov = json.loads((DATA / "overrides.json").read_text(encoding="utf-8"))
    kos = parse_kos(DATA / "kos2025.xlsx")

    sheet = parse_birds(DATA / "birds.xlsx") + parse_reptiles(DATA / "reptiles.xlsx")
    by_key = {(t["group"], t["sci"]): t for t in sheet}
    linker = Linker(sheet)
    nibr_by = {(t["group"], t["sci"]): t for t in nibr}

    # --- 손으로 정한 것 먼저 ---
    manual = {}
    for o in ov.get("link", []):
        manual[(o["group"], o["nibr_sci"])] = ("link", o)
    for o in ov.get("keep", []):
        manual[(o["group"], o["nibr_sci"])] = ("keep", o)
    for o in ov.get("subspecies", []):
        manual[(o["group"], o["nibr_sci"])] = ("ssp", o)

    def add_ssp(parent_sci, group, entry):
        p = by_key.get((group, parent_sci))
        if p is None:
            return False
        lst = p.setdefault("subspecies", [])
        old = next((x for x in lst if x["sci"] == entry["sci"]), None)
        if old:
            # 국가생물종목록 국명은 지키고, 한국조류목록 이름은 kos_ko 로 따로 둔다
            if old.get("source") == "국가생물종목록" and entry.get("ko"):
                entry = dict(entry, kos_ko=entry.pop("ko"))
                entry.pop("source", None)
            old.update({k: v for k, v in entry.items() if v})
        else:
            lst.append(entry)
        return True

    # --- 국가생물종목록 → 시트 ---
    review = []
    for o in nibr:
        if o["rank"] != "species":
            t = by_key.get((o["group"], o["sci"]))
            if t and o["ko"]:
                t["official"] = o["ko"]
            continue
        key = (o["group"], o["sci"])
        fam = o["lineage"].get("family")
        rec = dict(group=o["group"], family=fam, nibr_sci=o["sci"], ko=o["ko"])
        if key in manual:
            kind, m = manual[key]
            if kind == "link":
                t = by_key[(o["group"], m["sci"])]
                t.update(official=o["ko"], nibr_sci=o["sci"], review=f"학명 불일치: 국가생물종목록 {o['sci']}")
                rec.update(sheet_sci=t["sci"], result="편집자 지정", how="학명 직접 지정")
            elif kind == "keep":
                repl = by_key.pop((o["group"], m["replaces"]), None) if m.get("replaces") else None
                t = dict(group=o["group"], rank="species", sci=o["sci"], family=fam, author=o["author"],
                         en=repl.get("en") if repl else None, consensus=None, proposals={}, rationale=None,
                         sheet="국가생물종목록", official=o["ko"], synonyms=[m["replaces"]] if repl else [],
                         review=m["note"])
                if repl:
                    sheet[sheet.index(repl)] = t
                else:
                    sheet.append(t)
                by_key[key] = t
                rec.update(sheet_sci=o["sci"], result="편집자 지정", how=m["note"])
            else:
                ok = add_ssp(m["parent"], o["group"], dict(sci=m["sci"], ko=o["ko"], source="국가생물종목록",
                                                            note=m["note"], nibr_sci=o["sci"]))
                rec.update(sheet_sci=m["sci"], result="편집자 지정" if ok else "후보 없음", how=m["note"])
            review.append(rec)
            continue
        if key in by_key:
            by_key[key]["official"] = o["ko"]
            continue
        t, how, cands = linker.link(o["group"], o["sci"], o["ko"], fam)
        if t:
            t.update(official=o["ko"], nibr_sci=o["sci"], review=f"학명 불일치: 국가생물종목록 {o['sci']}")
        review.append(dict(rec, sheet_sci=t["sci"] if t else None,
                           sheet_name=(t.get("consensus") or t.get("moe")) if t else None,
                           sheet_tab=t["sheet"] if t else None, how=how, candidates=cands,
                           result="자동 연결" if t else ("후보 여러 개" if cands else "후보 없음")))

    # --- 국가생물종목록 국명 vs 시트 이름: 종 분할로 국명이 옮겨간 경우 ---
    where = defaultdict(list)
    for t in sheet:
        for k in {k for v in [t.get("consensus"), *t["proposals"].values()] for k in ko_keys(v)}:
            where[(t["group"], k)].append(t["sci"])
    conflicts = []
    for t in list(sheet):
        o, c = t.get("official"), t.get("consensus") or next(iter(t["proposals"].values()), None)
        if not o or "moved" in t:
            continue
        own = {k for v in [t.get("consensus"), *t["proposals"].values()] for k in ko_keys(v)}
        if norm(o) in own or (c and norm(c) == norm(o)):
            continue
        other = [x for x in where[(t["group"], norm(o))] if x != t["sci"]]
        if not c and not other:
            continue
        conflicts.append(dict(group=t["group"], rank=t["rank"], sci=t["sci"], official=o, sheet=c, moved_to=other))
        if len(other) == 1:
            dst = by_key[(t["group"], other[0])]
            dst.update(official=o, moved=True, review=f"분류 변경: 국가생물종목록에서는 {t['sci']}")
            t.update(official=None, moved=True, review=f"분류 변경: 국가생물종목록 국명 {o} → {other[0]}")

    # --- 한국조류목록 2025 → 시트 (조류만) ---
    kos_rows = []
    for k in kos:
        if k["rank"] in ("family", "order"):
            t = by_key.get(("AVES", k["sci"]))
            if t and k["ko"] and not k["held"]:
                t["kos"] = dict(sci=k["sci"], ko=k["ko"], category=None, held=False)
            continue
        if k["rank"] == "subspecies":
            parent = " ".join(k["sci"].split()[:2])
            pt, _, _ = linker.link("AVES", parent, None)
            if pt and pt["sci"] != parent:
                pt = None
            ptk = by_key.get(("AVES", parent))
            if ptk and k["ko"]:
                add_ssp(parent, "AVES", dict(sci=k["sci"], ko=k["ko"], source="한국조류목록 2025"))
            continue
        m = manual.get(("AVES", k["sci"]))
        if m and m[0] == "ssp":  # IOC 종이 eBird에서는 아종으로 합쳐진 경우
            add_ssp(m[1]["parent"], "AVES", dict(sci=m[1]["sci"], kos_ko=k["ko"]))
            kos_rows.append(dict(kos_sci=k["sci"], ko=k["ko"], category=k["category"], held=k["held"],
                                 sheet_sci=m[1]["sci"], how="아종 단위 통합", candidates=[]))
            continue
        if ("AVES", k["sci"]) in by_key:
            t, how, cands = by_key[("AVES", k["sci"])], "학명 일치", []
        else:
            t, how, cands = linker.link("AVES", k["sci"], k["ko"])
        row = dict(kos_sci=k["sci"], ko=k["ko"], category=k["category"], held=k["held"],
                   sheet_sci=t["sci"] if t else None, how=how, candidates=cands)
        if t:
            if "kos" not in t or how == "학명 일치":
                t["kos"] = dict(sci=k["sci"], ko=k["ko"], category=k["category"], held=k["held"])
            row.update(official=t.get("official"), sheet=t.get("consensus"))
        kos_rows.append(row)
    # 한국조류목록의 종이 아종 하나로만 기록됐고 그 아종이 시트에서 독립 종이면 국명을 그 종으로 옮긴다
    # (예: Gygis alba candida → 시트의 Gygis candida)
    kos_ssp = defaultdict(list)
    for k in kos:
        if k["rank"] in ("family", "order"):
            t = by_key.get(("AVES", k["sci"]))
            if t and k["ko"] and not k["held"]:
                t["kos"] = dict(sci=k["sci"], ko=k["ko"], category=None, held=False)
            continue
        if k["rank"] == "subspecies":
            kos_ssp[" ".join(k["sci"].split()[:2])].append(k)
    for t in list(sheet):
        k = t.get("kos")
        if not k or k.get("sci") != t["sci"] or len(kos_ssp[t["sci"]]) != 1:
            continue
        ssp = kos_ssp[t["sci"]][0]
        g, _, e = ssp["sci"].split()
        dst = by_key.get(("AVES", f"{g} {e}"))
        if dst and dst is not t and not dst.get("kos"):
            dst["kos"] = dict(k, sci=ssp["sci"])
            dst["review"] = f"분류 변경: 한국조류목록 2025에서는 {ssp['sci']}"
            t["kos_ref"] = t.pop("kos")
            t["review"] = f"분류 변경: 한국조류목록 2025 국명 {k['ko']} → {dst['sci']}"
    # 하위 아종에 '아종 단위 통합'으로 붙인 국명은 한국조류목록 아종명과 비교해 둔다
    for t in sheet:
        for s in t.get("subspecies", []):
            s.setdefault("source", "한국조류목록 2025")

    # --- 국명 확정 ---
    stat = Counter()
    # 다른 분류군의 공식 국명과 겹치면 한국조류목록 이름으로 채우지 않는다(종 분할 뒤 중복 방지)
    # 한국조류목록 2025 국명이 다른 분류군에 이미 쓰였으면, 그 국가생물종목록 국명은 쓰지 않는다
    kos_taken = {(t["group"], norm(t["kos"]["ko"])): t["sci"] for t in sheet if t.get("kos") and not t["kos"].get("held")}
    for t in sheet:
        o = t.get("official")
        if o and not t.get("kos") and kos_taken.get((t["group"], norm(o)), t["sci"]) != t["sci"]:
            t["official_ref"] = o
            t["official"] = None
        t["name"], t["status"] = pick_name(t)
    # 개인 제안 국명이 다른 종과 겹치면 그 제안은 국명으로 쓰지 않는다(영명 표시)
    used = Counter((t["group"], norm(t["name"])) for t in sheet if t["name"] and t["rank"] == "species")
    for t in sheet:
        if t["status"] in ("proposal", "kos_held") and t["rank"] == "species" and used[(t["group"], norm(t["name"]))] > 1:
            t["name"], t["status"] = None, "none"
            t["proposals_hidden"] = True
    for t in sheet:
        stat[(t["group"], t["rank"], t["status"])] += 1
    # 아종: 한국조류목록 2025 이름이 있으면 그것을 먼저
    for t in sheet:
        for s_ in t.get("subspecies", []):
            if s_.get("kos_ko"):
                s_["nibr_ko"], s_["ko"] = s_.get("ko"), s_["kos_ko"]

    kos_diff = [r for r in kos_rows if r["sheet_sci"] and r.get("official") and norm(r["official"]) != norm(r["ko"])]
    kos_used = [r for r in kos_rows if r["sheet_sci"] and not r.get("official") and not r["held"]
                and by_key.get(("AVES", r["sheet_sci"]), {}).get("status") == "kos"]
    kos_unlinked = [r for r in kos_rows if not r["sheet_sci"]]
    (DATA / "names.json").write_text(json.dumps(sheet, ensure_ascii=False, indent=1), encoding="utf-8")
    (DATA / "review.json").write_text(json.dumps(review, ensure_ascii=False, indent=1), encoding="utf-8")
    (DATA / "conflicts.json").write_text(json.dumps(conflicts, ensure_ascii=False, indent=1), encoding="utf-8")
    (DATA / "kos.json").write_text(json.dumps(dict(diff=kos_diff, used=kos_used, unlinked=kos_unlinked),
                                              ensure_ascii=False, indent=1), encoding="utf-8")

    rep = ["== 계급·상태별 개수 =="] + [f"{k[0]:9} {k[1]:10} {k[2]:10} {stat[k]}" for k in sorted(stat)]
    rc = Counter(r["result"] for r in review)
    rep.append(f"\n학명 불일치 {len(review)}건: " + ", ".join(f"{k} {v}" for k, v in rc.items()))
    rep.append(f"국명 차이 {len(conflicts)}건 (분류 변경 {sum(1 for c in conflicts if len(c['moved_to']) == 1)})")
    rep.append(f"한국조류목록 2025: 연결 {len(kos_rows) - len(kos_unlinked)} / 못 이음 {len(kos_unlinked)} · "
               f"국가생물종목록과 국명 다름 {len(kos_diff)} · 빈 국명 채움 {len(kos_used)}")
    rep += [f"  못 이음: {r['kos_sci']} {r['ko']} 후보 {r['candidates'][:4]}" for r in kos_unlinked]
    (DATA / "report.txt").write_text("\n".join(rep), encoding="utf-8")
    print("\n".join(rep))


if __name__ == "__main__":
    main()
