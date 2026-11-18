"""악어목 연대 계통수(data/phylo/crocodylia_davies2026.tre)를 MrBayes 결과에서 만든다.

Davies et al. 2026 (Proc. R. Soc. B 293:20260635) 의 figshare 자료(doi:10.6084/m9.figshare.33121148)에는
입력 파일만 있고 결과 계통수가 없다. 그래서 논문이 가장 믿을 만하다고 본 '마디 보정 + 분자 자료' 분석
(supp/1_analyses/1_posterior/1_node_molecular)을 다시 돌렸다. 바꾼 점(data/phylo/crocodylia_mrbayes/r1.nex 등):
  - 무리 제약 번호를 행렬 순서에 맞게 고침: Crocodylidae 9-22 → 9-23(Osteolaemus tetraspis 포함), Longirostres 9-24 → 9-25(Tomistoma 포함).
    원래 번호로는 시작 계통수가 제약을 어겨 MrBayes 3.2.7 이 멈춘다.
  - 계통이 고정된 분석이라 체인 가열 없이 독립 런 4개(체인 1개, 300만 세대, 1,000세대마다 표본)를 나란히 돌림. BEAGLE 끔.
각 런의 앞 25%를 버리고, 표본 계통수마다 마디 높이를 시계 속도로 나눠 나이(백만 년)를 구한 뒤 마디별 중앙값을 쓴다.

    python scripts/croc_dates.py <MrBayes 출력 폴더>      # r1.t ~ r4.t 를 읽는다
"""
import re
import statistics
import sys
from pathlib import Path

from build_phylo import N, parse_newick, tips

OUT = Path(__file__).resolve().parent.parent / "data" / "phylo" / "crocodylia_davies2026.tre"


def read_t(path, burnin=0.25):
    txt = Path(path).read_text(encoding="utf-8", errors="replace")
    tr = {}
    m = re.search(r"translate(.*?);", txt, re.S | re.I)
    for part in m.group(1).split(","):
        w = part.split()
        if len(w) == 2:
            tr[w[0]] = w[1]
    trees = re.findall(r"tree gen\.\d+[^=]*=\s*\[&[RU]\]\s*\[&clockrate=([0-9.e+-]+)\]\s*(.*?;)", txt)
    trees = trees[int(len(trees) * burnin):]
    return tr, trees


def clades(root):
    """마디 → (그 아래 끝 이름 집합, 높이)"""
    out = {}

    def walk(n):
        if not n.kids:
            return frozenset([n.name]), 0.0
        sets, hs = zip(*(walk(c) for c in n.kids))
        s = frozenset().union(*sets)
        h = max(hh + c.bl for hh, c in zip(hs, n.kids))
        out[s] = h
        return s, h
    walk(root)
    return out


def main(folder):
    ages, topo = {}, None
    nt = 0
    for f in sorted(Path(folder).glob("r[0-9].t")):
        tr, trees = read_t(f)
        for rate, nwk in trees:
            root = parse_newick(nwk)
            for lf in tips(root):
                lf.name = tr.get(lf.name, lf.name)
            for s, h in clades(root).items():
                ages.setdefault(s, []).append(h / float(rate))
            topo = topo or root
            nt += 1
    med = {s: statistics.median(v) for s, v in ages.items()}

    def build(n):
        if not n.kids:
            return n.name, 0.0
        parts = [build(c) for c in n.kids]
        s = frozenset(x for c in n.kids for x in tip_names(c))
        a = med[s]
        return "(" + ",".join(f"{p}:{max(a - pa, 0):.4f}" for p, pa in parts) + ")", a

    def tip_names(n):
        return [x.name for x in tips(n)]

    nwk, root_age = build(topo)
    OUT.write_text(nwk + ";\n", encoding="utf-8")
    print(f"표본 계통수 {nt}개 · 악어목 크라운 {root_age:.1f} Ma · {OUT}")
    for s, v in sorted(med.items(), key=lambda z: -z[1])[:8]:
        print(f"  {v:6.1f} Ma  {len(s)}종  {', '.join(sorted(s))[:80]}")


if __name__ == "__main__":
    main(sys.argv[1])
