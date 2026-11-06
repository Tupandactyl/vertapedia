"""국명 부여 기준 페이지(site/review.html): 편집 지침 전문, 분류 변동이 있는 종, 번역문에 반영한 국명 변경, 참고문헌."""
import html
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SITE = ROOT / "site"
load = lambda name, default=None: json.loads((DATA / name).read_text(encoding="utf-8")) if (DATA / name).exists() else default
e = html.escape


def guideline():
    """지침 원문(data/naming_guideline.md) → (HTML, 조 목차)"""
    lines = (DATA / "naming_guideline.md").read_text(encoding="utf-8").splitlines()
    body, toc = [], []
    for raw in lines[1:]:
        line = raw.strip()
        if not line:
            continue
        m = re.fullmatch(r"제(\d+)조 \((.+)\)", line)
        if m:
            if toc:
                body.append("</section>")
            toc.append(f'<a href="#a{m[1]}">제{m[1]}조 {e(m[2])}</a>')
            body.append(f'<section id="a{m[1]}"><h3>제{m[1]}조 <span>{e(m[2])}</span></h3>')
        elif re.match(r"[가나다라]\. ", line):
            body.append(f'<p class="rank">{e(line)}</p>')
        elif raw.startswith("  "):
            body.append(f'<p class="item">{e(line)}</p>')
        elif line[0] in "①②③④⑤":
            body.append(f'<p class="clause">{e(line)}</p>')
        else:
            body.append(f"<p>{e(line)}</p>")
    return "\n".join(body) + "</section>", "\n".join(toc)


def kind(src, dst):
    if len(dst.split()) == 3:
        return "아종으로 수록"
    return "속 이동" if src.split()[1][:4] == dst.split()[1][:4] else "분류 변동"


rows = []
for r in load("kos.json", {}).get("changed", []):
    rows.append(("조류", "한국조류목록", r["kos_sci"], r["ko"], r["sheet_sci"], kind(r["kos_sci"], r["sheet_sci"])))
for r in load("kshr.json", []):
    if r["sheet_sci"] and r["sheet_sci"] != r["kshr_sci"]:
        rows.append(("파충류", "양서파충류학회", r["kshr_sci"], r["ko"], r["sheet_sci"], "아종으로 수록" if len(r["kshr_sci"].split()) == 3 else kind(r["kshr_sci"], r["sheet_sci"])))
rdb = load("rdb.json", {})
for r in rdb.get("merged", []):
    rows.append(("파충류", "시트", r["old"], r.get("name") or "", r.get("ssp") or r["into"], "아종으로 통합" if r.get("ssp") else "다른 종에 통합"))
for r in rdb.get("renamed", []):
    rows.append(("파충류", "시트", r["old"], r.get("name") or "", r["new"], kind(r["old"], r["new"])))
for r in rdb.get("dropped", []):  # 시트에서 지워야 할 종이 새로 생기면 보인다
    rows.append(("파충류", "시트", r["sci"], r.get("name") or "", "—", "Reptile Database 목록에 없음"))
table = "\n".join(f'<tr><td>{g}</td><td><i>{e(a)}</i><small>{s}</small></td><td class="ko">{e(k)}</td><td><i>{e(b)}</i></td><td>{e(n)}</td></tr>'
                  for g, s, a, k, b, n in rows)

# 번역문에 자동 반영한 국명 변경: 같은 변경은 문서 수로 묶는다
changes, ambiguous = {}, []
for c in load("name_changes.json", []):
    if c.get("new"):
        changes[(c["old"], c["new"])] = changes.get((c["old"], c["new"]), 0) + 1
    else:
        ambiguous.append(c)
italic = lambda s: re.sub(r"\*([^*]+)\*", r"<i>\1</i>", e(s))
change_rows = "\n".join(f"<tr><td>{e(o)}</td><td>{italic(n)}</td><td>{c}</td></tr>" for (o, n), c in sorted(changes.items()))
changes_html = (f'<table><thead><tr><th>번역 당시</th><th>지금</th><th>문서</th></tr></thead><tbody>{change_rows}</tbody></table>'
                if changes else "<p>아직 없습니다.</p>")
if ambiguous:
    changes_html += "<p class=\"warn\">자동으로 바꾸지 못한 이름(같은 문서의 다른 종이 지금 쓰는 이름): " + ", ".join(f"{e(c['old'])} · <i>{e(c['doc'])}</i>" for c in ambiguous) + "</p>"

refs = "\n".join(f'<li>{e(r["text"])}{f" <a href=\"{e(r["url"])}\">↗</a>" if r.get("url") else ""}<small>{e(r["use"])}</small></li>'
                 for r in load("references.json", []) if r["id"] != "ebird")
body, toc = guideline()
built = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M KST")
out = (SITE / "review.template.html").read_text(encoding="utf-8")
for key, val in dict(GUIDELINE=body, TOC=toc, ROWS=table, NROWS=str(len(rows)), CHANGES=changes_html, REFS=refs, BUILT=built).items():
    out = out.replace("{{" + key + "}}", val)
(SITE / "review.html").write_text(out, encoding="utf-8")
print("site/review.html", len(out) // 1024, "KB · 분류 변동", len(rows), "· 국명 변경", len(changes))
