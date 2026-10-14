"""영문 위키백과 본문 속 생물 이름을 버타피디아 국명으로 바꾼다(번역 비용 없이).

- 종: 영명(대소문자 무시, grey/gray 같게, 복수형 -s/-es 포함). 이명법 학명은 바꾸지 않고 종 문서 링크만 건다(계급 S)
- 과·목: 학명, 속: 학명(뒤에 종소명이 붙어 있으면 건너뜀 — 국명 없는 종일 수 있다)
- 국명이 있는 분류군만 바꾼다. 문단은 문자열 또는 [문자열 | [국명, 원래 이름, 계급, 학명, 처음?]] 목록이 된다.
"""
import re

WORD = re.compile(r"[A-Za-z][A-Za-z'\-]*")
# 속 이름 뒤에 와도 종소명이 아닌 흔한 영어 낱말
ENGLISH = set("and or but the a an is are was were be been has have had in of on at to from by with as for "
              "which that who whose its it this these those than then also not only into include includes "
              "including contains contain comprises species genus genera family".split())
# 영명 앞에 붙으면 다른 종 이름이 되는 수식어(크기·방위·색·서식지 등)
NAME_MODS = set("""northern southern eastern western central greater lesser little great giant common dwarf pygmy
black white red grey gray brown yellow green blue golden spotted striped barred mountain forest desert island arctic
hoary mealy rufous olive dusky pale dark large small""".split())
THE = re.compile(r"(?:(?<=\W)|^)(?:[Tt]he|[Aa]n?) $")
# 흔한 영어 낱말·사람 이름과 겹치는 한 단어 영명은 바꾸지 않는다
AMBIGUOUS = {"merlin", "rook", "redhead", "whitehead", "hardhead", "ruff", "ou", "rifleman", "yellowhead",
             "redwing", "sora", "standardwing", "watercock", "morningbird"}


def _norm(w):
    w = w.lower().replace("’", "'")
    return "gray" if w == "grey" else w


class Linker:
    def __init__(self, names):
        self.en, self.sci, self.genus = {}, {}, {}
        for t in names:
            ko = t.get("name")
            rk = t["rank"]
            if not ko:
                # 국명 없는 종의 영명·학명도 넣어 둔다: 더 긴 이름이 그 종이면 통째로 영어로 두고, 그 안의 짧은 이름을 잘못 잡지 않게
                if rk == "species":
                    self.sci.setdefault(tuple(t["sci"].split()), (None, "S", t["sci"]))
                    en = (t.get("en") or "").strip()
                    if en and " " in en:
                        self.en.setdefault(tuple(_norm(w) for w in WORD.findall(en)), (None, "s", t["sci"]))
                continue
            if rk == "species":
                self.sci.setdefault(tuple(t["sci"].split()), (ko, "S", t["sci"]))  # 학명은 그대로 두고 링크만
                en = (t.get("en") or "").strip()
                if en and (" " in en or "-" in en or en.lower() not in AMBIGUOUS):
                    self.en.setdefault(tuple(_norm(w) for w in WORD.findall(en)), (ko, "s", t["sci"]))
            elif rk in ("family", "order", "suborder"):
                self.sci.setdefault((t["sci"],), (ko, rk[0] if rk != "suborder" else "o", t["sci"]))
            elif rk == "genus":
                self.genus.setdefault(t["sci"], (ko, "g", t["sci"]))
        self.maxlen = max([len(k) for k in self.en] + [len(k) for k in self.sci] + [1])

    def _match(self, text, toks, i):
        """toks[i] 에서 시작하는 가장 긴 이름 → (끝 토큰 번호, 값)"""
        for n in range(min(self.maxlen, len(toks) - i), 0, -1):
            seg = toks[i:i + n]
            if any(text[a.end():b.start()] != " " for a, b in zip(seg, seg[1:])):
                continue
            words = tuple(m.group() for m in seg)
            if words in self.sci:
                return i + n, self.sci[words]
            key = tuple(_norm(w) for w in words)
            hit = self.en.get(key)
            if not hit and key[-1].endswith("s"):  # 복수형
                for cut in ("es", "s"):
                    if key[-1].endswith(cut):
                        hit = hit or self.en.get(key[:-1] + (key[-1][:-len(cut)],))
            if hit:
                return i + n, hit
        g = self.genus.get(toks[i].group())
        if g:
            nxt = toks[i + 1] if i + 1 < len(toks) else None
            epithet = nxt and text[toks[i].end():nxt.start()] == " " and nxt.group().islower() \
                and nxt.group() not in ENGLISH
            if not epithet:
                return i + 1, g
        return None

    @staticmethod
    def _modified(text, toks, i):
        """영명 바로 앞에 이름을 이루는 수식어가 붙어 있나(예: Madagascar Black Bulbul, lesser redpoll).
        그러면 대조표에 없는 더 긴 이름일 수 있으니 바꾸지 않는다."""
        if i == 0 or text[toks[i - 1].end():toks[i].start()] != " ":
            return False
        prev = toks[i - 1].group()
        if _norm(prev) in NAME_MODS:
            return True
        if prev[0].isupper() and prev not in ("The", "A", "An"):
            before = text[:toks[i - 1].start()].rstrip()
            return bool(before) and before[-1] not in ".!?:;(\"'“‘"  # 문장 첫 단어는 제외
        return False

    def paragraph(self, text, seen):
        toks = list(WORD.finditer(text))
        out, pos, i = [], 0, 0
        while i < len(toks):
            m = self._match(text, toks, i)
            if not m:
                i += 1
                continue
            j, (ko, rk, sci) = m
            if ko is None or (rk == "s" and self._modified(text, toks, i)):
                i = j  # 국명 없는 종이거나 더 긴 다른 이름의 일부 → 영어 그대로
                continue
            a, b = toks[i].start(), toks[j - 1].end()
            before = text[pos:a]
            if rk != "S":  # 국명 앞 관사(the·a·an)는 뺀다 — 남겨 두면 번역기가 "the ○○"를 "그만큼" 따위로 옮긴다
                before = THE.sub("", before)
            if before:
                out.append(before)
            out.append([ko, text[a:b], rk, sci, 0 if rk == "S" or sci in seen else 1])
            if rk != "S":
                seen.add(sci)
            pos, i = b, j
        if not out:
            return text
        if pos < len(text):
            out.append(text[pos:])
        return out

    def wiki(self, w):
        if not w or not w.get("sections"):
            return w
        seen = set()
        secs = [dict(s, paras=[self.paragraph(p, seen) for p in s["paras"]]) for s in w["sections"]]
        return dict(w, sections=secs, ko_linked=True)
