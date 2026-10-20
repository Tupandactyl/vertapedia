"""Reptile Database 종 목록을 받는다.

- data/rdb_live.json      : 웹사이트의 현재 전체 종 목록(학명·명명자). 학명의 기준.
                            웹은 수시로 고쳐지고, 내려받는 checklist는 1년에 두세 번만 나온다.
- data/rdb_checklist.xlsx : 내려받는 최신 checklist. 과·목·아종은 여기서 가져온다.

    python scripts/fetch_rdb.py            # 둘 다
    python scripts/fetch_rdb.py --live     # 웹 목록만
    python scripts/fetch_rdb.py --subfamilies  # 속 → 아과 (data/rdb_subfamily.json)
"""
import html
import json
import re
import sys
import time
import urllib.request
from datetime import date
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
BASE = "http://www.reptile-database.org/data/"
UA = {"User-Agent": "Vertapedia/0.1 (https://github.com/Tupandactyl/vertapedia)"}


LIVE = "https://reptile-database.reptarium.cz/advanced_search?synonym=x&submit=Search"  # 조건 없는 검색 = 모든 종


def get(url):
    for attempt in range(10):  # 서버가 자주 503을 낸다
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=300).read().decode("utf-8", "replace")
        except Exception as e:
            print("다시 시도:", e)
            time.sleep(15)
    raise SystemExit("Reptile Database에서 받지 못했습니다: " + url)


def checklist_genera():
    f = DATA / "rdb_checklist.xlsx"
    if not f.exists():
        return set()
    import openpyxl
    ws = openpyxl.load_workbook(f, read_only=True)["Checklist"]
    return {str(r[1]).split()[0] for r in list(ws.iter_rows(values_only=True))[1:] if r[1]}


def higher_taxa(genera):
    """checklist에 없는 속 {속: 대표 종}: 종 문서의 Higher Taxa 줄에서 과와 목(Sauria/Serpentes 등)을 읽는다."""
    out = {}
    for genus, s in sorted(genera.items()):
        g, e = s.split()[:2]
        text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", get(f"https://reptile-database.reptarium.cz/species?genus={g}&species={e}")))
        m = re.search(r"Higher Taxa (.*?) Subspecies|Higher Taxa (.*?) Common Names", text)
        line = html.unescape((m.group(1) or m.group(2)) if m else "")
        fam = next(iter(re.findall(r"([A-Z][a-z]+idae)", line)), None)
        order = "Serpentes" if "Serpentes" in line else "Sauria" if "Sauria" in line or "Squamata" in line \
            else "Testudines" if "Testudines" in line else "Crocodylia" if "Crocodylia" in line else None
        out[genus] = dict(family=fam, order=order)
        print("새 속:", s, fam, order)
        time.sleep(1)
    return out


def fetch_subfamilies():
    """파충류 속마다 종 문서 하나의 Higher Taxa 「Colubridae (Natricinae)」에서 아과를 읽는다 → data/rdb_subfamily.json"""
    names = json.loads((DATA / "names.json").read_text(encoding="utf-8"))
    rep = {}  # 파충류 모든 속(시트에 아과 행이 없는 과도 Reptile Database에는 아과가 있을 수 있다)
    for t in names:
        if t["group"] == "REPTILIA" and t["rank"] == "species":
            rep.setdefault(t["sci"].split()[0], t["sci"])
    out_f = DATA / "rdb_subfamily.json"
    out = json.loads(out_f.read_text(encoding="utf-8")) if out_f.exists() else {}
    for n, (genus, s) in enumerate(sorted(rep.items()), 1):
        if genus in out:
            continue
        g, e = s.split()[:2]
        text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", get(f"https://reptile-database.reptarium.cz/species?genus={g}&species={e}")))
        # 「Colubridae (Natricinae), …」 또는 「Scincidae, Eugongylinae (Eugongylini), …」
        m = re.search(r"Higher Taxa (.{0,160})", html.unescape(text))
        sub = re.findall(r"\b([A-Z][a-z]+inae)\b", m.group(1).split("Subspecies")[0]) if m else []
        out[genus] = sub[0] if sub else None
        if n % 20 == 0:
            out_f.write_text(json.dumps(out, ensure_ascii=False, indent=0, sort_keys=True), encoding="utf-8")
            print(f"아과 {n}/{len(rep)}", flush=True)
        time.sleep(1)
    out_f.write_text(json.dumps(out, ensure_ascii=False, indent=0, sort_keys=True), encoding="utf-8")
    print("아과 받은 속:", len(out))


def fetch_live():
    page = get(LIVE)
    total = int(re.search(r"Species found: (\d+)", page).group(1))
    sp = {f"{g} {e}": html.unescape(a).strip() for g, e, a in
          re.findall(r"<li><a href='/([A-Z][a-z]+)/([a-z\-]+)\?[^']*'><em>[^<]*</em>\s*([^<]*)</a>", page)}
    if len(sp) != total:
        raise SystemExit(f"웹 목록 읽기 실패: {len(sp)} / {total}")
    known = checklist_genera()
    higher = higher_taxa({s.split()[0]: s for s in sp if s.split()[0] not in known})
    (DATA / "rdb_live.json").write_text(json.dumps(dict(fetched=date.today().isoformat(), species=sp, higher=higher),
                                                   ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"웹 목록 {total}종 → data/rdb_live.json")


def main():
    if "--subfamilies" in sys.argv:
        return fetch_subfamilies()
    fetch_live()
    if "--live" in sys.argv:
        return
    page = urllib.request.urlopen(urllib.request.Request(BASE, headers=UA), timeout=60).read().decode("utf-8", "replace")
    files = set(re.findall(r"reptile_checklist_(\d{4})_(\d{2})(v\d+)?\.xlsx", page, re.I))
    y, m, v = max(files, key=lambda f: (f[0], f[1], f[2]))
    name = f"reptile_checklist_{y}_{m}{v}.xlsx"
    data = urllib.request.urlopen(urllib.request.Request(BASE + name, headers=UA), timeout=300).read()
    (DATA / "rdb_checklist.xlsx").write_bytes(data)
    print(f"{name} ({len(data) // 1024} KB) → data/rdb_checklist.xlsx · 판 표기: Reptile Database {y}-{m}")


if __name__ == "__main__":
    main()
