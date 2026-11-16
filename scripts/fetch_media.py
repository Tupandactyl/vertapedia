"""종마다 iNaturalist 사진·영문 위키백과 본문을 받아 data/media/<학명>.json 에 둔다.

- 사진은 재사용 가능한 라이선스(CC0, CC BY, CC BY-SA, CC BY-NC, CC BY-NC-SA)만 받는다.
- iNaturalist 권고에 맞춰 1초에 한 번 이하로 부른다.
- 이미 받은 종은 --max-age 일이 지나기 전에는 다시 받지 않는다. 못 찾은 종은 RETRY_DAYS 일마다 다시 묻는다
  (iNaturalist 가 새 학명을 뒤늦게 등록하기 때문이다).

    python scripts/fetch_media.py                 # 국명이 있는 한국 출현종 (--scope named/unnamed/all)
    python scripts/fetch_media.py --limit 200     # 이번에 새로 받을 최대 종 수
    python scripts/fetch_media.py --covers        # 이미 받은 종에 대표 사진(큐레이터 선정)만 채우기
    python scripts/fetch_media.py --wiki-fix      # 위키 문서가 없거나 속 문서뿐인 종을 옛 학명·영명으로 다시 찾기
    python scripts/fetch_media.py --commons       # iNaturalist 사진이 2장 이하인 종에 위키미디어 커먼즈 자유 이미지(논문 도판·표본 포함) 채우기

위키 문서: data/wiki_overrides.json 에 적은 문서 → iNaturalist 가 걸어 둔 문서 → 학명·옛 학명·영명으로 찾은 문서(wiki_found) 순서.
찾은 문서는 첫머리에 그 종의 학명(또는 옛 학명)과 영명이 함께 있을 때만 받아들인다.
"""
import argparse
import html
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = DATA / "media"
UA = {"User-Agent": "Vertapedia/0.1 (https://github.com/Tupandactyl/vertapedia)"}
LICENSES = "cc0,cc-by,cc-by-sa,cc-by-nc,cc-by-nc-sa"
PER_SPECIES = 8
RETRY_DAYS = 7

_last = [0.0]


def get(url, params=None):
    if params:
        url += "?" + urllib.parse.urlencode(params)
    wait = 1.05 - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    for attempt in range(4):
        _last[0] = time.time()
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if e.code in (429, 500, 502, 503) and attempt < 3:
                time.sleep(10 * (attempt + 1))
                continue
            raise
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
            if attempt < 3:  # 연결이 끊기면 잠깐 쉬고 다시
                time.sleep(15 * (attempt + 1))
                continue
            raise


def inat_taxon(sci):
    # 흔한 학명은 아종·동명 분류군이 앞에 와서 10개 안에 종이 없을 수 있다 → 종 계급으로 먼저 찾는다
    for endpoint, extra in (("taxa/autocomplete", {}), ("taxa", dict(rank="species"))):
        d = get("https://api.inaturalist.org/v1/" + endpoint, dict(q=sci, is_active="true", per_page=20, **extra))
        for t in (d or {}).get("results", []):
            if t["name"] == sci:
                return t
    d = get("https://api.inaturalist.org/v1/taxa", dict(q=sci, is_active="true", per_page=10))
    for t in (d or {}).get("results", []):
        if t["name"] == sci:
            return t
    for t in (d or {}).get("results", []):  # 학명이 이명으로만 걸린 경우
        if sci in (t.get("matched_term") or "") and t["rank"] in ("species", "subspecies"):
            return t
    return None


def inat_photos(taxon_id):
    d = get("https://api.inaturalist.org/v1/observations", dict(
        taxon_id=taxon_id, quality_grade="research", photos="true", photo_license=LICENSES,
        order_by="votes", per_page=PER_SPECIES * 2))
    out, seen_users = [], {}
    for o in (d or {}).get("results", []):
        for p in o.get("photos", [])[:1]:
            if not p.get("license_code"):
                continue
            user = (o.get("user") or {}).get("login")
            if seen_users.get(user, 0) >= 2:  # 한 사람 사진이 갤러리를 채우지 않게
                continue
            seen_users[user] = seen_users.get(user, 0) + 1
            out.append(dict(url=p["url"].replace("/square.", "/{size}."), license=p["license_code"],
                            attribution=p.get("attribution"), obs=o["id"], place=o.get("place_guess"),
                            date=o.get("observed_on")))
        if len(out) >= PER_SPECIES:
            break
    return out


def curated(taxon_photos, n=3):
    """iNaturalist 큐레이터가 고른 분류군 대표 사진(재사용 허락된 것만). 대표 사진은 여기서 고른다."""
    ok = set(LICENSES.split(","))
    out = []
    for tp in taxon_photos or []:
        p = tp.get("photo") or {}
        if (p.get("license_code") or "") in ok:
            out.append(dict(url=re.sub(r"/square\.", "/{size}.", p["url"]), license=p["license_code"],
                            attribution=p.get("attribution"), photo=p["id"]))
        if len(out) >= n:
            break
    return out


def inat_curated_many(ids, with_common=False):
    """여러 분류군을 한 번에(30개씩) 불러 대표 사진을 얻는다 → {id: [사진]} (with_common 이면 {id: (사진, 영명)})"""
    d = get("https://api.inaturalist.org/v1/taxa/" + ",".join(map(str, ids)), dict(locale="en"))
    res = (d or {}).get("results", [])
    if with_common:
        return {t["id"]: (curated(t.get("taxon_photos")), t.get("preferred_common_name")) for t in res}
    return {t["id"]: curated(t.get("taxon_photos")) for t in res}


def backfill_common():
    """iNaturalist 영명(preferred_common_name)을 inat.common 에 채운다(30개씩 묶어 부른다)."""
    todo = []
    for f in sorted(OUT.glob("*.json")):
        m = json.loads(f.read_text(encoding="utf-8"))
        if m.get("inat") and "common" not in m["inat"]:
            todo.append((f, m))
    for k in range(0, len(todo), 30):
        chunk = todo[k:k + 30]
        got = inat_curated_many([m["inat"]["id"] for _, m in chunk], with_common=True)
        for f, m in chunk:
            m["inat"]["common"] = (got.get(m["inat"]["id"]) or (None, None))[1]
            f.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"영명 {min(k + 30, len(todo))}/{len(todo)}", flush=True)
    print("영명 채운 종:", len(todo))


def backfill_covers():
    """이미 받은 자료에 대표 사진이 없으면 채운다(분류군 30개씩 묶어 부르므로 빠르다)."""
    todo = []
    for f in sorted(OUT.glob("*.json")):
        m = json.loads(f.read_text(encoding="utf-8"))
        if m.get("inat") and "curated" not in m:
            todo.append((f, m))
    for k in range(0, len(todo), 30):
        chunk = todo[k:k + 30]
        got = inat_curated_many([m["inat"]["id"] for _, m in chunk])
        for f, m in chunk:
            m["curated"] = got.get(m["inat"]["id"], [])
            f.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"대표 사진 {min(k + 30, len(todo))}/{len(todo)}", flush=True)
    print("대표 사진 채운 종:", len(todo))


SKIP_SECTIONS = {"references", "external links", "see also", "further reading", "notes", "sources",
                 "bibliography", "gallery", "footnotes", "citations", "cited sources", "works cited"}


def wiki_full(url):
    """영문 위키백과 본문 전체(일반 텍스트)를 절 단위로 받는다. 참고문헌·바깥 링크 절은 뺀다."""
    if not url:
        return None
    title = urllib.parse.unquote(url.rsplit("/wiki/", 1)[-1]).replace("_", " ")
    d = get("https://en.wikipedia.org/w/api.php", dict(
        action="query", prop="extracts|info|pageprops", explaintext=1, exsectionformat="wiki",
        redirects=1, titles=title, format="json", formatversion=2))
    pages = (d or {}).get("query", {}).get("pages", [])
    if not pages or pages[0].get("missing") or "disambiguation" in pages[0].get("pageprops", {}):
        return None
    pg = pages[0]
    text = pg.get("extract") or ""
    sections, cur = [], dict(h=None, level=1, text=[])
    for line in text.splitlines():
        m = re.match(r"^(={2,5})\s*(.*?)\s*\1$", line.strip())
        if m:
            sections.append(cur)
            cur = dict(h=m.group(2), level=len(m.group(1)), text=[])
        else:
            cur["text"].append(line)
    sections.append(cur)
    out, skip_level = [], None
    for sec in sections:
        if skip_level is not None and sec["level"] > skip_level:
            continue
        skip_level = None
        if sec["h"] and sec["h"].strip().lower() in SKIP_SECTIONS:
            skip_level = sec["level"]
            continue
        paras = [p.strip() for p in sec["text"] if p.strip()]
        if paras or sec["h"]:
            out.append(dict(h=sec["h"], level=sec["level"], paras=paras))
    out = [s for i, s in enumerate(out) if s["paras"] or (i + 1 < len(out) and out[i + 1]["level"] > s["level"])]
    return dict(title=pg["title"], url="https://en.wikipedia.org/wiki/" + urllib.parse.quote(pg["title"].replace(" ", "_")),
                revision=pg.get("lastrevid"), sections=out)


OVERRIDES = json.loads((DATA / "wiki_overrides.json").read_text(encoding="utf-8")) if (DATA / "wiki_overrides.json").exists() else {}
_old_names = {}


def norm_name(s):
    return re.sub(r"[-‐–'’\s]+", " ", s or "").lower().strip()


def lead_of(w):
    for sec in w.get("sections") or []:
        if sec["paras"]:
            return " ".join(sec["paras"])[:500]
    return ""


def is_genus_doc(w, sci):
    """종이 아니라 속을 다루는 문서인가: 제목이 속명이고 첫머리에 종 학명이 없다"""
    return bool(w) and w.get("title") == sci.split()[0] and sci.lower() not in lead_of(w).lower()


def wiki_find(t):
    """지금 학명·옛 학명·영명으로 문서를 찾는다. 첫머리에 학명류와 영명이 모두 있어야 받는다."""
    sci, en = t["sci"], t.get("en")
    binoms = _old_names.get(sci) or [sci]
    tried = set()
    for c in binoms + ([en] if en else []):
        w = wiki_full("/wiki/" + c)
        if not w or w["title"] in tried or not w.get("sections"):
            continue
        tried.add(w["title"])
        lead = lead_of(w).lower()
        # 학명으로 찾아 들어왔고 제목이 영명과 같으면 첫머리 학명에 오타가 있어도 받는다(Schoeniclusa tristrami)
        same_title = c in binoms and en and norm_name(en) == norm_name(w["title"])
        if not same_title and not any(b.lower() in lead for b in binoms):
            continue
        if en and norm_name(en) not in norm_name(w["title"]) and norm_name(en) not in norm_name(lead):
            continue
        return dict(w, found_by=c)
    return None


def wiki_for(t, inat_url, old=None):
    """종의 위키 문서: 지정 문서 → iNaturalist 문서 → 찾은 문서 → 전에 찾아 둔 문서"""
    if t["sci"] in OVERRIDES:
        w = wiki_full("/wiki/" + OVERRIDES[t["sci"]])
        if w:
            return w
    w = wiki_full(inat_url)
    if w and w.get("sections") and not is_genus_doc(w, t["sci"]):
        return w
    found = wiki_find(t)
    if found:
        return found
    prev = (old or {}).get("wiki") or {}
    return prev if prev.get("found_by") else w


def load_old_names(names):
    from fetch_distribution import old_names
    _old_names.update(old_names(names, [t for t in names if t["rank"] == "species"]))


def wiki_fix(scope):
    """문서가 없거나 속 문서뿐인 종, 지정 문서가 있는 종을 다시 찾는다."""
    names = json.loads((DATA / "names.json").read_text(encoding="utf-8"))
    load_old_names(names)
    fixed = checked = 0
    for t in targets(scope):
        f = OUT / (t["sci"].replace(" ", "_") + ".json")
        m = json.loads(f.read_text(encoding="utf-8")) if f.exists() else dict(sci=t["sci"], fetched=date.today().isoformat(), inat=None, photos=[], wiki=None)
        w = m.get("wiki") or {}
        if t["sci"] in OVERRIDES:
            new = wiki_full("/wiki/" + OVERRIDES[t["sci"]])
        elif w.get("sections") and not is_genus_doc(w, t["sci"]):
            continue
        else:
            checked += 1
            new = wiki_find(t)
        if new and new.get("title") != w.get("title"):
            print(t["sci"], "|", w.get("title"), "→", new["title"], "|", new.get("found_by"), flush=True)
            m["wiki"] = new
            f.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
            fixed += 1
    print(f"위키 문서 다시 찾기: 확인 {checked} · 바꿈 {fixed}")


# --- 위키미디어 커먼즈: iNaturalist 사진이 없는 종만 ---
# 자유 라이선스(CC0·퍼블릭 도메인·CC BY·CC BY-SA)만 쓴다. 논문 도판·표본 사진·옛 삽화도 받되 지도·도식은 뺀다.
# 위키데이터 대표 이미지(P18)를 먼저, 그다음 커먼즈 'Category:<학명>' 파일.
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
COMMONS_SKIP = re.compile(r"distribut|range|map|karte|verbreitung|areal|locator|svg$|\.gif$|\.pdf$|\.djvu$|sound|\.ogg$|\.wav$|\.mp3$|\.webm$", re.I)
COMMONS_FREE = re.compile(r"^(cc0|public domain|pd|pd-|cc by(-sa)? ?\d|cc-by(-sa)?-?\d|cc by(-sa)?$)", re.I)


def wiki_get(url, params):
    """위키미디어 API(1초에 여러 번까지 괜찮지만 0.3초 간격으로)"""
    url += "?" + urllib.parse.urlencode(dict(params, format="json"))
    for attempt in range(4):
        try:
            time.sleep(0.3)
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as r:
                return json.load(r)
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
            time.sleep(5 * (attempt + 1))
    return {}


def wikidata_p18(scis):
    """학명 → 위키데이터 대표 이미지 파일 이름"""
    out = {}
    for i in range(0, len(scis), 150):
        part = scis[i:i + 150]
        q = "SELECT ?n ?img WHERE { VALUES ?n {%s} ?i wdt:P225 ?n . ?i wdt:P18 ?img }" % " ".join(json.dumps(x) for x in part)
        req = urllib.request.Request("https://query.wikidata.org/sparql", headers=dict(UA, Accept="application/sparql-results+json"),
                                     data=urllib.parse.urlencode({"query": q}).encode())
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=90) as r:
                    for b in json.load(r)["results"]["bindings"]:
                        f = urllib.parse.unquote(b["img"]["value"].rsplit("/", 1)[-1])
                        out.setdefault(b["n"]["value"], []).append("File:" + f)
                break
            except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
                time.sleep(10 * (attempt + 1))
        time.sleep(1)
    return out


def strip_html(h):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", h or "")).strip()


# 커먼즈 작가 표기 정리
_YEAR = re.compile(r"\((?:\d{1,2} \w+ )?(\d{4})[a-z]?\)")
_INIT = re.compile(r"^(?:[A-ZÀ-Ý][a-z]?\.?[\s-]*){1,3}$")  # 'G.', 'W. R.', 'J-P'
_ORG = re.compile(r"Service|Department|Dept|Museum|Universit|Library|Institut|Center|Centre|Archive|Images|Wikipedia|Society|Survey|Collection|Commons|Conservation|Corporation|Press|USA|U\.S\.|Firm|Expedition|Laborator|Photography", re.I)
_NAME = re.compile(r"^(?:(?:de|da|dos|van|von|del|du|le|la) )?(?:[A-ZÀ-Ý][\w.'’-]*|[A-Z]{1,4})(?: (?:[A-ZÀ-Ý][\w.'’-]*|[A-Z]{1,4}|de|da|dos|das|do|van|von|der|den|del|la|le|du|Jr\.?)){0,5}$")
_UNKNOWN = {"", "unknown", "unspecified", "unknown artist", "anonymous", "unknown author"}


def _lead_bracket(s):
    """맨 앞 [ … ] 또는 ( … ) 묶음(사진 출처 설명)을 뗀다. 괄호가 겹쳐도 짝을 맞춘다."""
    s = s.lstrip()
    if not s or s[0] not in "[(":
        return s
    close, depth = {"[": "]", "(": ")"}[s[0]], 0
    for i, ch in enumerate(s):
        if ch == s[0]:
            depth += 1
        elif ch == close:
            depth -= 1
            if depth == 0:
                return s[i + 1:].lstrip()
    return s


def _people(a):
    """저자·작가 목록 → 사람(또는 단체) 이름 목록"""
    a = re.sub(r"\s*\([^()]*\)", "", a).strip(" .,;&")
    if ";" in a:
        parts = [p.strip(" .") for p in a.split(";")]
    else:
        ch = [c.strip() for c in re.split(r",|&| and | dan ", a) if c.strip()]
        parts, i = [], 0
        while i < len(ch):  # 'Chávez, G.' 꼴은 성과 머리글자를 다시 붙인다
            if " " not in ch[i] and i + 1 < len(ch) and _INIT.match(ch[i + 1]):
                parts.append(f"{ch[i]}, {ch[i + 1]}"); i += 2
            else:
                parts.append(ch[i]); i += 1
    out = []
    for p in parts:
        p = p.strip(" .")
        if p and not re.match(r"^\d", p) and p not in out:
            out.append(p)
    return out


def _names(parts, cite=False):
    if not parts:
        return ""
    if not cite:  # 첫 이름 뒤에서는 사람 이름처럼 보이는 것만 센다(단체·지명은 빼고, 설명문이 끼어 있으면 첫 이름만)
        if any(re.match(r"^[a-z]", p) and not re.match(r"^(?:de|da|dos|van|von|del|du|le|la) ", p) for p in parts[1:]):
            return parts[0]
        parts = parts[:1] + [p for p in parts[1:] if _NAME.match(p.replace(", ", " ")) and not _ORG.search(p)]
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2 and len(parts[0]) + len(parts[1]) <= 34:
        return f"{parts[0]} & {parts[1]}"
    return parts[0] + " 외"


def clean_artist(s, limit=48):
    """커먼즈 작가 표기를 짧게: 논문은 '첫 저자 외 (연도)', 사진 설명·URL·생몰년·군더더기 머리말은 뺀다."""
    s = html.unescape(s or "").replace("\ufeff", "").strip()
    s = re.sub(r"(Unknown author)+", "", s).strip()
    s = re.sub(r"^(?:\*?(?:File:)?[^:*]+\.(?:jpe?g|png|tiff?|svg|gif)\s*:\s*)+", "", s, flags=re.I)
    s = re.sub(r"\s*\*?derivative work:.*$", "", s, flags=re.I)
    m = re.match(r"^No machine-readable author provided\.\s*(\S+?)(?:~commonswiki)? assumed", s)
    if m:
        return m.group(1)
    m = re.match(r"^(?:The )?original uploader was (\S+)", s, flags=re.I)
    if m:
        return m.group(1)
    m = re.match(r"^\(c\)\s*(.+?),\s*some rights reserved", s, flags=re.I)
    if m:
        return m.group(1)
    m = re.match(r"^iNat\w*(?: [\w ]+?)? user:\s*(\S+)", s, flags=re.I)
    if m:
        return m.group(1) + " (iNaturalist)"
    if re.fullmatch(r"https?://\S+", s):
        host = re.sub(r"^https?://(www\.)?", "", s).split("/")[0]
        return "Flickr" if "flickr" in host else host
    s = re.sub(r"^(?:image credit|artist|author|künstler|artist/künstler|photographer|designer)\s*:\s*©?\s*", "", s, flags=re.I)
    s = re.sub(r"^(?:Artwork|Drawn|Depiction|Photographs?|All photographs|By|This illustration was made)\s+by\s+|^By\s+|^Author\s+", "", s, flags=re.I)
    s = re.sub(r"^unknown:\s*|\s*\(create creator page\)\s*(?:unknown:\s*)?", lambda m: "" if m.start() == 0 else ", ", s)
    s = re.sub(r"\s*-\s*BIOWEB,?\s*", ", ", s)
    s = re.sub(r"^((?:\S+ ){0,3}\S+) from [A-Z][^,]*(?:,.*)?$", r"\1", s)  # Flickr 'X from 도시, 나라'
    if re.match(r"^Photo\w*(?: credits)?\s*:", s, flags=re.I) and not _YEAR.search(s):
        s = re.sub(r"^Photo\w*(?: credits)?\s*:\s*", "", s, flags=re.I)
        s = re.sub(r"(?:(?<=^)|(?<=; ))[A-J](?:\s*[,–-]\s*[A-J])*\s*[.:=]\s*", "", s)  # 'A, C, D.' 같은 그림 칸 표시
    s = re.sub(r"\S+@\S+|\s*\(?https?://[^\s)]*\)?", "", s)  # 메일·URL
    if "@" in s:
        s = re.sub(r"\s*∙.*$", "", s)
        s = re.sub(r"(?<=[a-z])\d+(?:,\d+)*", "", s)  # 'Rijsdijk1,9' 소속 번호
    s = re.sub(r"\s*\((?:Life time:)?[^()]*\d{4}\s*[-–][^()]*\)|\s*\(d\. \d{4}.*$|,?\s*\d{4}\s*[-–]\s*\d{4}\b", "", s)  # 생몰년
    s = s.strip(" ,;")
    y = _YEAR.search(s)
    if y:  # 논문 인용
        a = _lead_bracket(s[:y.start()])
        a = re.sub(r"^Photo\w*:.*?\.\s+(?=[A-Z])", "", a)
        a = a.replace("et al.", "et al")
        if "et al" in a:
            return f"{a.split('et al')[0].strip(' ,')} 외 ({y.group(1)})"
        nm = _names(_people(a), cite=True)
        if nm:
            return f"{nm} ({y.group(1)})"
    if s.lower() in _UNKNOWN or re.match(r"^Unknown,", s):
        return ""
    if len(s) > limit:
        s = _lead_bracket(s)
    if len(s) > limit or ";" in s:
        nm = _names(_people(s))
        if nm and len(nm) <= limit:
            return nm
    if len(s) > limit:
        s = s[:limit].rsplit(" ", 1)[0].rstrip(" ,;-–") + "…"
    return re.sub(r"(?<=\w{3})\.$", "", s)


def commons_info(titles):
    """파일 이름들 → 표시용 사진 정보(자유 라이선스·사진 파일만)"""
    out = {}
    for i in range(0, len(titles), 40):
        d = wiki_get(COMMONS_API, dict(action="query", titles="|".join(titles[i:i + 40]), prop="imageinfo",
                                       iiprop="url|extmetadata|mime", iiurlwidth=800))
        for pg in (d.get("query") or {}).get("pages", {}).values():
            ii = (pg.get("imageinfo") or [None])[0]
            if not ii or not ii.get("mime", "").startswith("image/") or ii["mime"] in ("image/svg+xml", "image/gif"):
                continue
            em = ii.get("extmetadata") or {}
            lic = strip_html((em.get("LicenseShortName") or {}).get("value"))
            if not COMMONS_FREE.match(lic):
                continue
            out[pg["title"]] = dict(src="commons", url=(ii.get("thumburl") or ii["url"]).split("?")[0], page=ii.get("descriptionurl"),
                                    license=lic, artist=clean_artist(strip_html((em.get("Artist") or {}).get("value"))),
                                    title=pg["title"][5:])
    return out


COMMONS_MAX_INAT = 2  # iNaturalist 사진이 이 수 이하인 종만 커먼즈를 확인한다


def inat_count(m):
    """iNaturalist 사진 수(대표 사진과 관찰 사진, 같은 사진은 한 번만)"""
    pid = lambda p: p["url"].split("/photos/")[-1].split("/")[0]
    return len({pid(p) for p in (m.get("curated") or [])[:1] + (m.get("photos") or [])})


def fill_commons(limit, max_age=60):
    """iNaturalist 사진이 2장 이하인 종에 커먼즈 이미지를 채운다."""
    cutoff = (date.today() - timedelta(days=max_age)).isoformat()
    names = json.loads((DATA / "names.json").read_text(encoding="utf-8"))
    todo = []
    for t in names:
        if t["rank"] != "species":
            continue
        f = OUT / (t["sci"].replace(" ", "_") + ".json")
        m = json.loads(f.read_text(encoding="utf-8")) if f.exists() else None
        if not m or inat_count(m) > COMMONS_MAX_INAT or m.get("commons_checked", "") >= cutoff:
            continue
        todo.append((t["sci"], f, m))
    todo = todo[:limit]
    print("커먼즈 확인할 종:", len(todo), flush=True)
    p18 = wikidata_p18([s for s, _, _ in todo])
    got = 0
    for n, (sci, f, m) in enumerate(todo, 1):
        titles = list(p18.get(sci, []))
        d = wiki_get(COMMONS_API, dict(action="query", list="categorymembers", cmtitle="Category:" + sci, cmtype="file", cmlimit=20))
        titles += [x["title"] for x in (d.get("query") or {}).get("categorymembers", []) if x["title"] not in titles]
        titles = [x for x in titles if not COMMONS_SKIP.search(x)]
        info = commons_info(titles) if titles else {}
        m["commons"] = [info[x] for x in titles if x in info][:PER_SPECIES]
        m["commons_checked"] = date.today().isoformat()
        f.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
        got += bool(m["commons"])
        if m["commons"] or n % 100 == 0:
            print(f"{n:5} {sci:34} 커먼즈 {len(m['commons'])} (누적 {got})", flush=True)
    print("커먼즈 이미지가 있는 종:", got)


def targets(scope):
    """korean: 한국 출현종 · named: 국명이 있는 모든 종 · unnamed: 국명이 없는 종만 · all: 전부"""
    names = json.loads((DATA / "names.json").read_text(encoding="utf-8"))
    sp = [t for t in names if t["rank"] == "species"]
    korean = [t for t in sp if t["status"] in ("kos", "official")]
    named = [t for t in sp if t not in korean and t.get("name")]
    unnamed = [t for t in sp if not t.get("name")]
    return {"korean": korean, "named": korean + named, "unnamed": unnamed,
            "all": korean + named + unnamed}[scope]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=10_000)
    ap.add_argument("--max-age", type=int, default=60, help="이보다 오래된 자료만 다시 받는다(일)")
    ap.add_argument("--scope", choices=["korean", "named", "unnamed", "all"], default="korean")
    ap.add_argument("--all-named", action="store_true", help="--scope named 와 같다(예전 이름)")
    ap.add_argument("--covers", action="store_true", help="이미 받은 종의 대표 사진만 채운다")
    ap.add_argument("--common", action="store_true", help="이미 받은 종의 iNaturalist 영명만 채운다")
    ap.add_argument("--wiki-fix", action="store_true", help="위키 문서가 없거나 속 문서뿐인 종을 다시 찾는다")
    ap.add_argument("--commons", action="store_true", help="iNaturalist 사진이 2장 이하인 종에 위키미디어 커먼즈 이미지를 채운다")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if a.covers:
        return backfill_covers()
    if a.common:
        return backfill_common()
    if a.commons:
        return fill_commons(a.limit)
    if a.wiki_fix:
        return wiki_fix("named" if a.scope == "korean" else a.scope)
    load_old_names(json.loads((DATA / "names.json").read_text(encoding="utf-8")))
    cutoff = (date.today() - timedelta(days=a.max_age)).isoformat()
    retry_cutoff = (date.today() - timedelta(days=RETRY_DAYS)).isoformat()
    done = 0
    for t in targets("named" if a.all_named else a.scope):
        f = OUT / (t["sci"].replace(" ", "_") + ".json")
        old = json.loads(f.read_text(encoding="utf-8")) if f.exists() else None
        if old and old.get("fetched", "") >= (cutoff if old.get("inat") else retry_cutoff):
            # 예전 형식(요약만 있음)이면 위키백과 본문만 새로 받는다
            if old.get("inat") and (old.get("wiki") or {}).get("sections") is None and old["inat"].get("wikipedia_url"):
                if done >= a.limit:
                    break
                old["wiki"] = wiki_full(old["inat"]["wikipedia_url"])
                f.write_text(json.dumps(old, ensure_ascii=False, indent=1), encoding="utf-8")
                done += 1
                print(f"{done:4} {t['sci']:34} 위키 본문 {'O' if old['wiki'] else '-'}", flush=True)
            continue
        if done >= a.limit:
            break
        tx = inat_taxon(t["sci"])
        rec = dict(sci=t["sci"], fetched=date.today().isoformat(), inat=None, photos=[], wiki=None)
        if tx:
            rec["inat"] = dict(id=tx["id"], name=tx["name"], observations=tx.get("observations_count"),
                               wikipedia_url=tx.get("wikipedia_url"))
            rec["photos"] = inat_photos(tx["id"])
            rec["inat"]["common"] = tx.get("preferred_common_name")
            rec["curated"] = inat_curated_many([tx["id"]]).get(tx["id"], [])
            rec["wiki"] = wiki_for(t, tx.get("wikipedia_url"), old)
        if old and inat_count(rec) <= COMMONS_MAX_INAT:  # 커먼즈 이미지는 다시 받을 때도 남긴다
            for k in ("commons", "commons_checked"):
                if k in old:
                    rec[k] = old[k]
        f.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
        done += 1
        print(f"{done:4} {t['sci']:34} 사진 {len(rec['photos'])} 위키 {'O' if rec['wiki'] else '-'}", flush=True)
    print("새로 받은 종:", done)


if __name__ == "__main__":
    main()
