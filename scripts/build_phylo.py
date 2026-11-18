"""분기도 자료를 만든다: site/data/phylo_A.json(조류), site/data/phylo_R.json(파충류).

조류: Birds of the World Phylogeny Explorer 와 같은 계통수(clootl, McTavish et al. 2025, PNAS 122:e2409658122).
  data/phylo/aves_1.7_clements2025.nex = McTavishLab/AvesDataLite 의 Tree_versions/Aves_1.7/Clements2025/summary_dated_clements.nex

파충류: 논문 계통수 다섯을 시간 축에 맞춰 이어 붙인다.
  유린목  data/phylo/squamata_title2024_imputed.tre  Title et al. 2024, Science 383:918 (5,400 유전자 자리, 시간 보정 6,885종)
            — Dryad doi:10.5061/dryad.p5hqbzkvb 의 2.time_calibration_imputation/primarytree-imputed-trees.zip 가운데
              best-full-trees/squams-full-imputed-xx1.tre. 주 계통수(data/phylo/squamata_title2024.tre)에 유전자 자료가 없는 종 3,872 자리를
              분류에 맞춰 무작위로 끼워 넣은 100개 복제 중 첫째. 자리는 속별 이름표(「Ficimia_xzx2」)뿐이라
              그 속에서 유전자 자료가 없는 사이트 종을 시트 순서대로 넣는다(점선, 위치는 한 가지 가능한 배치일 뿐).
  뼈대    data/phylo/Data_S8_Dated_Astral_IQ_Point_Tree  Burbrink et al. 2020, Syst. Biol. 69:502 (유린목·훼두목·바깥 무리 연대)
  거북목  data/phylo/turtle_thomson2021.tre  Thomson, Spinks & Shaffer 2021, PNAS 118:e2012215118
            — Dryad doi:10.5061/dryad.jh9w0vt8w 의 bd.mcc.median_heights.tre(종마다 개체 하나, 시간 보정)
  악어목  data/phylo/crocodylia_davies2026.tre  Davies et al. 2026, Proc. R. Soc. B 293:20260635 (figshare 33121148)
            — 공개 자료에 결과 계통수가 없어 마디 보정·분자 자료 분석을 MrBayes 로 다시 돌린 것(scripts/croc_dates.py)
  뿌리    Jenkins et al. 2026, Curr. Biol. (OSF t945w) FBD 화석 계통수 — 파충류 크라운·거북+주룡류 갈래 나이
  각 무리 계통수는 제 연대를 그대로 쓰고, 인룡류(투아타라 x 유린목) 나이는 Burbrink 뼈대 계통수, 그 위 두 마디는 Jenkins 계통수에서 읽는다.

공통 처리(fit)
1. 계통수의 끝을 사이트 종(tree.json)에 맞춘다. 같은 학명 → 그대로. 종소명 철자가 조금 다르거나 속만 바뀐 종 → 하나만 맞으면 그 끝.
2. imputed 계통수의 속별 빈자리(유린목)가 있으면 그 속의 나머지 사이트 종을 넣는다('*', 화면은 점선).
   그래도 남는 사이트 종은 같은 속(없으면 같은 아과·과) 종들의 공통 조상에서 갈라진 것으로 붙이고 '*'로 표시한다(화면은 점선).
   그 속에 계통수에 있는 종이 하나뿐이면 그 가지 중간에서 가른다.
3. 사이트에 없는 끝(통합된 종, 개체 중복 등)은 지운다.
4. 자식 순서는 시트 순서에 맞춘다.

출력: {"src", "cite"(화면 출처 HTML), "nwk"(가지 길이 = 백만 년), "add"(붙인 종 수)}

    python scripts/build_phylo.py          # 둘 다
    python scripts/build_phylo.py R -v     # 파충류만, 맞춤 내역 출력
"""
import json
import random
import re
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PH = ROOT / "data" / "phylo"
TREE = ROOT / "site" / "data" / "tree.json"
OUT = ROOT / "site" / "data"
sys.setrecursionlimit(100000)

A = lambda href, text: f'<a href="{href}" target="_blank" rel="noopener">{text}</a>'
CITE_A = ("출처: " + A("https://birdsoftheworld.org/bow/phylogeny", "Birds of the World Phylogeny v1.7") + " · McTavish et al. 2025, "
          + A("https://doi.org/10.1073/pnas.2409658122", "<i>PNAS</i>"))
CITE_R = ("출처: 유린목 Title et al. 2024, " + A("https://doi.org/10.1126/science.adh2449", "<i>Science</i>")
          + " · 거북목 Thomson et al. 2021, " + A("https://doi.org/10.1073/pnas.2012215118", "<i>PNAS</i>")
          + " · 악어목 Davies et al. 2026, " + A("https://doi.org/10.1098/rspb.2026.0635", "<i>Proc. R. Soc. B</i>")
          + " · 인룡류 Burbrink et al. 2020, " + A("https://doi.org/10.1093/sysbio/syz062", "<i>Syst. Biol.</i>")
          + " · 뿌리 Jenkins et al. 2026, " + A("https://doi.org/10.1016/j.cub.2026.04.070", "<i>Curr. Biol.</i>"))


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
    """Newick 또는 NEXUS(Translate 표 포함). 첫 계통수를 읽는다."""
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


def _nodes(node):
    out, st = [], [node]
    while st:
        x = st.pop(); out.append(x); st.extend(x.kids)
    return out


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
    """마디 나이(끝까지 거리). 초계량 계통수라 첫 자식 쪽으로만 내려간다."""
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


def fit(root, rows, verbose=False, impute=None):
    """impute(경로) 가 참인 종은 같은 속 가지 위에 무작위로 붙인다(유전자 자료 없는 종의 imputed 배치)."""
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

    for sci in [r[0] for r in rows if r[0] not in matched]:  # (나) 속이 바뀜: 종소명이 같고, 계통수에서 곁의 종들이 같은 과
        ep, fam = sci.split(" ")[1], info[sci].get("f")
        cands = [c for c in tree_only if len(c.split(" ")) > 1 and stem(c.split(" ")[1]) == stem(ep) and
                 fam in gfam.get(c.split(" ")[0], {fam})]
        cands = [c for c in cands if near_fams(byname[c]) == {fam}]
        if len(cands) == 1:
            take(sci, cands[0])
            fam_of_leaf[id(byname[sci] if sci in byname else matched[sci])] = fam

    # (다) imputed 계통수의 속별 자리표(「Ficimia xzx2」)에 그 속에서 아직 못 맞춘 사이트 종을 시트 순서대로 넣는다
    imputed = []
    slots = {}
    for c in sorted(tree_only, key=lambda c: (c.split(" ")[0], int(re.sub(r"\D", "", c.split(" ")[1]) or 0))):
        if re.fullmatch(r"[A-Z][a-z]+ xzx\d+", c):
            slots.setdefault(c.split(" ")[0], []).append(c)
    # 자리가 사이트 분류와 맞는 곳에 있을 때만 쓴다(imputed 계통수는 자리를 상위 무리 안에 무작위로 두기도 한다).
    #  - 그 자리를 품은 '같은 속만으로 된 가장 큰 무리'를 찾는다(자리표도 이름의 속으로 본다. 지울 끝은 없는 셈 친다).
    #  - 그 속에 유전자 자료 종이 있으면: 그 무리 안에 유전자 자료 종이 하나라도 있어야 한다(속 덩어리에 붙은 자리).
    #  - 없으면: 그 무리의 자매 쪽 속들이 모두 그 안에 통째로 들어 있고(남의 속 안에 끼어들지 않음) 같은 과여야 한다.
    #  쓰지 않은 자리의 종은 아래 (라)에서 속 공통 조상에 붙는다.
    PH_RE = re.compile(r"[A-Z][a-z]+ xzx\d+")
    drop_named = {id(byname[c]) for c in tree_only if not PH_RE.fullmatch(c)}
    gen = lambda x: x.name.split(" ")[0]
    seq_ids = {id(lf) for lf in matched.values()}
    has_seq = {s.split(" ")[0] for s in matched}
    fam_of_g = {r.split(" ")[0]: p.get("f") for r, p in rows}
    fam_of_id = {id(lf): info[s].get("f") for s, lf in matched.items()}
    live = lambda a: [x for x in tips(a) if id(x) not in drop_named]
    gtotal = {}
    for x in live(root):
        gtotal[gen(x)] = gtotal.get(gen(x), 0) + 1

    def near_ok(lf, g):
        a = lf
        while a.up and all(gen(x) == g for x in live(a.up)):
            a = a.up
        if g in has_seq:
            return any(id(x) in seq_ids for x in live(a))
        if not a.up:
            return False
        inner = {id(x) for x in live(a)}
        others = [x for x in live(a.up) if id(x) not in inner]
        cnt = {}
        for x in others:
            cnt[gen(x)] = cnt.get(gen(x), 0) + 1
        if any(cnt[h] != gtotal.get(h) for h in cnt):
            return False
        fams = {fam_of_id[id(x)] for x in others if id(x) in fam_of_id}
        return fams == {fam_of_g.get(g)}
    for g in list(slots):
        slots[g] = [c for c in slots[g] if near_ok(byname[c], g)]
    for sci in [r[0] for r in rows if r[0] not in matched]:
        sl = slots.get(sci.split(" ")[0])
        if sl:
            c = sl.pop(0)
            take(sci, c)
            renamed.pop()
            byname[c].star = True
            imputed.append(sci)

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
        if impute and rank == "g" and impute(path):
            # TACT 처럼: 그 속 크라운 무리 안의 가지 하나(길이에 비례해 고름, 속에 종이 하나면 그 끝 가지) 위
            # 무작위 시점에서 갈라진 것으로 둔다. 종마다 난수를 고정해 빌드마다 같은 결과.
            rnd = random.Random(zlib.crc32(sci.encode("utf-8")))
            crown = mrca(group)
            br = [x for x in _nodes(crown) if x is not crown and x.bl > 0] or [crown]
            tot = sum(x.bl for x in br)
            pick, acc = rnd.uniform(0, tot), 0.0
            for x in br:
                acc += x.bl
                if acc >= pick:
                    break
            low = height(x)
            t = low + rnd.uniform(0.05, 0.95) * x.bl
            par = x.up
            mid = N(bl=x.bl - (t - low)); mid.up = par
            par.kids[par.kids.index(x)] = mid
            x.bl = t - low; x.up = mid
            new.bl = t; new.up = mid
            mid.kids = [x, new]
            matched[sci] = new
            imputed.append(sci)
            continue
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
    stats = dict(rows=len(rows), leaves=len(leaves), exact=len(rows) - len(renamed) - len(added) - len(lost) - len(imputed),
                 renamed=len(renamed), imputed=len(imputed), added=len(added), lost=len(lost),
                 dropped=len([d for d in dropped if not re.fullmatch(r"[A-Z][a-z]+ xzx\d+", d)]),
                 slots_left=sum(len(v) for v in slots.values()))
    if verbose:
        print("속·철자 맞춤:", renamed)
        print("붙임:", added[:400], "…" if len(added) > 400 else "")
        print("지움:", dropped[:400])
        print("못 붙임:", lost)
    return nwk(root) + ";", stats


def write(G, src, cite, nwk, stats):
    out = OUT / f"phylo_{G}.json"
    out.write_text(json.dumps({"src": src, "cite": cite, "nwk": nwk, "add": stats["added"], "imp": stats["imputed"]},
                              ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{G}: 사이트 {stats['rows']}종 · 계통수 끝 {stats['leaves']} · 학명 그대로 {stats['exact']} · 속·철자 맞춤 {stats['renamed']} · "
          f"imputed 자리 {stats['imputed']}(남은 자리 {stats['slots_left']}) · 붙임 {stats['added']} · 못 붙임 {stats['lost']} · 지운 끝 {stats['dropped']} · "
          f"{out.stat().st_size // 1024} KB")


def birds(verbose):
    root = parse_tree_file((PH / "aves_1.7_clements2025.nex").read_text(encoding="utf-8"))
    nwk, stats = fit(root, site_rows("A"), verbose)
    OUTS["A"] = nwk
    write("A", "Birds of the World Phylogeny · Tree v1.7 / Clements 2025 (McTavish et al. 2025, PNAS; clootl)", CITE_A, nwk, stats)


# ---------------- 파충류: 계통수 잇기 ----------------
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
    figshare 자료에 결과 계통수가 없어 scripts/croc_dates.py 로 그 분석을 다시 돌려 만든 계통수를 쓴다."""
    return parse_tree_file((PH / "crocodylia_davies2026.tre").read_text(encoding="utf-8"))


def graft(kids_ages, age):
    """[(마디, 그 마디 나이)] 를 age 나이의 새 마디 아래에 잇는다(줄기 길이 = 나이 차)."""
    n = N()
    for k, a in kids_ages:
        assert a <= age + 1e-6, (a, age)
        k.bl = age - a; k.up = n; n.kids.append(k)
    return n


# 무리 사이 마디 나이(백만 년 전)
# Jenkins et al. 2026(Curr. Biol., OSF t945w)의 FBD 화석 계통수는 가장 젊은 끝(Huehuecuetzpalli, 100-105 Ma)을 0으로 둔
# 상대 나이라, 다른 화석 끝들의 보정 범위가 모두 맞는 103.2 Ma 를 더해 절대 나이로 바꾼다.
#   파충류 크라운(Clevosaurus x Protosuchus) 173.81 → 277.0, 거북+주룡류(Proganochelys x Protosuchus) 166.95 → 270.2
JENKINS_OFFSET = 103.2
AGE_REPTILIA = round(173.81 + JENKINS_OFFSET, 1)
AGE_ARCHELOSAURIA = round(166.95 + JENKINS_OFFSET, 1)
#   주룡류(Protosuchus x Coelophysis) 149.93 → 253.1 (Thomson et al. 2021 거북 계통수의 닭 x 앨리게이터 253.7 과도 맞는다)
AGE_ARCHOSAURIA = round(149.93 + JENKINS_OFFSET, 1)
OUTS = {}


def combined():
    """조류+파충류: 파충류 계통수의 악어목 갈래를 주룡류 마디(악어목 + 조류)로 바꿔 끼운다. 둘 다 fit 을 거친 계통수."""
    A_, R_ = parse_newick(OUTS["A"]), parse_newick(OUTS["R"])
    crocs = {r for r, p in site_rows("R") if p.get("o") == "Crocodylia"}
    cr = mrca([x for x in tips(R_) if x.name.rstrip("*").replace("_", " ") in crocs])
    par, bl_old = cr.up, cr.bl
    age_par = height(cr) + bl_old
    arch = graft([(cr, height(cr)), (A_, height(A_))], AGE_ARCHOSAURIA)
    arch.bl = age_par - AGE_ARCHOSAURIA
    arch.up = par
    par.kids[par.kids.index(cr)] = arch

    def nwk(node):
        bl = ("%.3f" % max(node.bl, 0)).rstrip("0").rstrip(".") or "0"
        return (node.name if not node.kids else "(" + ",".join(nwk(c) for c in node.kids) + ")") + ":" + bl
    R_.bl = 0
    ra, rr = (json.loads((OUT / f"phylo_{g}.json").read_text(encoding="utf-8")) for g in "AR")
    out = OUT / "phylo_X.json"
    cite = (ra["cite"] + " · " + rr["cite"].replace("출처: ", "", 1) + " · 주룡류 Jenkins et al. 2026")
    out.write_text(json.dumps({"src": ra["src"] + "; " + rr["src"], "cite": cite, "nwk": nwk(R_) + ";",
                               "add": ra["add"] + rr["add"], "imp": ra["imp"] + rr["imp"]},
                              ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"X: 조류+파충류 · 주룡류 {AGE_ARCHOSAURIA} · 조류 크라운 {height(A_):.1f} · 악어목 {height(cr):.1f} · {out.stat().st_size // 1024} KB")


def reptiles(verbose):
    rows = site_rows("R")
    sq = keep_species(parse_tree_file((PH / "squamata_title2024_imputed.tre").read_text(encoding="utf-8")))
    tu = parse_tree_file((PH / "turtle_thomson2021.tre").read_text(encoding="utf-8", errors="replace"))
    tu = subtree_of(tu, {sp_name(x.name) for x in tips(tu) if not x.name.startswith("AA_")})  # 바깥 무리(닭·앨리게이터) 빼기
    tu = keep_species(tu)
    cr = keep_species(croc_tree())
    bb = parse_tree_file((PH / "Data_S8_Dated_Astral_IQ_Point_Tree").read_text(encoding="utf-8", errors="replace"))
    age_lep = height(bb)  # 뼈대 계통수 뿌리 = 투아타라 x 유린목
    assert any(x.name == "Sphenodon_punctatus" for x in bb.kids), "뼈대 계통수 뿌리가 투아타라 갈래가 아님"
    sph = N("Sphenodon punctatus")
    lep = graft([(sph, 0.0), (sq, height(sq))], age_lep)
    arc = graft([(tu, height(tu)), (cr, height(cr))], AGE_ARCHELOSAURIA)
    root = graft([(lep, age_lep), (arc, AGE_ARCHELOSAURIA)], AGE_REPTILIA)
    print(f"R 연대: 파충류 {AGE_REPTILIA} · 인룡류 {age_lep:.1f} · 유린목 {height(sq):.1f} · 거북+악어 {AGE_ARCHELOSAURIA} · "
          f"거북목 {height(tu):.1f} · 악어목 {height(cr):.1f}")
    # 거북목·악어목은 imputed 계통수가 없어 같은 방식(속 무리 안 가지 위 무작위 배치)으로 직접 채운다
    nwk, stats = fit(root, rows, verbose, impute=lambda p: p.get("o") in ("Testudines", "Crocodylia"))
    OUTS["R"] = nwk
    write("R", "Title et al. 2024; Thomson et al. 2021; Davies et al. 2026; Burbrink et al. 2020; Jenkins et al. 2026", CITE_R, nwk, stats)


def main():
    which = [a for a in sys.argv[1:] if a in ("A", "R")] or ["A", "R"]
    v = "-v" in sys.argv
    if "A" in which:
        birds(v)
    if "R" in which:
        reptiles(v)
    if len(OUTS) == 2:
        combined()


if __name__ == "__main__":
    main()
