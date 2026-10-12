"""영문 위키백과 본문 속 생물 이름을 버타피디아 국명으로 바꾼다(번역 비용 없이).

- 종: 영명(대소문자 무시, grey/gray 같게, 복수형 -s/-es 포함). 이명법 학명은 바꾸지 않고 종 문서 링크만 건다(계급 S)
- 과·목: 학명, 속: 학명(뒤에 종소명이 붙어 있으면 건너뜀 — 국명 없는 종일 수 있다)
- 국명이 있는 분류군만 바꾼다. 문단은 문자열 또는 [문자열 | [국명, 원래 이름, 계급, 학명, 처음?]] 목록이 된다.
"""
import re

WORD = re.compile(r"[A-Za-z][A-Za-z'\-]*")
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
            if not ko:
                continue
            rk = t["rank"]
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
            if not (nxt and text[toks[i].end():nxt.start()] == " " and nxt.group().islower()):
                return i + 1, g
        return None

    def paragraph(self, text, seen):
        toks = list(WORD.finditer(text))
        out, pos, i = [], 0, 0
        while i < len(toks):
            m = self._match(text, toks, i)
            if not m:
                i += 1
                continue
            j, (ko, rk, sci) = m
            a, b = toks[i].start(), toks[j - 1].end()
            if a > pos:
                out.append(text[pos:a])
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
