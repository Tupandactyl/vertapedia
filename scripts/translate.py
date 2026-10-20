"""영문 위키백과 본문을 한국어로 옮긴다(시험·본 번역 공용).

- 생물 이름은 번역 전에 자리표시 [[N0]] … 로 바꿔 두었다가, 번역 뒤 버타피디아 국명으로 되돌린다
  (scripts/ko_link.py 의 이름 바꾸기를 그대로 쓴다). 그래야 국명이 문서마다 흔들리지 않는다.
- 문단 단위로 옮기고, 자리표시·숫자가 빠지지 않았는지 검사해 표시한다.
- 결과: data/translations/<학명>.<엔진>.json  (절마다 원문 해시를 둬서 나중에 바뀐 절만 다시 옮길 수 있게)

엔진
  ollama:<모델>   이 PC의 Ollama (예: ollama:exaone3.5:7.8b)
  manual          사람이 붙여 넣은 번역(data/translations/<학명>.manual.json 의 paras 를 검사만)

    python scripts/translate.py ollama:exaone3.5:7.8b Pica_serica Ciconia_boyciana
"""
import hashlib
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ko_link import Linker  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = DATA / "translations"

HEADINGS = {
    "taxonomy": "분류", "taxonomy and systematics": "분류와 계통", "systematics": "계통", "etymology": "어원",
    "subspecies": "아종", "description": "형태", "identification": "식별", "voice": "울음소리",
    "vocalisations": "울음소리", "vocalizations": "울음소리", "distribution": "분포",
    "distribution and habitat": "분포와 서식지", "habitat": "서식지", "behaviour": "행동", "behavior": "행동",
    "behaviour and ecology": "행동과 생태", "behavior and ecology": "행동과 생태", "ecology": "생태",
    "breeding": "번식", "feeding": "먹이", "food and feeding": "먹이", "diet": "먹이", "migration": "이동",
    "status": "현황", "conservation": "보전", "conservation status": "보전 현황", "threats": "위협 요인",
    "in culture": "문화 속에서", "relationship with humans": "사람과의 관계", "in human culture": "문화 속에서",
    "predators": "포식자", "predators and parasites": "포식자와 기생충", "parasites": "기생충",
    "evolution": "진화", "fossil record": "화석 기록", "gallery": "사진",
}

PROMPT = """다음 영어 문단을 자연스러운 한국어 문어체(-다)로 옮겨라. 생물학 백과사전 문체로 쓴다.
규칙:
- [[N0]], [[N1]] 같은 자리표시는 생물 이름이다. 글자 하나 바꾸지 말고 그대로 두고, 한국어 어순에 맞게 자리만 옮겨라. 뒤에 조사를 붙여도 된다.
- 숫자, 단위, 연도, 학명(라틴어)은 그대로 둔다. 단위는 cm, kg처럼 쓴다.
- 원문에 없는 내용을 더하거나 빼지 마라. 설명이나 머리말 없이 번역문만 내놓아라.

영어:
{text}

한국어:"""


def protect(segs):
    """ko_link 문단(문자열 또는 조각 목록) → (자리표시 문장, {자리표시: 되돌릴 한국어})"""
    if isinstance(segs, str):
        return segs, {}
    text, back = [], {}
    for x in segs:
        if isinstance(x, str):
            text.append(x)
            continue
        ko, orig, rk, sci, first = x
        key = f"[[N{len(back)}]]"
        if rk == "S":
            back[key] = f"*{orig}*"  # 학명은 그대로(기울임)
        else:
            back[key] = f"{ko}({orig})" if first else ko
        text.append(key)
    return "".join(text), back


# 국명 뒤 조사를 받침에 맞춘다(까치은 → 까치는). 순서: 긴 것 먼저
JOSA = [("으로", "로"), ("이다", "다"), ("이나", "나"), ("이라", "라"), ("은", "는"), ("이", "가"), ("을", "를"), ("과", "와")]


def _batchim(word):
    """한글 마지막 글자의 받침: None(받침 없음), 'ㄹ', 'other'. 한글이 아니면 None 을 돌려 고치지 않는다."""
    m = re.search(r"([가-힣])[^가-힣]*$", re.sub(r"\(.*?\)$", "", word))
    if not m:
        return "?"
    jong = (ord(m.group(1)) - 0xAC00) % 28
    return None if jong == 0 else ("ㄹ" if jong == 8 else "other")


def restore(ko_text, back):
    for k, v in back.items():
        b = _batchim(v) if not v.startswith("*") else "?"
        def fix(m, v=v, b=b):
            j = m.group(1) or ""
            for with_b, without_b in JOSA:
                if j in (with_b, without_b) and b != "?":
                    if with_b == "으로":
                        j = "로" if b in (None, "ㄹ") else "으로"
                    else:
                        j = without_b if b is None else with_b
                    break
            return v + j
        ko_text = re.sub(re.escape(k) + r"(으로|이다|이나|이라|은|는|이|가|을|를|과|와|로|다|나|라)?", fix, ko_text)
    return ko_text


def check(src, out, back):
    """빠진 자리표시·숫자, 길이 비율 이상을 찾는다"""
    issues = [f"이름 빠짐 {k}" for k in back if k not in out]
    extra = [x for x in re.findall(r"\[\[[^\]]*\]\]", out) if x not in back]
    if extra:
        issues.append("없는 괄호 " + ", ".join(extra[:3]))
    if re.search(r"(습니다|입니다|합니다)[.!]?\s*$", out) or re.search(r"(습니다|입니다)\.", out):
        issues.append("문체(-습니다)")
    nums = lambda t: sorted(re.findall(r"\d+(?:[.,]\d+)?", t))
    miss = [n for n in set(nums(src)) if n not in out]
    if miss:
        issues.append("숫자 빠짐 " + ", ".join(miss[:5]))
    ratio = len(out) / max(1, len(src))
    if ratio < 0.25 or ratio > 0.9:
        issues.append(f"길이 비율 {ratio:.2f}")
    return issues


def ollama(model, text):
    body = json.dumps(dict(model=model, prompt=PROMPT.format(text=text), stream=False,
                           options=dict(temperature=0.2, num_ctx=4096, num_predict=2048))).encode()
    req = urllib.request.Request("http://127.0.0.1:11434/api/generate", data=body,
                                 headers={"Content-Type": "application/json"})
    r = json.load(urllib.request.urlopen(req, timeout=1800))
    return r["response"].strip(), r.get("eval_count", 0), r.get("eval_duration", 0) / 1e9


def source(sci, linker):
    m = json.loads((DATA / "media" / f"{sci}.json").read_text(encoding="utf-8"))
    w = linker.wiki(m["wiki"])
    return m, w


def translate(engine, sci, linker):
    m, w = source(sci, linker)
    OUT.mkdir(parents=True, exist_ok=True)
    name = engine.split(":", 1)[1] if engine.startswith("ollama:") else engine
    f = OUT / f"{sci}.{name.replace(':', '_')}.json"
    secs, tokens, secs_time = [], 0, 0.0
    for s in w["sections"]:
        h = s["h"]
        hk = HEADINGS.get((h or "").strip().lower()) if h else None
        if h and not hk and engine.startswith("ollama:"):
            hk = ollama(engine.split(":", 1)[1], h)[0].splitlines()[0].strip(" .#")
        paras = []
        for p in s["paras"]:
            src, back = protect(p)
            t0 = time.time()
            ko, n, dur = ollama(engine.split(":", 1)[1], src)
            tokens += n
            secs_time += time.time() - t0
            paras.append(dict(en=src, ko=restore(ko, back), raw=ko, issues=check(src, ko, back)))
            print(f"  {sci} 문단 {len(paras)} · {n}토큰 {dur:.0f}초", flush=True)
        secs.append(dict(h=h, h_ko=hk or h, level=s["level"], paras=paras,
                         hash=hashlib.sha1("\n".join(protect(p)[0] for p in s["paras"]).encode()).hexdigest()[:12]))
    rec = dict(sci=m["sci"], title=w["title"], revision=w.get("revision"), engine=engine,
               translated=time.strftime("%Y-%m-%d"), tokens=tokens, seconds=round(secs_time), sections=secs)
    f.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{sci}: {tokens}토큰, {secs_time / 60:.1f}분 → {f.name}", flush=True)


def main():
    engine, sp = sys.argv[1], sys.argv[2:]
    linker = Linker(json.loads((DATA / "names.json").read_text(encoding="utf-8")))
    for s in sp:
        translate(engine, s, linker)


if __name__ == "__main__":
    main()
