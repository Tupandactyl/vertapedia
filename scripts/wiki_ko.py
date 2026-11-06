"""영문 위키백과 본문의 한국어 번역 작업 도구. 결과는 data/wiki_ko/<학명>.json (사이트 생성 때 종 문서에 들어간다).

    python scripts/wiki_ko.py prep 학명1 학명2 ...   # 번역할 입력 만들기(translation_review/in/)
    python scripts/wiki_ko.py check                  # 번역본 검사 후 합치기(translation_review/out/ → data/wiki_ko/)

- 문서가 1만 자를 넘으면 핵심 절(한국, 형태, 분포, 분류, 생태, 보전 순)만 1만 자 안에서 고른다. 머리 문단은 늘 넣는다.
- 번역본은 원문 판과 함께 따로 두므로, 위키 원문이 갱신되어도 그대로 보여 줄 수 있다.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
IN, OUT, FINAL = ROOT / "translation_review" / "in", ROOT / "translation_review" / "out", DATA / "wiki_ko"
CAP = 10000
PRIORITY = [r"korea", r"descri|appearance|morpholog|identif|plumage|anatomy", r"distribut|range|habitat", r"taxonom|systematic|subspecies|etymolog|name",
            r"behav|ecolog|diet|feed|food|breed|reprodu|nest|life", r"conserv|status|threat", r"voice|song|call|vocal|migrat"]
# 숫자 대조에서 빼는 야드파운드 병기
IMPERIAL = re.compile(r"\([^()]*\b(?:in|ft|lb|mi|oz|yd|sq mi|mph|acres?|°F)\b[^()]*\)")
NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")
PUBLIC = ("수정", "확인 필요")
TYPES = PUBLIC + ("번역 메모",)


def load(p, default=None):
    p = Path(p)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def fname(sci):
    return sci.replace(" ", "_") + ".json"


def wiki_of(sci):
    return (load(DATA / "media" / fname(sci), {}) or {}).get("wiki") or {}


def seclen(s):
    return sum(len(p) for p in s.get("paras", []))


def choose(secs):
    """번역할 절 번호. 1만 자 이하면 전부"""
    if sum(seclen(s) for s in secs) <= CAP:
        return set(range(len(secs)))
    rank = lambda s: next((i for i, r in enumerate(PRIORITY) if re.search(r, (s.get("h") or "").lower())), len(PRIORITY))
    keep, used = {0}, seclen(secs[0])
    for i in sorted(range(1, len(secs)), key=lambda i: (rank(secs[i]), i)):
        if used + seclen(secs[i]) <= CAP:
            keep.add(i)
            used += seclen(secs[i])
    return keep


def prep(names):
    sys.path.insert(0, str(ROOT / "scripts"))
    from ko_link import Linker

    IN.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    all_names = json.loads((DATA / "names.json").read_text(encoding="utf-8"))
    by = {t["sci"]: t for t in all_names}
    linker = Linker(all_names)
    dist, bird_iucn, rng, auth = load(DATA / "distribution.json", {}), load(DATA / "bird_iucn.json", {}), load(DATA / "bird_range.json", {}), load(DATA / "bird_authority.json", {})
    report = []
    for sci in names:
        t, w = by[sci], wiki_of(sci)
        secs = w.get("sections") or []
        keep = choose(secs)
        gloss, seen, paras, heads = {}, set(), {}, {}
        for i, s in enumerate(secs):
            if i not in keep:
                continue
            if s.get("h"):
                heads[str(i)] = s["h"]
            for j, p in enumerate(s["paras"]):
                paras[f"{i}.{j}"] = p
                linked = linker.paragraph(p, seen)
                for x in [] if isinstance(linked, str) else linked:
                    if isinstance(x, list):
                        gloss[x[1]] = f"{x[0]} ({x[3]})"
        rec = dict(sci=sci, ko=t.get("name"), group=t["group"], title=w.get("title"), url=w.get("url"), revision=w.get("revision"),
                   site_facts=dict(iucn=bird_iucn.get(sci) if t["group"] == "AVES" else (dist.get(sci) or {}).get("iucn"),
                                   avilist_range=rng.get(sci), authority=auth.get(sci), kos=t.get("kos"),
                                   subspecies=[s.get("sci") for s in t.get("subspecies") or []],
                                   gbif_korea_records=((dist.get(sci) or {}).get("c") or {}).get("KR")),
                   glossary=gloss, heads=heads, paras=paras,
                   skipped=[s.get("h") for i, s in enumerate(secs) if i not in keep and s.get("h")])
        (IN / fname(sci)).write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
        report.append((sci, sum(len(p) for p in paras.values())))
    # 묶음 나누기: 분량이 고르도록
    n = int(sys.argv[sys.argv.index("--batches") + 1]) if "--batches" in sys.argv else 1
    bins = [[0, []] for _ in range(n)]
    for sci, c in sorted(report, key=lambda r: -r[1]):
        b = min(bins, key=lambda x: x[0])
        b[0] += c
        b[1].append(sci)
    for i, (c, L) in enumerate(bins, 1):
        print(f"묶음 {i}: {c}자 {len(L)}종 | " + ", ".join(L))
    print("합계", sum(c for _, c in report))


def check():
    FINAL.mkdir(parents=True, exist_ok=True)
    bad = ok = 0
    for f in sorted(OUT.glob("*.json")):
        sci = f.stem.replace("_", " ")
        src = load(IN / f.name)
        if src is None:  # 처음 10종처럼 입력 파일이 없으면 만들어 둔 번역본을 그대로 검사
            print("입력 없음:", f.name)
            bad += 1
            continue
        tr = json.loads(f.read_text(encoding="utf-8"))
        errs = []
        ko, heads, notes = tr.get("ko", {}), tr.get("heads", {}), tr.get("notes", [])
        # omit: 일부러 뺀 문단(끊긴 문단을 앞 문단에 합쳤거나, 다른 문서를 가리키기만 하는 문장)
        src["paras"] = {k: v for k, v in src["paras"].items() if k not in tr.get("omit", [])}
        errs += [f"문단 없음 {k}" for k in src["paras"] if not (ko.get(k) or "").strip()]
        errs += [f"남는 문단 {k}" for k in ko if k not in src["paras"]]
        errs += [f"제목 없음 {k}" for k in src["heads"] if not (heads.get(k) or "").strip()]
        errs += [f"주석 종류 {n.get('type')}" for n in notes if n.get("type") not in TYPES]
        errs += [f"주석 위치 {n.get('ref')}" for n in notes if n.get("ref") not in ko]
        warn = []
        for k, p in src["paras"].items():
            for num in NUM.findall(IMPERIAL.sub("", p)):
                num = num.rstrip(",")
                if num not in ko.get(k, "") and num.replace(",", "") not in ko.get(k, "").replace(",", ""):
                    warn.append(f"{k}:{num}")
            if len(p) > 80 and len(ko.get(k, "")) < len(p) * 0.25:
                warn.append(f"{k}:짧음")
            if re.search(r"[A-Za-z]{4,} [a-z]{4,} [a-z]{4,} [a-z]{4,}", re.sub(r"\*[^*]+\*", "", ko.get(k, ""))):
                warn.append(f"{k}:영어 문장?")
        if errs:
            bad += 1
            print("오류", sci, errs[:8])
            continue
        secs_by = {}
        for k in src["paras"]:
            secs_by.setdefault(int(k.split(".")[0]), []).append(k)
        w = wiki_of(sci)
        levels = [s.get("level") for s in w.get("sections") or []]
        sections = [dict(h=heads.get(str(i)), en=src["heads"].get(str(i)), level=levels[i] if i < len(levels) else 2,
                         paras=[dict(ref=k, text=ko[k]) for k in refs]) for i, refs in sorted(secs_by.items())]
        final = dict(sci=sci, title=src["title"], url=src["url"], revision=src["revision"], translator="Claude", date=tr.get("date") or "2026-11-06",
                     sections=sections, skipped=src.get("skipped") or [], notes=notes)
        (FINAL / f.name).write_text(json.dumps(final, ensure_ascii=False, indent=1), encoding="utf-8")
        ok += 1
        if warn:
            print("확인", sci, warn[:12])
    print(f"합침 {ok} · 오류 {bad}")


if __name__ == "__main__":
    if sys.argv[1] == "prep":
        prep([a for a in sys.argv[2:] if not a.startswith("--") and not a.isdigit()])
    else:
        check()
