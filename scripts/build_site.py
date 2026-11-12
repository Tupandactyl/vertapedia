"""data/names.json·data/media 에서 사이트 자료를 만든다.

- site/data/names.min.json : 검색용 가벼운 목록
- site/data/tree.json      : 목 > (아목) > (상과) > 과 > (아과) > 속 > 종 분류군 (시트 순서)
- site/data/random.json    : 첫 화면에서 고를 종 (국명과 사진이 있는 종)
- site/sp/<학명>.json      : 종 문서 (시트 기준 이전·다음 종 포함)
- site/fam/<학명>.json     : 과 문서 — 명칭 근거와 포함 속·종 목록
- site/sp/<학명>.html      : 종 주소. 공유 미리보기(Open Graph) 태그를 담고 본문은 sp.css·sp.js 로 그린다
- site/{index,find,sp,fam}.html (sp.html 은 옛 주소 sp.html#학명 을 새 주소로 넘긴다)
"""
import html
import json
import re
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

from ko_link import Linker
import distrule
import ko_names

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SITE = ROOT / "site"
SITE_URL = "https://tupandactyl.github.io/vertapedia/"


def load(name, default=None):
    f = DATA / name
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else default


names = load("names.json")
dist = load("distribution.json", {})
bird_ssp = load("bird_subspecies.json", {})  # 조류 아종 목록(AviList v2026)


def subspecies_of(t):
    """아종 목록. 조류는 AviList 아종 전체에 한국조류목록 등의 국명을 붙이고, 국내 도래(국명 있는) 아종을 맨 위에,
    나머지는 알파벳 순서로 둔다. 파충류는 Reptile Database 아종 목록."""
    have = {s["sci"]: s for s in t.get("subspecies", [])}
    if t["group"] != "AVES":
        return list(t.get("subspecies", []))
    out = [dict(have.get(sci, {}), sci=sci, author=au or have.get(sci, {}).get("author")) for sci, au in bird_ssp.get(t["sci"], [])]
    seen = {x["sci"] for x in out}
    out += [s for s in t.get("subspecies", []) if s["sci"] not in seen and s.get("ko")]  # AviList에 없는 국명 아종(통합 등)
    return sorted(out, key=lambda x: (not x.get("ko"), x["sci"]))


bird_range = load("bird_range.json", {})  # 조류 분포 설명(AviList v2026 RANGE, 영문)
bird_iucn = load("bird_iucn.json", {})  # 조류 IUCN 등급(AviList v2026). 파충류는 distribution.json 의 GBIF 값  # GBIF 나라별 기록 수 (scripts/fetch_distribution.py)


GEO = load("geo.json", {"neighbours": {}, "subregion": {}})
GADM = load("gadm_regions.json", {})  # GBIF 행정구역 → 지역(US-HI 등)
RANGE_PLACES = load("bird_range_places.json", {})  # AviList 분포 설명의 지명(scripts/build_range_places.py)
REGION_KO = load("region_ko.json", {})  # 나라·지역 코드 → 한국어 이름(scripts/build_region_names.py)
estab = load("establishment.json", {})  # iNaturalist 나라별 토착/도입 표시 (scripts/fetch_establishment.py)  # GeoNames 이웃 나라, UN 소지역


def dist_of(sci):
    """서식국(노랑)·도입 정착지(청록)·드문 기록(옅게). 판정 규칙은 scripts/distrule.py"""
    d = dist.get(sci)
    c = distrule.counts(d, GADM)
    if not c:
        return None
    places = RANGE_PLACES.get(sci)
    intro_flag, native_flag = distrule.flags(estab.get(sci), c)
    major = distrule.bird_habitat(c, GEO, places, intro_flag) if places else distrule.habitat(c, GEO)
    said_native, said_intro = set((places or {}).get("n", [])), set((places or {}).get("i", []))
    intro_flag, native_flag = (intro_flag - said_native) | said_intro, (native_flag | said_native) - said_intro
    home = distrule.home_range(major, c, intro_flag, native_flag, GEO)
    intro = ((major - home) & intro_flag) | (major & said_intro)
    rare = sorted(k for k in c if k not in major)
    native, intro = (sorted(s, key=lambda k: (-c[k], k)) for s in (major - intro, intro))  # 기록 많은 곳부터
    ko = lambda a: [REGION_KO.get(k, k) for k in a]
    total = lambda a: sum(c[k] for k in a)
    return dict(m=native, i=intro, r=rare, n=sum(c.values()), key=d.get("key"), wild=bool(d.get("w")), verbatim=d.get("verbatim"),
                mk=ko(native), ik=ko(intro), mn=total(native), inn=total(intro), rn=total(rare))


ebird = load("ebird_codes.json", {})
ebird.update(load("bird_codes.json", {}))  # AviList v2026 의 eBird 종 코드가 먼저
ebird_ord = load("ebird_families.json", {})
media = {}
for f in (DATA / "media").glob("*.json"):
    m = json.loads(f.read_text(encoding="utf-8"))
    media[m["sci"]] = m
# 파충류는 시트에 영명이 없으면 iNaturalist 영명을 쓴다
for t in names:
    if t["group"] == "REPTILIA" and t["rank"] == "species" and not t.get("en"):
        t["en"] = ((media.get(t["sci"]) or {}).get("inat") or {}).get("common")
G = {"AVES": "A", "REPTILIA": "R"}
NOFAM = "미분류"  # 과·목·아속을 정하지 못한 묶음


def first_by(*ranks):
    out = {}
    for t in names:
        if t["rank"] in ranks:
            out.setdefault((t["group"], t["sci"]), t)
    return out


orders, families, genera = first_by("order", "suborder"), first_by("family"), first_by("genus")
subfams = first_by("subfamily")
# 참새목 아목·상과 (data/bird_higher.json). 국명은 모식과 국명의 '과'를 '아목'·'상과'로 바꿔 만든다.
BH = load("bird_higher.json", {})
bird_auth = load("bird_authority.json", {})  # 조류 명명자·연도 (AviList v2025, scripts/fetch_avilist.py)
_ranks = {}
for _f, (_so, _sp) in BH.get("family", {}).items():
    _ranks[_so] = "suborder"
    if _sp:
        _ranks[_sp] = "superfamily"
for _sci, _rk in _ranks.items():
    _tf = families.get(("AVES", BH.get("type_family", {}).get(_sci)), {})
    _ko = BH.get("names", {}).get(_sci)
    if not _ko and (_tf.get("name") or "").endswith("과"):
        _ko = _tf["name"][:-1] + ("아목" if _rk == "suborder" else "상과")
    orders.setdefault(("AVES", _sci), dict(group="AVES", rank=_rk, sci=_sci, name=_ko,
                                         status="derived" if _ko and _sci not in BH.get("names", {}) else ("consensus" if _ko else "none")))
# 파충류 속 → 아과 (Reptile Database 종 문서의 Higher Taxa, scripts/fetch_rdb.py --subfamilies)
sub_of = {("REPTILIA", g): sf for g, sf in load("rdb_subfamily.json", {}).items() if sf}
# 한 과의 모든 속이 같은 아과 하나뿐이면 과와 겹치는 단계라 뺀다
# (시트는 보아과를 여러 과로 나누는데 Reptile Database는 그들을 Boidae의 아과로 둔다: Erycidae → Erycinae 등)
_fam_of_genus = {}
for t in names:
    if t["group"] == "REPTILIA" and t["rank"] == "species":
        _fam_of_genus.setdefault(t["sci"].split()[0], t.get("family"))
_subs_in_fam = {}
for g, f in _fam_of_genus.items():
    _subs_in_fam.setdefault(f, set()).add(sub_of.get(("REPTILIA", g)))
for g, f in _fam_of_genus.items():
    if len(_subs_in_fam[f]) == 1:
        sub_of.pop(("REPTILIA", g), None)
subfamilies = [t for t in names if t["rank"] == "subfamily"]
# 파충류 큰 속의 아속 (시트의 아속 줄, scripts/add_subgenus_rows.py). 아속 이름만 쓴다(「Odatria」).
# 속이 바뀐 종(Reptile Database 반영)은 아속을 버린다. 아속이 있는 속에서 아속을 못 정한 종은 「미분류」.
NOSUB = "미분류"
_has_sub = lambda t: t.get("subgenus") and t.get("subgenus_genus") == t["sci"].split()[0]
subgens = {}  # (강, 속, 아속) → {sci, name}
for t in names:
    if t["rank"] == "species" and _has_sub(t):
        subgens.setdefault((t["group"], t["subgenus_genus"], t["subgenus"]), dict(sci=t["subgenus"], name=t.get("subgenus_ko")))
_sub_genera = {(g, ge) for g, ge, _ in subgens}


def subgenus_of(t):
    """그 종의 아속 이름. 아속을 쓰지 않는 속이면 None"""
    if (t["group"], t["sci"].split()[0]) not in _sub_genera:
        return None
    return t["subgenus"] if _has_sub(t) else NOSUB
species = [t for t in names if t["rank"] == "species"]
linker = Linker(names)


def pics(m):
    """대표 사진(iNaturalist 큐레이터 선정) 하나를 맨 앞에, 그 뒤로 관찰 사진. 같은 사진은 한 번만."""
    cover = [dict(c, cover=1) for c in (m.get("curated") or [])[:1]]
    pid = lambda p: p["url"].split("/photos/")[-1].split("/")[0]
    seen = {pid(c) for c in cover}
    return cover + [p for p in m.get("photos", []) if pid(p) not in seen]


has_pic = lambda sci: bool(media.get(sci, {}).get("photos") or media.get(sci, {}).get("curated"))
# 속 → 모식종: 파충류는 Reptile Database 표시, 조류(와 표시 없는 파충류 속)는 data/type_species.json (AviList 등)
type_of = {(t["group"], t["sci"].split()[0]): t["sci"] for t in names if t["rank"] == "species" and t.get("type_species")}
_sp_group = {t["sci"]: t["group"] for t in names if t["rank"] == "species"}
for gname, tsci in load("type_species.json", {}).items():
    if tsci and not gname.startswith("_") and tsci in _sp_group:
        type_of.setdefault((_sp_group[tsci], gname), tsci)


_by_sci = {}
for _t in names:
    _by_sci.setdefault(_t["sci"], _t)
NAME_ALIASES = {k: v for k, v in load("name_aliases.json", {}).items() if not k.startswith("_")}
name_changes = []  # 번역문에 자동으로 반영한 국명 변경


def show_name(sci):
    """(현재 국명, 표시할 이름). 국명이 없으면 영명, 그것도 없으면 학명. 목록에 없는 학명은 None"""
    t = _by_sci.get(sci)
    return (t.get("name"), t.get("name") or t.get("en") or f"*{sci}*") if t else None
# fetch_media.py 의 SKIP_SECTIONS 에 없던 참고문헌 절 (이미 받은 자료에서도 뺀다)
BIB_SECTIONS = {"cited texts", "cited text", "cited books", "other sources", "general bibliography", "cited literature", "literature cited",
                "sources cited", "texts cited", "general references", "general sources", "general and cited references", "cited references",
                "print sources", "web sources", "additional sources"}


def wiki_of(t, m):
    """위키 문서가 종이 아니라 속 문서이면 표시해 둔다."""
    w = linker.wiki(m.get("wiki"))
    secs = (m.get("wiki") or {}).get("sections") or []
    lead = " ".join(next((x["paras"] for x in secs if x["paras"]), []))[:500].lower()
    # 제목이 한 단어여도 Emu·Mallard 같은 종 문서가 많다. 제목이 속명이고 첫머리에 종 학명이 없을 때만 속 문서로 본다
    if w and w.get("title") == t["sci"].split()[0] and t["sci"].lower() not in lead:
        w = dict(w, genus_doc=True)
    return w


def wiki_ko_of(t, wiki):
    """data/wiki_ko 의 한국어 번역 → 종 문서용. 공개 주석만 싣고 번호를 매긴다.
    본문 속 국명은 원문 링크(ko_link)로 찾은 이름만, 문서에서 처음 나올 때 링크한다."""
    p = DATA / "wiki_ko" / (t["sci"].replace(" ", "_") + ".json")
    if not p.exists():
        return None
    k = json.loads(p.read_text(encoding="utf-8"))
    # 번역 뒤 바뀐 국명을 현재 국명으로
    wanted, skipped = ko_names.plan(k.get("names") or {}, show_name, NAME_ALIASES)
    fix = lambda s: ko_names.apply(s, wanted)
    joined = " ".join(q["text"] for s in k["sections"] for q in s["paras"])
    renamed = sorted((o, n) for o, n in wanted.items() if ko_names.pattern([o]).search(joined))
    name_changes.extend(dict(doc=t["sci"], old=o, new=n) for o, n in renamed)
    name_changes.extend(dict(doc=t["sci"], old=o, new=None, sci=s) for s, o in skipped if ko_names.pattern([o]).search(joined))
    names = {}
    for s in (wiki or {}).get("sections") or []:
        for para in s["paras"]:
            for x in [] if isinstance(para, str) else para:
                if isinstance(x, list) and x[2] in ("s", "S", "f"):
                    names.setdefault(x[0], ("s" if x[2] == "S" else x[2], x[3]))
    if t.get("name"):
        names[t["name"]] = ("s", t["sci"])
    words = sorted(names, key=len, reverse=True)
    # 이름 뒤에는 한글이 아니거나 조사만 오게 한다('매'가 '매우'에, '황새'가 '황새과'에 걸리지 않게)
    josa = r"(?:은|는|이|가|을|를|의|에|와|과|도|로|만|으로|에서|에게|보다|처럼|까지|부터|이다|이며|이고|였다|라고)?(?![가-힣])"
    pat = re.compile(r"(?<![가-힣])(" + "|".join(map(re.escape, words)) + r")(?=" + josa + ")") if words else None
    seen = set()

    def link(text):
        out, pos = [], 0
        for m in pat.finditer(text) if pat else []:
            if m.group(1) in seen:
                continue
            seen.add(m.group(1))
            if m.start() > pos:
                out.append(text[pos:m.start()])
            rk, sci = names[m.group(1)]
            out.append([m.group(1), m.group(1), rk, sci, 0])
            pos = m.end()
        if not out:
            return text
        if pos < len(text):
            out.append(text[pos:])
        return out

    notes = [n for n in k.get("notes", []) if n.get("type") != "번역 메모"]
    secs = [dict(h=s.get("h"), level=s.get("level") or 2,
                 paras=[dict(p=link(fix(q["text"])), n=[i + 1 for i, n in enumerate(notes) if n["ref"] == q["ref"]]) for q in s["paras"]])
            for s in k["sections"]]
    return dict(revision=k.get("revision"), date=k.get("date"), translator=k.get("translator"), sections=secs, skipped=k.get("skipped") or [],
                renamed=renamed, notes=[dict(type=n["type"], text=fix(n["text"])) for n in notes])


dump = lambda obj: json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
fname = lambda sci: sci.replace(" ", "_") + ".json"


def photo_credit(p):
    """미리보기 설명 줄에 넣을 사진 저작자와 라이선스."""
    a = p.get("attribution") or ""
    m = re.match(r"\(c\)\s*(.*?),\s*(?:some|all|no) rights", a, re.I) or re.match(r"(.*?),?\s*no rights reserved", a, re.I)
    who = m.group(1) if m else a
    lic = (p.get("license") or "").upper().replace("CC-", "CC ")
    return f"{who} ({lic})" if who and lic else who or lic


def share_tags(rec):
    """채팅앱 등이 링크 미리보기로 읽는 <title>과 Open Graph 태그."""
    e = lambda s: html.escape(str(s), quote=True)
    title = " ".join(filter(None, [rec["name"] or rec["en"], rec["sci"]]))
    fam = rec["family"] or {}
    desc = [rec["en"] if rec["name"] else None, "조류" if rec["group"] == "AVES" else "파충류", fam.get("name") or fam.get("sci")]
    ph = (rec["photos"] or [None])[0]
    if ph:
        desc.append("사진: " + photo_credit(ph))
    desc = " · ".join(filter(None, desc))
    url = SITE_URL + "sp/" + quote(rec["sci"].replace(" ", "_")) + ".html"
    tags = [f"<title>{e(rec['name'] or rec['en'] or rec['sci'])} · Vertapedia</title>",
            f'<meta name="description" content="{e(desc)}">',
            '<meta property="og:site_name" content="Vertapedia">',
            '<meta property="og:type" content="article">',
            f'<meta property="og:url" content="{e(url)}">',
            f'<meta property="og:title" content="{e(title)}">',
            f'<meta property="og:description" content="{e(desc)}">']
    if ph:
        tags += [f'<meta property="og:image" content="{e(ph["url"].replace("{size}", "large"))}">',
                 f'<meta property="og:image:alt" content="{e(title)}">',
                 '<meta name="twitter:card" content="summary_large_image">']
    return "\n".join(tags)


def short(t):
    return dict(sci=t["sci"], name=t.get("name"), status=t["status"]) if t else None


def lineage(t):
    """(목, 아목, 상과) — 과 행에 적힌 것, 없으면 eBird 과 → 목, 분류미정 탭이면 그 탭의 목·아목.
    조류 참새목은 data/bird_higher.json 의 아목·상과."""
    fam = families.get((t["group"], t.get("family"))) or {}
    o = fam.get("order") or t.get("order_hint") or (ebird_ord.get(t.get("family")) if t["group"] == "AVES" else None)
    so = fam.get("suborder") or t.get("suborder_hint")
    sp = None
    if t["group"] == "AVES" and t.get("family") in BH.get("family", {}):
        so, sp = BH["family"][t["family"]]
    return o, so, sp


def taxon(rank_map, g, sci):
    x = rank_map.get((g, sci))
    return short(x) if x else ({"sci": sci} if sci else None)


# --- 분류군: 내부 마디 [계급, 학명, 국명, 자식들], 종 [학명, 국명, 영명, 사진] ---
tree = {}
for t in species:
    g = t["group"]
    o, so, sup = lineage(t)
    sf = sub_of.get((g, t["sci"].split()[0]))
    path = [("o", o or "미분류")] + ([("u", so)] if so else []) + ([("p", sup)] if sup else []) +         [("f", t.get("family") or NOFAM)] +         ([("s", sf)] if sf else []) + [("g", t["sci"].split()[0])] + \
        ([("h", subgenus_of(t))] if subgenus_of(t) else [])
    node = tree.setdefault(g, {})
    for key in path:
        node = node.setdefault(key, {})
    node.setdefault("_sp", []).append(t)


def emit(g, d, genus=None):
    out = []
    for key, child in d.items():
        if key == "_sp":
            continue
        rank, sci = key
        src = {"o": orders, "u": orders, "p": orders, "f": families, "s": subfams, "g": genera}.get(rank)
        x = src.get((g, sci)) if src else subgens.get((g, genus, sci))
        kids = [[s["sci"], s.get("name"), s.get("en"), 1 if has_pic(s["sci"]) else 0] for s in child["_sp"]] \
            if set(child) == {"_sp"} else emit(g, child, sci if rank == "g" else genus)  # 아속이 있는 속은 속 → 아속 → 종
        out.append([rank, sci, x.get("name") if x else None, kids] + ([type_of[(g, sci)]] if rank == "g" and (g, sci) in type_of else []))
    return out


(SITE / "data").mkdir(parents=True, exist_ok=True)
(SITE / "data" / "tree.json").write_text(dump({G[g]: emit(g, d) for g, d in tree.items()}), encoding="utf-8")

# --- 검색 목록 ---
rows = []
for t in names:
    if t["rank"] not in ("order", "suborder", "family", "genus", "species"):
        continue
    ssp = [[s["sci"], s.get("ko"), s.get("note")] for s in t.get("subspecies", []) if s.get("ko")]
    fam = families.get((t["group"], t.get("family")))
    rk = "u" if t["rank"] == "suborder" else t["rank"][0]
    # 별칭: 환경부 지정명·국내 관용명(정식 국명과 다를 때만)
    alias = [[label, v] for label, v in (("환경부 지정명", t.get("moe")), ("국내 관용명", t.get("trade")))
             if v and v not in ("-", t.get("name"))]
    rows.append([G[t["group"]], rk, t["sci"], t.get("name"), t.get("en"),
                 t["status"], t.get("family"), ssp or None, (fam or {}).get("name"), 1 if has_pic(t["sci"]) else 0,
                 alias or None])
(SITE / "data" / "names.min.json").write_text(dump(rows), encoding="utf-8")

# --- 첫 화면에 띄울 종 ---
pool = [t["sci"] for t in species if t.get("name") and has_pic(t["sci"])]
(SITE / "data" / "random.json").write_text(dump(pool), encoding="utf-8")

# --- 종 문서 ---
shutil.rmtree(SITE / "sp", ignore_errors=True)
(SITE / "sp").mkdir(parents=True)
seq = {g: [t for t in species if t["group"] == g] for g in G}
shares = {}
for g, lst in seq.items():
    for i, t in enumerate(lst):
        o, so, sup = lineage(t)
        m = media.get(t["sci"], {})
        nb = lambda j: short(lst[j]) if 0 <= j < len(lst) else None
        rec = dict(
            group=g, sci=t["sci"], name=t.get("name"), status=t["status"], en=t.get("en"),
            author=t.get("author") or (bird_auth.get(t["sci"]) if g == "AVES" else None),
            rationale=t.get("rationale") if t["status"] in ("consensus", "proposal") else None,
            review=t.get("review") if "국가생물종목록" not in (t.get("review") or "") else None,
            synonyms=t.get("synonyms"),
            order=taxon(orders, g, o), suborder=taxon(orders, g, so), superfamily=taxon(orders, g, sup),
            family=taxon(families, g, t.get("family")),
            genus=dict(taxon(genera, g, t["sci"].split()[0]), type=type_of.get((g, t["sci"].split()[0]))),
            type_species=type_of.get((g, t["sci"].split()[0])) == t["sci"],
            subfamily=taxon(subfams, g, sub_of.get((g, t["sci"].split()[0]))),
            subgenus=(subgens.get((g, t["sci"].split()[0], subgenus_of(t))) or {"sci": NOSUB}) if subgenus_of(t) else None,
            subspecies=subspecies_of(t),
            kos=dict(category=t["kos"].get("category")) if t.get("kos") else None, kr=t.get("kr"),
            refs=dict(official=None,  # 국가생물종목록은 쓰지 않는다
                      moe=t.get("moe"), trade=t.get("trade")),
            ebird=ebird.get(t["sci"]),
            dist=dist_of(t["sci"]), range=bird_range.get(t["sci"]) if g == "AVES" else None,
            iucn=(bird_iucn.get(t["sci"]) if g == "AVES" else None) or (dist.get(t["sci"]) or {}).get("iucn"),
            inat=m.get("inat"), photos=pics(m), wiki=wiki_of(t, m), fetched=m.get("fetched"),
            prev=nb(i - 1), next=nb(i + 1), pos=[i + 1, len(lst)],
        )
        rec["wiki_ko"] = wiki_ko_of(t, rec["wiki"])
        if rec["wiki"]:
            rec["wiki"] = dict(rec["wiki"], sections=[s for s in rec["wiki"].get("sections") or []
                                                      if (s.get("h") or "").strip().lower() not in BIB_SECTIONS])
        (SITE / "sp" / fname(t["sci"])).write_text(dump(rec), encoding="utf-8")
        shares[t["sci"]] = share_tags(rec)

# --- 과 문서: 명칭 근거 + 포함 속·종 ---
shutil.rmtree(SITE / "fam", ignore_errors=True)
(SITE / "fam").mkdir(parents=True)
fam_seq = {g: [] for g in G}
for t in species:  # 종이 실제로 있는 과만, 시트 순서대로
    k = (t["group"], t.get("family"))
    if t.get("family") and k in families and families[k] not in fam_seq[t["group"]]:
        fam_seq[t["group"]].append(families[k])
for g, lst in fam_seq.items():
    for i, f in enumerate(lst):
        sps = [t for t in seq[g] if t.get("family") == f["sci"]]
        gens = {}
        for s in sps:
            gens.setdefault(s["sci"].split()[0], []).append(s)
        o, so, sup = lineage(sps[0])
        nb = lambda j: short(lst[j]) if 0 <= j < len(lst) else None
        rec = dict(
            group=g, sci=f["sci"], name=f.get("name"), status=f["status"], en=f.get("en"),
            rationale=f.get("rationale"),
            refs=dict(official=None,
                      kos=(f.get("kos") or {}).get("ko") if f["status"] != "kos" else None),
            order=taxon(orders, g, o), suborder=taxon(orders, g, so), superfamily=taxon(orders, g, sup),
            subfamilies=[dict(sci=x["sci"], name=x.get("name"), en=x.get("en"), rationale=x.get("rationale"))
                         for x in subfamilies if x["group"] == g and x.get("family") == f["sci"]],
            genera=[dict(sci=ge, name=(genera.get((g, ge)) or {}).get("name"), subfamily=sub_of.get((g, ge)),
                         type=type_of.get((g, ge)),
                         status=(genera.get((g, ge)) or {}).get("status"),
                         rationale=(genera.get((g, ge)) or {}).get("rationale"),
                         subgenera={k: v.get("name") for (gg, gn, k), v in subgens.items() if gg == g and gn == ge},
                         species=[[s["sci"], s.get("name"), s.get("en"), s["status"], 1 if has_pic(s["sci"]) else 0]
                                  + ([subgenus_of(s)] if subgenus_of(s) else [])
                                  for s in ss]) for ge, ss in gens.items()],
            counts=dict(genera=len(gens), species=len(sps), named=sum(1 for s in sps if s.get("name"))),
            prev=nb(i - 1), next=nb(i + 1), pos=[i + 1, len(lst)],
        )
        (SITE / "fam" / fname(f["sci"])).write_text(dump(rec), encoding="utf-8")

(DATA / "name_changes.json").write_text(json.dumps(name_changes, ensure_ascii=False, indent=0), encoding="utf-8")  # 검토 페이지에서 읽는다

# --- 분포 지도 ---
# 지역을 나눈 세계지도(scripts/build_world_map.py). 지도에 마우스를 올리면 한국어 이름
world = load("world.geojson", {"features": []})


def densify(ring, step=2.0):
    """긴 변에 점을 넣는다. d3 는 변을 대권 곡선으로 그려서, 북위 49도 같은 긴 국경의 끝점이 조금만 달라도 두 나라 사이가 벌어진다."""
    out = [ring[0]]
    for a, b in zip(ring, ring[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        n = int(max(abs(dx), abs(dy)) // step) if abs(dx) < 180 else 0
        out += [[round(a[0] + dx * i / (n + 1), 2), round(a[1] + dy * i / (n + 1), 2)] for i in range(1, n + 1)] + [b]
    return out


def real_hole(ring):
    """지역을 합칠 때 생긴 가느다란 틈이 아니라 넓이가 있는 구멍인가"""
    area = abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(ring, ring[1:]))) / 2
    length = sum(((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** .5 for a, b in zip(ring, ring[1:]))
    return area >= .3 and 12.57 * area / (length * length or 1) >= .1


for f in world["features"]:
    f["properties"]["n"] = REGION_KO.get(f["properties"]["c"], f["properties"]["n"])
    g = f["geometry"]
    polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
    polys = [[densify(p[0])] + [densify(h) for h in p[1:] if real_hole(h)] for p in polys if p]
    g["coordinates"] = polys if g["type"] == "MultiPolygon" else (polys[0] if polys else [])
(SITE / "data" / "world.json").write_text(json.dumps(world, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

# --- 페이지 ---
stats = {g: dict(total=len(seq[g]), named=sum(1 for t in seq[g] if t.get("name")),
                 photos=sum(1 for t in seq[g] if has_pic(t["sci"])),
                 translated=sum(1 for t in seq[g] if (DATA / "wiki_ko" / fname(t["sci"])).exists())) for g in G}
meta = dict(stats=stats, built=datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M KST"))
for name in ("index", "find", "fam"):
    tpl = (SITE / f"{name}.template.html").read_text(encoding="utf-8")
    (SITE / f"{name}.html").write_text(tpl.replace("/*META*/null", json.dumps(meta, ensure_ascii=False)), encoding="utf-8")

# 종 문서: 2만 개가 넘으니 CSS와 JS는 한 벌만 두고 종별 HTML은 머리말과 뼈대만 담는다
tpl = (SITE / "sp.template.html").read_text(encoding="utf-8").replace("/*META*/null", json.dumps(meta, ensure_ascii=False))
css_at, css_end = tpl.index("<style>"), tpl.index("</style>")
(SITE / "sp.css").write_text(tpl[css_at + len("<style>"):css_end], encoding="utf-8")
js_at, js_end = tpl.rindex("<script>"), tpl.rindex("</script>")
(SITE / "sp.js").write_text(tpl[js_at + len("<script>"):js_end], encoding="utf-8")
shell = (tpl[:css_at] + '<link rel="stylesheet" href="sp.css">' + tpl[css_end + len("</style>"):js_at]
         + '<script src="sp.js"></script>' + tpl[js_end + len("</script>"):])
shell = shell.replace('<meta charset="utf-8">', '<meta charset="utf-8">\n<base href="../">', 1)
for sci, tags in shares.items():
    (SITE / "sp" / (sci.replace(" ", "_") + ".html")).write_text(shell.replace("<title>Vertapedia</title>", tags, 1), encoding="utf-8")
# 옛 주소 sp.html#학명
(SITE / "sp.html").write_text("""<!doctype html>
<html lang="ko">
<meta charset="utf-8">
<title>Vertapedia</title>
<script>const s=decodeURIComponent(location.hash.slice(1)).replace(/ /g,'_');location.replace(s?'sp/'+encodeURIComponent(s)+'.html':'find.html')</script>
</html>
""", encoding="utf-8")
print("검색 목록", len(rows), "· 종 문서", len(species), "· 과 문서", sum(len(v) for v in fam_seq.values()),
      "· 첫 화면 후보", len(pool))
