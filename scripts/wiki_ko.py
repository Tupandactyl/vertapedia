"""영문 위키백과 본문의 한국어 번역 작업 도구. 결과는 data/wiki_ko/<학명>.json (사이트 생성 때 종 문서에 들어간다).

    python scripts/wiki_ko.py prep 학명1 학명2 ...   # 번역할 입력 만들기(translation_review/in/)
    python scripts/wiki_ko.py prep --korea           # 한국 기록종 가운데 아직 번역하지 않은 모든 종
    python scripts/wiki_ko.py check                  # 번역본 검사 후 합치기(translation_review/out/ → data/wiki_ko/)

- 전문을 옮긴다. 일부만 번역된 문서는 빠진 문단만 <학명>.add 입력으로 만든다.
- 긴 문서는 나눠 <이름>.part1.json 처럼 저장해도 check 가 한 문서로 합친다.
- 번역본은 원문 판과 함께 따로 두므로, 위키 원문이 갱신되어도 그대로 보여 줄 수 있다.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
IN, OUT, FINAL = ROOT / "translation_review" / "in", ROOT / "translation_review" / "out", DATA / "wiki_ko"
BATCH = 75000  # 한 묶음 원문 글자 수
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


def merged(stem):
    """out/<학명>.json 과 조각(<학명>.part1.json, <학명>.add.part1.json ...)을 하나로"""
    tr = dict(ko={}, heads={}, notes=[], omit=[])
    for f in sorted(OUT.glob(stem + "*.json")):
        if f.stem != stem and not f.stem.startswith(stem + "."):
            continue
        d = json.loads(f.read_text(encoding="utf-8"))
        tr["ko"].update(d.get("ko", {}))
        tr["heads"].update(d.get("heads", {}))
        tr["notes"] += d.get("notes", [])
        tr["omit"] += d.get("omit", [])
        tr["date"] = d.get("date") or tr.get("date")
    return tr


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
        keep = set(range(len(secs)))
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
        stem, have = sci.replace(" ", "_"), merged(sci.replace(" ", "_"))
        if have["ko"]:  # 일부만 번역된 문서: 빠진 문단만 따로
            todo = {k: v for k, v in paras.items() if k not in have["ko"] and k not in have["omit"]}
            hd = {k: v for k, v in heads.items() if k not in have["heads"]}
            if not todo and not hd:
                continue
            (IN / f"{stem}.add.json").write_text(json.dumps(dict(rec, paras=todo, heads=hd), ensure_ascii=False, indent=1), encoding="utf-8")
            stem += ".add"
            paras = todo
        report.append((stem, sum(len(p) for p in paras.values())))
    # 묶음 나누기: 분량이 고르도록
    bins = []
    for stem, c in sorted(report, key=lambda r: -r[1]):
        b = next((x for x in bins if x[0] + c <= BATCH), None)
        if not b:
            b = [0, []]
            bins.append(b)
        b[0] += c
        b[1].append(stem)
    (ROOT / "translation_review" / "batches.json").write_text(json.dumps([dict(chars=c, items=L) for c, L in bins], ensure_ascii=False, indent=0), encoding="utf-8")
    print("묶음", len(bins), "· 문서", len(report), "· 합계", sum(c for _, c in report), "· 가장 큰 묶음", max((c for c, _ in bins), default=0))


def check():
    FINAL.mkdir(parents=True, exist_ok=True)
    bad = ok = 0
    for f in sorted({OUT / (x.name.split(".")[0] + ".json") for x in OUT.glob("*.json")}):
        sci = f.stem.replace("_", " ")
        src = load(IN / f.name)
        if src is None:  # 처음 10종처럼 입력 파일이 없으면 만들어 둔 번역본을 그대로 검사
            print("입력 없음:", f.name)
            bad += 1
            continue
        tr = merged(f.stem)
        errs = []
        ko, heads, notes = tr.get("ko", {}), tr.get("heads", {}), tr.get("notes", [])
        # omit: 일부러 뺀 문단(끊긴 문단을 앞 문단에 합쳤거나, 다른 문서를 가리키기만 하는 문장)
        src["paras"] = {k: v for k, v in src["paras"].items() if k not in tr.get("omit", [])}
        missing = [k for k in src["paras"] if not (ko.get(k) or "").strip()]
        # 작업 중인 문서: 옮긴 절만 싣고 나머지는 옮기지 않은 절로 적는다(첫 문단은 있어야 한다)
        partial = "--partial" in sys.argv and missing and "0.0" in ko
        if partial:
            gone = {int(k.split(".")[0]) for k in missing}
            src["skipped"] = [src["heads"][str(i)] for i in sorted(gone) if str(i) in src["heads"]]
            src["paras"] = {k: v for k, v in src["paras"].items() if k not in missing}
            src["heads"] = {k: v for k, v in src["heads"].items() if k in heads}
            notes = [n for n in notes if n.get("ref") in ko]
            ko = {k: v for k, v in ko.items() if k in src["paras"]}
            notes = [n for n in notes if n.get("ref") in ko]
        else:
            errs += [f"문단 없음 {k}" for k in missing]
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
        if "--korea" in sys.argv:
            ksci = {k.get("sheet_sci") for k in load(DATA / "kshr.json", [])}
            names = [t["sci"] for t in load(DATA / "names.json", []) if t.get("rank") == "species" and (t.get("kos") or t["sci"] in ksci)]
            prep([s for s in names if wiki_of(s).get("sections")])
        else:
            prep([a for a in sys.argv[2:] if not a.startswith("--")])
    else:
        check()
