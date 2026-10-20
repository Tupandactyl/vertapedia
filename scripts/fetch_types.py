"""속의 모식종(type species)을 받아 data/type_species.json 에 둔다 → {속: 모식종 학명}

- 조류: AviList v2025 확장판(data/avilist2025.xlsx)의 Type_species_of_genus. 원래 조합(예: Corvus pica)으로
  적혀 있으므로 종 행의 Protonym 으로 지금 학명(Pica pica)을 찾고, 옛 이명뿐이면 GBIF 학명 대조로 찾는다.
- 파충류: Reptile Database 종 목록의 type_species 표시를 먼저 쓰고(scripts/rdb.py), 표시가 없는 속만
  1) Wikidata P427, 2) 영문 위키백과 속 문서 분류 상자의 type_species 칸에서 찾는다.
  AviList 모식종이 옛 이명으로만 적혀 지금 학명을 못 찾은 조류 속도 2)로 보충한다. 같은 이름의 식물·곤충 속과 헷갈리지 않게,
Wikidata 모식종이 우리 목록의 종(또는 같은 속의 종소명 어간이 같은 종)일 때만 쓴다.

    python scripts/fetch_types.py
"""
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
UA = {"User-Agent": "Vertapedia/0.1 (https://github.com/Tupandactyl/vertapedia)", "Accept": "application/sparql-results+json"}
Q = """SELECT ?gname ?tname WHERE {{ VALUES ?gname {{ {names} }}
  ?g wdt:P225 ?gname; wdt:P105 wd:Q34740; wdt:P427 ?t. ?t wdt:P225 ?tname. }}"""


def stem(ep):
    for end in ("us", "um", "a", "is", "e", "i"):
        if ep.endswith(end) and len(ep) - len(end) >= 3:
            return ep[: -len(end)]
    return ep


def main():
    names = json.loads((DATA / "names.json").read_text(encoding="utf-8"))
    sp = [t for t in names if t["rank"] == "species"]
    have = {t["sci"] for t in sp}
    by_genus = {}
    for t in sp:
        by_genus.setdefault(t["sci"].split()[0], []).append(t["sci"])
    known = {t["sci"].split()[0] for t in sp if t.get("type_species")}
    birds = bird_genera(names)
    out_f = DATA / "type_species.json"
    out = json.loads(out_f.read_text(encoding="utf-8")) if out_f.exists() else {}
    out = {k: v for k, v in out.items() if k not in birds and k != "_wiki_tried"} |         {"_wiki_tried": [g for g in out.get("_wiki_tried", []) if g not in birds]}
    out.update(avilist_types(have, by_genus, birds))
    genera = sorted(g for g in by_genus if g not in known and g not in birds)
    todo = [g for g in genera if g not in out]
    for k in range(0, len(todo), 150):
        chunk = todo[k:k + 150]
        q = Q.format(names=" ".join(f'"{g}"' for g in chunk))
        url = "https://query.wikidata.org/sparql?" + urllib.parse.urlencode({"query": q})
        for attempt in range(5):
            try:
                res = json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120))
                break
            except Exception as e:
                print("다시 시도:", e)
                time.sleep(20)
        else:
            continue
        found = {}
        for b in res["results"]["bindings"]:
            found.setdefault(b["gname"]["value"], set()).add(b["tname"]["value"].strip())
        for g in chunk:
            pick = None
            for tn in sorted(found.get(g, ())):
                w = tn.split()
                if len(w) < 2:
                    continue
                if tn in have:
                    pick = tn
                    break
                same = [s for s in by_genus[g] if stem(s.split()[1]) == stem(w[1])]
                if len(same) == 1:
                    pick = same[0]
                    break
            out[g] = pick
        out_f.write_text(json.dumps(out, ensure_ascii=False, indent=0, sort_keys=True), encoding="utf-8")
        print(f"모식종 {min(k + 150, len(todo))}/{len(todo)}", flush=True)
        time.sleep(2)
    # 2) 위키백과 분류 상자(type_species = ''Pica pica'')
    # AviList 모식종이 옛 이명으로만 적힌 조류 속(예: Alcedo ispida = A. atthis)도 여기서 보충
    unresolved = sorted(g for g in birds if not out.get(g))
    todo = [g for g in genera + unresolved if not out.get(g) and g not in tried_wiki(out_f)]
    for k in range(0, len(todo), 40):
        chunk = todo[k:k + 40]
        titles = chunk + [f"{g} (bird)" for g in chunk if g in bird_genera(names)] + [f"{g} (genus)" for g in chunk]
        texts = wiki_texts(titles)
        for g in chunk:
            for title in (f"{g} (bird)", f"{g} (genus)", g):
                t = texts.get(title) or ""
                m = re.search(r"type_species\s*=\s*[\[']*\s*([A-Z][a-z]+\s+[a-z]+)", t)
                if not m:
                    continue
                pick = resolve(m.group(1).split(), have, by_genus, g)
                if pick:
                    out[g] = pick
                    break
            out.setdefault("_wiki_tried", []).append(g)
        out_f.write_text(json.dumps(out, ensure_ascii=False, indent=0, sort_keys=True), encoding="utf-8")
        print(f"위키 분류 상자 {min(k + 40, len(todo))}/{len(todo)}", flush=True)
        time.sleep(1)
    out_f.write_text(json.dumps(out, ensure_ascii=False, indent=0, sort_keys=True), encoding="utf-8")
    print("조류 모식종(AviList):", sum(1 for g in birds if out.get(g)), "/", len(birds),
          "· 파충류(목록 표시 없는 속):", sum(1 for g in genera if out.get(g)), "/", len(genera))


AVILIST = "https://www.avilist.org/wp-content/uploads/2025/06/AviList-v2025-11Jun-extended.xlsx"


def avilist_types(have, by_genus, birds):
    import openpyxl
    f = DATA / "avilist2025.xlsx"
    if not f.exists():  # 저장소에는 올리지 않는다(8.8 MB)
        f.write_bytes(urllib.request.urlopen(urllib.request.Request(
            AVILIST, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.avilist.org/checklist/v2025/"}), timeout=300).read())
    rows = list(openpyxl.load_workbook(DATA / "avilist2025.xlsx", read_only=True).worksheets[0].iter_rows(values_only=True))
    h = list(rows[0])
    ix = {k: h.index(k) for k in ("Taxon_rank", "Scientific_name", "Type_species_of_genus", "Protonym")}
    proto = {}  # 원래 조합 → 지금 학명
    for r in rows[1:]:
        if r[ix["Taxon_rank"]] == "species" and r[ix["Protonym"]]:
            w = str(r[ix["Protonym"]]).split()[:2]
            if len(w) == 2:
                proto.setdefault(f"{w[0]} {w[1].lower()}", r[ix["Scientific_name"]])
    out = {}
    for r in rows[1:]:
        if r[ix["Taxon_rank"]] != "genus" or not r[ix["Type_species_of_genus"]]:
            continue
        g = r[ix["Scientific_name"]]
        if g not in birds:
            continue
        txt = str(r[ix["Type_species_of_genus"]])
        # 「Anas boschas [...]; ... = Anas platyrhynchos Linnaeus, 1758」 처럼 지금 이름이 = 뒤에 있으면 그것
        w = re.findall(r"[A-Za-z]+", txt.rsplit("=", 1)[1] if "=" in txt else txt)[:2]
        if len(w) < 2:
            continue
        orig = f"{w[0]} {w[1].lower()}"
        cur = proto.get(orig) or orig
        pick = resolve(cur.split(), have, by_genus, g) if len(cur.split()) == 2 else None
        if not pick and cur.split()[0] != g:  # 모식종이 지금은 다른 속이면 그 속의 종이 아니므로 비워 둔다
            pick = None
        out[g] = pick
        if not pick:
            out.setdefault("_avilist_orig", {})[g] = orig
    # 옛 이명뿐인 것: GBIF 학명 대조로 지금 학명(아종이면 그 종)을 찾는다
    for g, orig in list(out.get("_avilist_orig", {}).items()):
        try:
            m = json.load(urllib.request.urlopen(urllib.request.Request(
                "https://api.gbif.org/v1/species/match?" + urllib.parse.urlencode(dict(name=orig, kingdom="Animalia")),
                headers={"User-Agent": UA["User-Agent"]}), timeout=60))
        except Exception:
            continue
        cur = m.get("species")
        if cur and m.get("matchType") in ("EXACT", "FUZZY") and len(cur.split()) == 2:
            out[g] = resolve(cur.split(), have, by_genus, g)
        time.sleep(0.3)
    out.pop("_avilist_orig", None)
    return out


def tried_wiki(out_f):
    return set(json.loads(out_f.read_text(encoding="utf-8")).get("_wiki_tried", [])) if out_f.exists() else set()


def bird_genera(names):
    return {t["sci"].split()[0] for t in names if t["rank"] == "species" and t["group"] == "AVES"}


def resolve(w, have, by_genus, g):
    tn = " ".join(w[:2])
    if tn in have and tn.split()[0] == g:
        return tn
    same = [s for s in by_genus.get(g, []) if stem(s.split()[1]) == stem(w[1])]
    return same[0] if len(same) == 1 else None


def wiki_texts(titles):
    """제목 → 위키텍스트(넘겨주기 따라감)"""
    out = {}
    for k in range(0, len(titles), 50):
        q = dict(action="query", prop="revisions", rvprop="content", rvslots="main", redirects=1, format="json",
                 formatversion=2, titles="|".join(titles[k:k + 50]))
        url = "https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode(q)
        for attempt in range(5):
            try:
                d = json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120))
                break
            except Exception as e:
                print("다시 시도:", e)
                time.sleep(10)
        else:
            continue
        back = {}
        for r in d["query"].get("redirects", []) + d["query"].get("normalized", []):
            back.setdefault(r["to"], []).append(r["from"])
        for p in d["query"].get("pages", []):
            text = ((p.get("revisions") or [{}])[0].get("slots") or {}).get("main", {}).get("content", "")
            for name in [p["title"]] + back.get(p["title"], []):
                out[name] = text
        time.sleep(1)
    return out


if __name__ == "__main__":
    main()
