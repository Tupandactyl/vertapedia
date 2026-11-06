"""번역문 속 국명을 현재 국명으로 바꾼다.

번역문(data/wiki_ko/*.json)에는 번역 당시 쓴 국명 목록 names = {학명: [국명, ...]} 이 함께 들어 있다.
사이트를 만들 때 그 목록과 현재 국명(시트)을 견주어, 달라진 이름만 본문·주석에서 바꾼다.
그래서 시트의 국명만 고치면 번역을 다시 하지 않아도 모든 문서에 반영된다.

- 뒤따르는 조사는 새 이름의 받침에 맞춘다(재갈매기는 → 큰갈매기는, 유럽벌매를 → 벌매사촌을).
- 다른 낱말의 일부('쇠재갈매기'의 '재갈매기', '재갈매기속')는 건드리지 않는다.
- 국명이 없어지면 영명, 그것도 없으면 학명으로 적는다.
- data/name_aliases.json {학명: [번역문에 쓰인 다른 표기]}: 지침과 다르게 쓴 표기를 함께 바꾸게 한다.
"""
import re

# (받침 있을 때, 받침 없을 때). 긴 것부터 찾는다
PAIRS = [("이었다", "였다"), ("이라고", "라고"), ("이라는", "라는"), ("이라", "라"), ("이다", "다"), ("이며", "며"), ("이고", "고"), ("이나", "나"),
         ("으로", "로"), ("은", "는"), ("이", "가"), ("을", "를"), ("과", "와")]
ROWS = {x: p for p in PAIRS for x in p}
JOSA = sorted(set(ROWS) | {"의", "에", "도", "만", "에서", "에게", "보다", "처럼", "까지", "부터", "류", "들"}, key=len, reverse=True)
PLAIN_END = set("aeiouyrwAEIOUYRW")


def batchim(word):
    """마지막 글자 받침: None 없음, 8 ㄹ, 그 밖의 숫자 받침. 로마자는 끝 글자로 어림한다."""
    ch = re.sub(r"[*\s)]+$", "", word)[-1:]
    if "가" <= ch <= "힣":
        return (ord(ch) - 0xAC00) % 28 or None
    if ch in PLAIN_END:
        return None
    return 8 if ch in "lL" else 1


def fit(josa, new):
    """조사를 새 이름의 받침에 맞춘다."""
    pair = ROWS.get(josa)
    if not pair:
        return josa
    b = batchim(new)
    if josa in ("으로", "로"):
        return "로" if b in (None, 8) else "으로"
    return pair[1] if b is None else pair[0]


def pattern(olds):
    """옛 이름 + (병기 괄호) + 조사. 괄호 뒤 조사도 새 이름에 맞춘다."""
    words = "|".join(map(re.escape, sorted(olds, key=len, reverse=True)))
    return re.compile(rf"(?<![가-힣])({words})(\([^()]*\))?({'|'.join(JOSA)})?(?![가-힣])")


def plan(snapshot, current, aliases=None):
    """바꿀 짝 {옛 이름: 새 이름}과 건너뛴 (학명, 이름).
    current(학명) → (현재 국명 또는 None, 표시할 이름). 목록에서 사라진 학명이면 None.
    같은 문서의 다른 분류군이 지금 쓰는 이름으로 바뀐 옛 이름은 어느 쪽인지 가릴 수 없어 건너뛴다."""
    now = {sci: current(sci) for sci in set(snapshot) | set(aliases or {})}
    taken = {v[0]: sci for sci, v in now.items() if v and v[0] and sci in snapshot}
    wanted, skipped = {}, []
    for sci, cur in now.items():
        if not cur:
            continue
        for old in list(snapshot.get(sci, [])) + list((aliases or {}).get(sci, [])):
            if not old or old == cur[1]:
                continue
            if taken.get(old, sci) != sci:
                skipped.append((sci, old))
            else:
                wanted[old] = cur[1]
    return wanted, skipped


def apply(text, wanted):
    """text 의 옛 이름을 바꾼다. wanted 가 비어 있으면 그대로."""
    if not wanted:
        return text

    def sub(m):
        new = wanted[m.group(1)]
        return new + (m.group(2) or "") + (fit(m.group(3), new) if m.group(3) else "")
    out = pattern(wanted).sub(sub, text)
    # '영명(영명, *학명*)'처럼 겹친 병기를 줄인다
    for new in set(wanted.values()):
        if re.search("[가-힣]", new):
            continue
        out = re.sub(rf"(?i)({re.escape(new)})\(\1, ", r"\1(", out)
        out = re.sub(rf"(?i)({re.escape(new)})\(\1\)", r"\1", out)
    return out


if __name__ == "__main__":
    w = {"재갈매기": "큰갈매기", "유럽/양벌매": "European honey buzzard", "벌매": "매사촌"}
    for a, b in [("재갈매기는 크다", "큰갈매기는 크다"), ("쇠재갈매기는 크다", "쇠재갈매기는 크다"), ("재갈매기속이다", "재갈매기속이다"),
                 ("벌매를 보고 벌매로", "매사촌을 보고 매사촌으로"),
                 ("유럽/양벌매(European honey buzzard, *Pernis apivorus*)는", "European honey buzzard(*Pernis apivorus*)은"),
                 ("벌매과 재갈매기와", "매사촌과 큰갈매기와"), ("재갈매기류", "큰갈매기류"), ("벌매이다", "매사촌이다")]:
        assert apply(a, w) == b, (a, apply(a, w), b)
    assert apply("벌매는", {"벌매": "황새"}) == "황새는" and apply("황새가", {"황새": "벌매"}) == "벌매가"
    print("ok")
