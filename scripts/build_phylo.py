"""분기도 자료를 만든다: site/data/phylo_A.json(조류), site/data/phylo_R.json(파충류).

조류: Birds of the World Phylogeny Explorer 와 같은 나무(clootl, McTavish et al. 2025, PNAS 122:e2409658122).
  data/phylo/aves_1.7_clements2025.nex = McTavishLab/AvesDataLite 의 Tree_versions/Aves_1.7/Clements2025/summary_dated_clements.nex

파충류: 논문 나무 다섯을 시간 축에 맞춰 이어 붙인다.
  유린목  data/phylo/squamata_title2024.tre  Title et al. 2024, Science 383:918 (5,400 유전자 자리, 시간 보정 6,885종)
            — Dryad doi:10.5061/dryad.p5hqbzkvb 의 1.tree_inference/mainTrees/best_ultrametric_fulltree_ddBD_revision.tre
  뼈대    data/phylo/Data_S8_Dated_Astral_IQ_Point_Tree  Burbrink et al. 2020, Syst. Biol. 69:502 (유린목·훼두목·바깥 무리 연대)
  거북목  data/phylo/turtle_thomson2021.tre  Thomson, Spinks & Shaffer 2021, PNAS 118:e2012215118
            — Dryad doi:10.5061/dryad.jh9w0vt8w 의 bd.mcc.median_heights.tre(종마다 개체 하나, 시간 보정)
  악어목  data/phylo/crocodylia_davies2026.tre  Davies et al. 2026, Proc. R. Soc. B 293:20260635 (figshare 33121148)
            — 공개 자료에 결과 나무가 없어 마디 보정·분자 자료 분석을 MrBayes 로 다시 돌린 것(scripts/croc_dates.py)
  뿌리    Jenkins et al. 2026, Curr. Biol. (OSF t945w) FBD 화석 나무 — 파충류 크라운·거북+주룡류 갈래 나이
  각 무리 나무는 제 연대를 그대로 쓰고, 인룡류(투아타라 x 유린목) 나이는 Burbrink 뼈대 나무, 그 위 두 마디는 Jenkins 나무에서 읽는다.

공통 처리(fit)
1. 나무의 끝을 사이트 종(tree.json)에 맞춘다. 같은 학명 → 그대로. 종소명 철자가 조금 다르거나 속만 바뀐 종 → 하나만 맞으면 그 끝.
2. 나무에 없는 사이트 종은 같은 속(없으면 같은 아과·과) 종들의 공통 조상에서 갈라진 것으로 붙이고 '*'로 표시한다(화면은 점선).
   그 속에 나무에 있는 종이 하나뿐이면 그 가지 중간에서 가른다.
3. 사이트에 없는 끝(통합된 종, 개체 중복 등)은 지운다.
4. 자식 순서는 시트 순서에 맞춘다.

출력: {"src", "cite"(화면 출처 HTML), "nwk"(가지 길이 = 백만 년), "add"(붙인 종 수)}

    python scripts/build_phylo.py          # 둘 다
    python scripts/build_phylo.py R -v     # 파충류만, 맞춤 내역 출력
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PH = ROOT / "data" / "phylo"
TREE = ROOT / "site" / "data" / "tree.json"
OUT = ROOT / "site" / "data"
sys.setrecursionlimit(100000)

A = lambda href, text: f'<a href="{href}" target="_blank" rel="noopener">{text}</a>'
CITE_A = ("나무: " + A("https://birdsoftheworld.org/bow/phylogeny", "Birds of the World Phylogeny") + " v1.7 · McTavish et al. 2025, "
          + A("https://doi.org/10.1073/pnas.2409658122", "<i>PNAS</i> 122:e2409658122") + " · "
          + A("https://github.com/eliotmiller/clootl", "clootl") + ". 분류 이름은 이 사이트의 목록(AviList)에 맞춤.")
CITE_R = ("나무: 유린목 Title et al. 2024, " + A("https://doi.org/10.1126/science.adh2449", "<i>Science</i> 383:918")
          + " · 거북목 Thomson et al. 2021, " + A("https://doi.org/10.1073/pnas.2012215118", "<i>PNAS</i> 118:e2012215118")
          + " · 악어목 Davies et al. 2026, " + A("https://doi.org/10.1098/rspb.2026.0635", "<i>Proc. R. Soc. B</i> 293:20260635")
          + " (MrBayes 마디 보정 분석을 다시 돌림) · 인룡류 연대 Burbrink et al. 2020, " + A("https://doi.org/10.1093/sysbio/syz062", "<i>Syst. Biol.</i> 69:502")
          + " · 파충류·거북+악어 갈래 연대 Jenkins et al. 2026, " + A("https://doi.org/10.1016/j.cub.2026.04.070", "<i>Curr. Biol.</i> 2026")
          + ". 나무 다섯을 시간 축에 맞춰 이어 붙였고, 분류 이름은 이 사이트의 목록(Reptile Database)에 맞춤.")


class N:
    __slots__ = ("name", "bl", "kids", "up", "star")

    def __init__(self, name=None, bl=0.0):
        self.name, self.bl, self.kids, self.up, self.star = name, bl, [], None, False


def parse_newick(s):
    s = re.sub(r"\[[^\]]*\]", "", s).strip().rstrip(";")
    i, n = 0, len(s)
    root = cur = N()
    stack = []
    while i < n:
        c = s[i]
        if c == "(":
            k = N(); k.up = cur; cur.kids.append(k); stack.append(cur); cur = k; i += 1
        elif c == ",":
            par = stack[-1]; k = N(); k.up = par; par.kids.append(k); cur = k; i += 1
        elif c == ")":
            cur = stack.pop(); i += 1
        else:
            j = i
            while j < n and s[j] not in "(),":
                j += 1
            name, _, bl = s[i:j].partition(":")
            if not cur.kids:
                cur.name = name.strip().strip("'\"")
            cur.bl = float(bl) if bl.strip() else 0.0
            i = j
    while len(root.kids) == 1 and root.name is None:
        root = root.kids[0]; root.up = None
    return root


def parse_tree_file(txt):
    """Newick 또는 NEXUS(Translate 표 포함). 첫 나무를 읽는다."""
    if "#NEXUS" not in txt[:200].upper():
        return parse_newick(txt.strip().split(";")[0] + ";")
    trans = {}
    m = re.search(r"\bTRANSLATE\b(.*?);", txt, re.S | re.I)
    if m:
        for part in m.group(1).split(","):
            w = part.strip().split(None, 1)
            if len(w) == 2:
                trans[w[0]] = w[1].strip().strip("'\"")
    m = re.search(r"\bTREE\s+\*?\s*[^=]+=\s*(?:\[&[RU]\]\s*)?(.*?;)", txt, re.S | re.I)
    root = parse_newick(m.group(1))
    for lf in tips(root):
        lf.name = trans.get(lf.name, lf.name)
    return root


def tips(node):
    out, st = [], [node]
    while st:
        x = st.pop()
        if x.kids:
            st.extend(x.kids)
        else:
            out.append(x)
    return out


def stem(ep):
    return re.sub(r"(us|a|um|is|e|i|ae|orum|arum)$", "", ep)


def close(a, b):
    """편집 거리 2 이하(긴 종소명에서 철자 한두 곳만 다름)."""
    if abs(len(a) - len(b)) > 2 or min(len(a), len(b)) < 6:
        return False
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1] <= 2


def mrca(nodes):
    if not nodes:
        return None
    anc = []
    x = nodes[0]
    while x:
        anc.append(x); x = x.up
    pos = {id(a): k for k, a in enumerate(anc)}
    best = 0
    for y in nodes[1:]:
        while id(y) not in pos:
            y = y.up
        best = max(best, pos[id(y)])
    return anc[best]


def height(node):
    """마디 나이(끝까지 거리). 초계량 나무라 첫 자식 쪽으로만 내려간다."""
    h = 0.0
    while node.kids:
        node = node.kids[0]; h += node.bl
    return h


def site_rows(G):
    """[(학명, {o,u,p,f,s,g})] 시트 순서"""
    t = json.loads(TREE.read_text(encoding="utf-8"))
    rows = []

    def walk(n, path):
        if not (len(n) > 3 and isinstance(n[3], list)):
            rows.append((n[0], path))
            return
        p = dict(path); p[n[0]] = n[1]
        for c in n[3]:
            walk(c, p)

    for o in t[G]:
        walk(o, {})
    return rows


def sp_name(tip):
    """끝 이름 → 「Genus species」(개체 번호·아종 꼬리 떼기)"""
    w = re.split(r"[_\s]+", tip.strip())
    return " ".join(w[:2]) if len(w) >= 2 else tip


def prune(lf):
    p = lf.up
    p.kids.remove(lf)
    if len(p.kids) == 1 and p.up:  # 하나 남은 마디는 없앤다
        only = p.kids[0]; only.bl += p.bl; only.up = p.up
        gp = p.up; gp.kids[gp.kids.index(p)] = only


def fit(root, rows, verbose=False):
    order = {r[0]: k for k, r in enumerate(rows)}
    info = dict(rows)
    leaves = tips(root)
    byname = {}
    for lf in leaves:
        lf.name = lf.name.replace("_", " ")
        if lf.name in byname:  # 같은 종 개체가 여럿: 하나만 남긴다
            prune(lf); continue
        byname[lf.name] = lf
    tree_only = {k for k in byname if k not in order}
    matched, renamed = {}, []
    for sci, _ in rows:
        if sci in byname:
            matched[sci] = byname[sci]
    gfam = {}
    for sci in matched:
        gfam.setdefault(sci.split(" ")[0], set()).add(info[sci].get("f"))

    def take(sci, cand):
        lf = byname[cand]
        renamed.append((cand, sci))
        tree_only.discard(cand)
        lf.name = sci
        matched[sci] = lf

    for sci in [r[0] for r in rows if r[0] not in matched]:  # (가) 같은 속, 종소명 철자만 다름
        g, ep = sci.split(" ")[:2]
        cands = [c for c in tree_only if c.split(" ")[0] == g and len(c.split(" ")) > 1 and
                 (stem(c.split(" ")[1]) == stem(ep) or close(c.split(" ")[1], ep))]
        if len(cands) == 1:
            take(sci, cands[0])
    fam_of_leaf = {id(lf): info[s].get("f") for s, lf in matched.items()}

    def near_fams(lf):
        """그 끝에서 올라가며 처음 만나는, 학명이 맞은 친척들의 과"""
        a = lf.up
        while a:
            fs = {fam_of_leaf[id(x)] for x in tips(a) if id(x) in fam_of_leaf}
            if fs:
                return fs
            a = a.up
        return set()

    for sci in [r[0] for r in rows if r[0] not in matched]:  # (나) 속이 바뀜: 종소명이 같고, 나무에서 곁의 종들이 같은 과
        ep, fam = sci.split(" ")[1], info[sci].get("f")
        cands = [c for c in tree_only if len(c.split(" ")) > 1 and stem(c.split(" ")[1]) == stem(ep) and
                 fam in gfam.get(c.split(" ")[0], {fam})]
        cands = [c for c in cands if near_fams(byname[c]) == {fam}]
        if len(cands) == 1:
            take(sci, cands[0])
            fam_of_leaf[id(byname[sci] if sci in byname else matched[sci])] = fam

    dropped = sorted(tree_only)
    for k in dropped:
        prune(byname[k])

    added, lost = [], []
    for sci, path in rows:
        if sci in matched:
            continue
        group = []
        for rank in ("g", "s", "f", "o"):
            if path.get(rank):
                group = [matched[r] for r, p in rows if p.get(rank) == path[rank] and r in matched]
                if group:
                    break
        if not group:
            lost.append(sci); continue
        new = N(sci); new.star = True
        if len(group) == 1:  # 형제 하나: 그 가지 중간에서 가른다
            t = group[0]; half = t.bl / 2
            mid = N(bl=t.bl - half); mid.up = t.up
            t.up.kids[t.up.kids.index(t)] = mid
            t.bl = half; t.up = mid; new.bl = half; new.up = mid
            mid.kids = [t, new]
        else:
            a = mrca(group)
            new.bl = height(a)
            new.up = a; a.kids.append(new)
        matched[sci] = new
        added.append(sci)

    def rot(node):
        if not node.kids:
            return order.get(node.name, 10 ** 9)
        ks = [rot(c) for c in node.kids]
        node.kids = [c for _, c in sorted(zip(ks, node.kids), key=lambda z: z[0])]
        return max(ks)
    rot(root)

    def nwk(node):
        bl = ("%.3f" % max(node.bl, 0)).rstrip("0").rstrip(".") or "0"
        if not node.kids:
            return node.name.replace(" ", "_") + ("*" if node.star else "") + ":" + bl
        return "(" + ",".join(nwk(c) for c in node.kids) + "):" + bl

    root.bl = 0.0
    stats = dict(rows=len(rows), leaves=len(leaves), exact=len(rows) - len(renamed) - len(added) - len(lost),
                 renamed=len(renamed), added=len(added), lost=len(lost), dropped=len(dropped))
    if verbose:
        print("속·철자 맞춤:", renamed)
        print("붙임:", added[:400], "…" if len(added) > 400 else "")
        print("지움:", dropped[:400])
        print("못 붙임:", lost)
    return nwk(root) + ";", stats


def write(G, src, cite, nwk, stats):
    out = OUT / f"phylo_{G}.json"
    out.write_text(json.dumps({"src": src, "cite": cite, "nwk": nwk, "add": stats["added"]},
                              ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{G}: 사이트 {stats['rows']}종 · 나무 끝 {stats['leaves']} · 학명 그대로 {stats['exact']} · 속·철자 맞춤 {stats['renamed']} · "
          f"붙임 {stats['added']} · 못 붙임 {stats['lost']} · 지운 끝 {stats['dropped']} · {out.stat().st_size // 1024} KB")


def birds(verbose):
    root = parse_tree_file((PH / "aves_1.7_clements2025.nex").read_text(encoding="utf-8"))
    nwk, stats = fit(root, site_rows("A"), verbose)
    write("A", "Birds of the World Phylogeny · Tree v1.7 / Clements 2025 (McTavish et al. 2025, PNAS; clootl)", CITE_A, nwk, stats)


# ---------------- 파충류: 나무 잇기 ----------------
def keep_species(root):
    """끝 이름을 종 이름으로 줄이고(개체·아종 꼬리 떼기), 같은 종 개체는 하나만 남긴다."""
    seen = set()
    for lf in tips(root):
        nm = sp_name(lf.name)
        if nm in seen:
            prune(lf)
        else:
            seen.add(nm); lf.name = nm
    return root


def subtree_of(root, names):
    """names 끝들의 공통 조상 마디를 떼어 낸다(다른 끝은 지운다)."""
    lv = [lf for lf in tips(root) if sp_name(lf.name) in names]
    a = mrca(lv)
    keep = {id(x) for x in lv}
    for lf in tips(a):
        if id(lf) not in keep:
            prune(lf)
    a.up = None
    return a


def node_age(root, a, b):
    lv = {sp_name(lf.name): lf for lf in tips(root)}
    x = mrca([lv[a], lv[b]])
    return height(x)


def croc_tree():
    """Davies et al. 2026 의 현생 악어 25종 고정 계통 + MrBayes 마디 보정(분자 자료) 연대.
    figshare 자료에 결과 나무가 없어 scripts/croc_dates.py 로 그 분석을 다시 돌려 만든 나무를 쓴다."""
    return parse_tree_file((PH / "crocodylia_davies2026.tre").read_text(encoding="utf-8"))


def graft(kids_ages, age):
    """[(마디, 그 마디 나이)] 를 age 나이의 새 마디 아래에 잇는다(줄기 길이 = 나이 차)."""
    n = N()
    for k, a in kids_ages:
        assert a <= age + 1e-6, (a, age)
        k.bl = age - a; k.up = n; n.kids.append(k)
    return n


# 무리 사이 마디 나이(백만 년 전)
# Jenkins et al. 2026(Curr. Biol., OSF t945w)의 FBD 화석 나무는 가장 젊은 끝(Huehuecuetzpalli, 100-105 Ma)을 0으로 둔
# 상대 나이라, 다른 화석 끝들의 보정 범위가 모두 맞는 103.2 Ma 를 더해 절대 나이로 바꾼다.
#   파충류 크라운(Clevosaurus x Protosuchus) 173.81 → 277.0, 거북+주룡류(Proganochelys x Protosuchus) 166.95 → 270.2
JENKINS_OFFSET = 103.2
AGE_REPTILIA = round(173.81 + JENKINS_OFFSET, 1)
AGE_ARCHELOSAURIA = round(166.95 + JENKINS_OFFSET, 1)


def reptiles(verbose):
    rows = site_rows("R")
    sq = keep_species(parse_tree_file((PH / "squamata_title2024.tre").read_text(encoding="utf-8")))
    tu = parse_tree_file((PH / "turtle_thomson2021.tre").read_text(encoding="utf-8", errors="replace"))
    tu = subtree_of(tu, {sp_name(x.name) for x in tips(tu) if not x.name.startswith("AA_")})  # 바깥 무리(닭·앨리게이터) 빼기
    tu = keep_species(tu)
    cr = keep_species(croc_tree())
    bb = parse_tree_file((PH / "Data_S8_Dated_Astral_IQ_Point_Tree").read_text(encoding="utf-8", errors="replace"))
    age_lep = height(bb)  # 뼈대 나무 뿌리 = 투아타라 x 유린목
    assert any(x.name == "Sphenodon_punctatus" for x in bb.kids), "뼈대 나무 뿌리가 투아타라 갈래가 아님"
    sph = N("Sphenodon punctatus")
    lep = graft([(sph, 0.0), (sq, height(sq))], age_lep)
    arc = graft([(tu, height(tu)), (cr, height(cr))], AGE_ARCHELOSAURIA)
    root = graft([(lep, age_lep), (arc, AGE_ARCHELOSAURIA)], AGE_REPTILIA)
    print(f"R 연대: 파충류 {AGE_REPTILIA} · 인룡류 {age_lep:.1f} · 유린목 {height(sq):.1f} · 거북+악어 {AGE_ARCHELOSAURIA} · "
          f"거북목 {height(tu):.1f} · 악어목 {height(cr):.1f}")
    nwk, stats = fit(root, rows, verbose)
    write("R", "Title et al. 2024; Thomson et al. 2021; Davies et al. 2026; Burbrink et al. 2020; Jenkins et al. 2026", CITE_R, nwk, stats)


def main():
    which = [a for a in sys.argv[1:] if a in ("A", "R")] or ["A", "R"]
    v = "-v" in sys.argv
    if "A" in which:
        birds(v)
    if "R" in which:
        reptiles(v)


if __name__ == "__main__":
    main()
