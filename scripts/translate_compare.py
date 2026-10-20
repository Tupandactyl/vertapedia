"""번역 시험 비교.

1) 사람이(또는 대화에서) 옮긴 번역문 텍스트 → data/translations/<학명>.claude.json
   형식:  ##### 학명 / === [절번호] 제목 번역 / [절.문단] 번역문(자리표시 [[N0]] 그대로)
2) data/translations/ 의 엔진별 결과를 원문과 나란히 놓은 data/translation_trial/compare.html

    python scripts/translate_compare.py import 번역.txt claude
    python scripts/translate_compare.py page
"""
import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ko_link import Linker  # noqa: E402
from translate import DATA, OUT, check, protect, restore  # noqa: E402


def do_import(txt, engine):
    linker = Linker(json.loads((DATA / "names.json").read_text(encoding="utf-8")))
    cur, heads, paras = None, {}, {}
    blocks = {}
    for line in Path(txt).read_text(encoding="utf-8").splitlines():
        if line.startswith("##### "):
            cur = line[6:].strip()
            blocks[cur] = (heads := {}, paras := {})
        elif m := re.match(r"^=== \[(\d+)\]\s*(.*)$", line):
            heads[int(m.group(1))] = m.group(2).strip()
        elif m := re.match(r"^\[(\d+)\.(\d+)\]\s*(.*)$", line):
            paras[(int(m.group(1)), int(m.group(2)))] = m.group(3).strip()
    for sci, (heads, paras) in blocks.items():
        m = json.loads((DATA / "media" / f"{sci}.json").read_text(encoding="utf-8"))
        w = linker.wiki(m["wiki"])
        secs = []
        for si, s in enumerate(w["sections"]):
            ps = []
            for pi, p in enumerate(s["paras"]):
                src, back = protect(p)
                ko = paras.get((si, pi), "")
                ps.append(dict(en=src, ko=restore(ko, back), raw=ko, issues=check(src, ko, back) if ko else ["번역 없음"]))
            secs.append(dict(h=s["h"], h_ko=heads.get(si) or s["h"], level=s["level"], paras=ps))
        rec = dict(sci=m["sci"], title=w["title"], revision=w.get("revision"), engine=engine, sections=secs)
        (OUT / f"{sci}.{engine}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
        print(sci, "→", f"{sci}.{engine}.json")


def page():
    names = {t["sci"]: t for t in json.loads((DATA / "names.json").read_text(encoding="utf-8")) if t["rank"] == "species"}
    linker = Linker(json.loads((DATA / "names.json").read_text(encoding="utf-8")))
    runs, backs = {}, {}
    for f in sorted(OUT.glob("*.json")):
        sci, eng = f.stem.split(".", 1)
        rec = json.loads(f.read_text(encoding="utf-8"))
        # 조사 맞춤·검사를 지금 규칙으로 다시(번역문 raw 는 그대로)
        if sci not in backs:
            w = linker.wiki(json.loads((DATA / "media" / f"{sci}.json").read_text(encoding="utf-8"))["wiki"])
            backs[sci] = [[protect(p)[1] for p in sec["paras"]] for sec in w["sections"]]
        for si, sec in enumerate(rec["sections"]):
            for pi, p in enumerate(sec["paras"]):
                back = backs[sci][si][pi]
                if p.get("raw"):
                    p["ko"] = restore(p["raw"], back)
                    p["issues"] = check(p["en"], p["raw"], back)
        f.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
        runs.setdefault(sci, {})[eng] = rec
    engines = sorted({e for r in runs.values() for e in r}, key=lambda e: (e != "claude", e))
    label = {"claude": "Claude (이 대화)", "exaone3.5_7.8b": "EXAONE 3.5 7.8B (이 PC, 무료)"}
    md = lambda t: html.escape(t or "").replace("*", "")  # 학명 표시용 * 는 뺀다
    out = []
    stat = []
    for sci, by in runs.items():
        base = next(iter(by.values()))
        t = names.get(sci.replace("_", " "), {})
        out.append(f'<section class="art"><h2>{html.escape(t.get("name") or "")} <i>{html.escape(sci.replace("_", " "))}</i>'
                   f' <small>{html.escape(base["title"])}</small></h2>')
        for e, r in by.items():
            if r.get("seconds"):
                stat.append((sci, e, r["seconds"], r.get("tokens", 0)))
        for si, s in enumerate(base["sections"]):
            hs = " · ".join(html.escape(by[e]["sections"][si].get("h_ko") or "") for e in engines if e in by)
            if s["h"]:
                out.append(f'<h3>{html.escape(s["h"])} <small>{hs}</small></h3>')
            for pi, p in enumerate(s["paras"]):
                cells = [f'<td class="en">{md(p["en"])}</td>']
                for e in engines:
                    if e not in by:
                        cells.append('<td class="na">—</td>')
                        continue
                    q = by[e]["sections"][si]["paras"][pi]
                    iss = "".join(f'<span class="iss">{html.escape(x)}</span>' for x in q.get("issues", []))
                    cells.append(f'<td>{md(q["ko"])}{iss}</td>')
                out.append("<table><tr>" + "".join(cells) + "</tr></table>")
        out.append("</section>")
    head = "".join(f"<th>{label.get(e, e)}</th>" for e in engines)
    st = "".join(f"<li>{html.escape(s.replace('_', ' '))}: {e} {sec // 60}분 {sec % 60}초, {tok:,}토큰</li>" for s, e, sec, tok in stat)
    doc = f"""<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>번역 시험 비교</title>
<style>
:root{{--bg:#f6f7f5;--ink:#1d2621;--muted:#5d6b63;--line:#d8ddd8;--card:#fff;--warn:#9a4b00;--warn-bg:#fff1e0}}
@media (prefers-color-scheme:dark){{:root{{--bg:#141a17;--ink:#e4ebe6;--muted:#9aa9a0;--line:#2b3530;--card:#1b221e;--warn:#ffb36b;--warn-bg:#3a2a18}}}}
body{{background:var(--bg);color:var(--ink);font-family:"IBM Plex Sans KR","Malgun Gothic",system-ui,sans-serif;margin:0;padding:16px;line-height:1.65}}
h1{{font-size:22px}} h2{{font-size:18px;margin-top:40px}} h2 small,h3 small{{color:var(--muted);font-weight:400;font-size:13px}} h3{{font-size:15px;margin:22px 0 6px}}
.legend{{display:grid;grid-template-columns:repeat({1 + len(engines)},1fr);gap:8px;position:sticky;top:0;background:var(--bg);padding:8px 0;font-weight:600;font-size:13px;border-bottom:1px solid var(--line)}}
table{{width:100%;table-layout:fixed;border-collapse:separate;border-spacing:8px 0;margin:0 -8px 8px}}
td{{vertical-align:top;background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px 12px;font-size:14px}}
td.en{{color:var(--muted)}} td.na{{color:var(--muted);text-align:center}}
.iss{{display:inline-block;margin:6px 6px 0 0;font-size:11px;padding:1px 6px;border-radius:999px;background:var(--warn-bg);color:var(--warn)}}
@media (max-width:760px){{table,tbody,tr,td{{display:block}} td{{margin-bottom:6px}} .legend{{display:none}}}}
</style><body>
<h1>위키 번역 시험 비교</h1>
<p>같은 원문을 엔진별로 옮긴 결과입니다. 생물 이름은 번역 전에 자리표시로 바꿨다가 버타피디아 국명으로 되돌렸습니다.
주황 표시는 자동 검사에서 걸린 곳(이름·숫자 빠짐, 길이 이상)입니다.</p>
<ul>{st}</ul>
<div class="legend"><div>원문</div>{"".join(f"<div>{label.get(e, e)}</div>" for e in engines)}</div>
{"".join(out)}
</body></html>"""
    d = DATA / "translation_trial"
    d.mkdir(exist_ok=True)
    (d / "compare.html").write_text(doc, encoding="utf-8")
    print("→", d / "compare.html")


if __name__ == "__main__":
    if sys.argv[1] == "import":
        do_import(sys.argv[2], sys.argv[3])
    else:
        page()
