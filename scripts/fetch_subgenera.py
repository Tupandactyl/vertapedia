"""Reptile Database 종 문서의 이명(Synonym) 목록에서 아속 조합 「Genus (Subgenus) epithet — AUTHOR YEAR」을 찾아
종마다 가장 최근 연도의 아속을 고른다. 받은 이명 글은 data/rdb_subgenus_cache.json 에 모아 두고 다시 받지 않는다.

    python scripts/fetch_subgenera.py --sample 6          # 종이 30종 이상인 속마다 6종씩 보고 아속을 쓰는 속을 찾는다
    python scripts/fetch_subgenera.py Varanus Gekko ...   # 그 속 전체 종을 받아 data/rdb_subgenus.json 에 쓴다
    python scripts/fetch_subgenera.py --fill Varanus ...  # 아속을 못 정한 종: 문서 전체의 아속 언급(data/rdb_subgenus_hints.json)
    python scripts/fetch_subgenera.py --build             # 기준을 넘는 속만 골라 data/subgenus.json (시트 스크립트 입력)

아속을 넣는 속의 기준: 종 30종 이상, 아속 2개 이상, 소속 종의 50% 이상에 아속을 정할 수 있음.
Anolis는 Reptile Database가 아속을 쓰지 않으므로 이명 목록의 Nicholson et al. 2012·2018 분류(Norops, Dactyloa 등,
2012년 이후 조합)를 아속으로 취급한다.
"""
import json
import re
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fetch_rdb import get

DATA = Path(__file__).resolve().parent.parent / "data"
CACHE = DATA / "rdb_subgenus_cache.json"
OUT = DATA / "rdb_subgenus.json"
HINTS = DATA / "rdb_subgenus_hints.json"  # --fill: 문서 전체에서 센 아속 언급
MIN_SPECIES = 30
MIN_SHARE = 0.5
TYPO = {"Rhaderemias": "Rhabderemias"}  # Reptile Database 이명 목록의 철자 실수
ANOLIS_CLADES = ["Audantia", "Chamaelinorops", "Ctenonotus", "Dactyloa", "Deiroptyx", "Norops", "Xiphosurus"]


def anolis_clades(cache, species):
    from rdb import stem
    out = {}
    for s in species:
        e = s.split()[1]
        t = cache.get(s, "")
        hits = []
        for m in re.finditer(rf"\b({'|'.join(ANOLIS_CLADES)}) ({re.escape(stem(e))}[a-z]*)\b(?! [a-z]+ )", t):
            y = re.search(r"\b(1[789]\d\d|20\d\d)\b", t[m.end():m.end() + 100])
            if y and int(y.group(1)) >= 2012:
                hits.append((int(y.group(1)), m.group(1)))
        out[s] = max(hits)[1] if hits else None
    return out


def build(by_g, cache):
    rdb = json.loads(OUT.read_text(encoding="utf-8"))
    hints = json.loads(HINTS.read_text(encoding="utf-8")) if HINTS.exists() else {}
    res = {}
    for g in sorted(set(rdb) | {"Anolis"}, key=lambda g: -len(by_g[g])):
        if g == "Anolis":
            sp = anolis_clades(cache, by_g[g])
            how = {s: "이명(Nicholson)" for s, v in sp.items() if v}
            src = ("Reptile Database 이명 목록의 Nicholson et al. 2012·2018 분류"
                   "(Norops, Dactyloa 등, 2012년 이후 조합)를 아속으로 취급")
        else:
            subs = {v for v in rdb[g].values() if v}
            sp, how = {}, {}
            for s, v in rdb[g].items():
                c = {k: n for k, n in hints.get(s, {}).items() if k in subs}
                sp[s] = v or (next(iter(c)) if len(c) == 1 else None)
                sp[s] = TYPO.get(sp[s], sp[s])
                if sp[s]:
                    how[s] = "이명" if v else "본문 언급"
            src = "Reptile Database 종 문서 이명 목록의 가장 최근 아속 조합(없으면 문서 본문의 아속 언급)"
        n_sub = len({v for v in sp.values() if v})
        share = sum(1 for v in sp.values() if v) / len(sp)
        ok = len(sp) >= MIN_SPECIES and n_sub >= 2 and share >= MIN_SHARE
        print(f"{'O' if ok else '-'} {g}: {len(sp)}종 · 아속 {n_sub} · 정함 {share:.0%}")
        if ok:
            res[g] = dict(source=src, species=sp, how=how)
    (DATA / "subgenus.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print("data/subgenus.json:", ", ".join(res))


def synonym_text(g, e):
    t = get(f"https://reptile-database.reptarium.cz/species?genus={g}&species={e}")
    t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t)).replace("&nbsp;", " ")
    i = t.find(" Synonym ")
    if i < 0:
        return ""
    j = min([k for k in (t.find(" Distribution ", i), t.find(" Comment ", i), t.find(" Reproduction ", i)) if k > 0]
            or [i + 20000])
    return t[i:j]


def assign(sci, text):
    """이명 글에서 이 종의 아속 조합을 연도와 함께 모아 가장 최근 것을 고른다(같은 해면 뒤에 적힌 것)."""
    g, e = sci.split()
    hits = []
    for k, m in enumerate(re.finditer(rf"\b{g} \(([A-Z][a-z]+)\) {e}\b", text)):
        y = re.search(r"\b(1[789]\d\d|20\d\d)\b", text[m.end():m.end() + 120])
        hits.append((int(y.group(1)) if y else 0, k, m.group(1)))
    if not hits:
        return None, []
    return max(hits)[2], sorted(set(h[2] for h in hits))


def load_cache():
    return json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}


def fetch_all(species, cache):
    todo = [s for s in species if s not in cache]

    def one(s):
        return s, synonym_text(*s.split())

    with ThreadPoolExecutor(4) as ex:
        for n, (s, txt) in enumerate(ex.map(one, todo), 1):
            cache[s] = txt
            if n % 25 == 0 or n == len(todo):
                CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
                print(f"  {n}/{len(todo)}", flush=True)
    return cache


def main():
    live = json.loads((DATA / "rdb_live.json").read_text(encoding="utf-8"))["species"]
    by_g = {}
    for s in sorted(live):
        by_g.setdefault(s.split()[0], []).append(s)
    cache = load_cache()
    if "--build" in sys.argv:
        return build(by_g, cache)
    if "--sample" in sys.argv:
        k = int(sys.argv[sys.argv.index("--sample") + 1])
        big = [g for g, l in by_g.items() if len(l) >= MIN_SPECIES]
        pick = {g: by_g[g][:: max(1, len(by_g[g]) // k)][:k] for g in big}
        fetch_all([s for l in pick.values() for s in l], cache)
        for g in sorted(big, key=lambda g: -len(by_g[g])):
            subs = Counter(assign(s, cache[s])[0] for s in pick[g])
            print(f"{g} ({len(by_g[g])}종): {dict(subs)}")
        return
    genera = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--fill" in sys.argv:  # 이명에 아속 조합이 없는 종: 문서 전체(설명·참고문헌 제목)에서 아속 언급을 센다
        out = json.loads(OUT.read_text(encoding="utf-8"))
        hints = json.loads(HINTS.read_text(encoding="utf-8")) if HINTS.exists() else {}
        todo = [s for g in genera for s, v in out[g].items() if not v and s not in hints]

        def one(s):
            g, e = s.split()
            t = get(f"https://reptile-database.reptarium.cz/species?genus={g}&species={e}")
            t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t))
            c = Counter(re.findall(rf"\b{g} \(([A-Z][a-z]+)\)", t)) + Counter(re.findall(r"[Ss]ubgenus ([A-Z][a-z]+)", t))
            return s, dict(c)

        with ThreadPoolExecutor(4) as ex:
            for n, (s, c) in enumerate(ex.map(one, todo), 1):
                hints[s] = c
                if n % 25 == 0 or n == len(todo):
                    HINTS.write_text(json.dumps(hints, ensure_ascii=False, indent=1), encoding="utf-8")
                    print(f"  {n}/{len(todo)}", flush=True)
        for g in genera:
            subs = set(v for v in out[g].values() if v)
            for s, v in out[g].items():
                if not v:
                    c = {k: n for k, n in hints.get(s, {}).items() if k in subs}
                    print(s, c)
        return
    species = [s for g in genera for s in by_g[g]]
    fetch_all(species, cache)
    out = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    for g in genera:
        out[g] = {s: assign(s, cache[s])[0] for s in by_g[g]}
        c = Counter(out[g].values())
        print(g, len(by_g[g]), dict(c.most_common()))
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
