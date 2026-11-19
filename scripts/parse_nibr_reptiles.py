"""국립생물자원관(2018) 「국가지정 주요 관리대상 생물종의 국명·영명 부여」 보고서의 파충류 → data/nibr2018_reptiles.json

원본 PDF는 저장소에 올리지 않는다. 신규 국명(24~79번), CITES 국명 재검토(592~778번), 위해우려종(16~20번, 기존국명 칸이 밀려 있어 개칭명만).
결과: {학명: {"no", "old", "new", "sec"}}. 파충류 시트 지정관리종목록 P~R열에 넣었다(2026-11-19).

    python -I scripts/parse_nibr_reptiles.py <보고서.pdf> data/nibr2018_reptiles.json
"""
import pypdf, re, sys, json
pages = [(p.extract_text() or "").replace("\xa0", " ") for p in pypdf.PdfReader(sys.argv[1]).pages]
NAME = r"[가-힣()·\-]+(?: 전 ?종)?"
def chunks(lo, hi):
    txt = "\n".join(pages[lo:hi])
    parts = re.split(r"(?m)^(\d+) 파충류\s+", txt)
    for k in range(1, len(parts), 2):
        body = parts[k + 1]
        body = re.split(r"(?m)^\d+ (?:조류|양서류|포유류|어류|곤충|식물)", body)[0]
        # 칸 폭 때문에 이름 끝 한두 글자가 다음 줄로 넘어간 것 붙이기
        body = re.sub(r"([가-힣])\n([가-힣]{1,2})(?= )", r"\1\2", body)
        body = re.sub(r"\s+", " ", body).strip()
        yield int(parts[k]), body
out, extra = {}, []
SCI = r"([A-Z][A-Za-z]+(?: [a-z]+(?: [a-z]+)?| spp\.)?)"
for no, b in chunks(45, 60):
    m = re.match(rf"{SCI} ({NAME})", b)
    if m: out.setdefault(m[1], dict(no=no, old=None, new=m[2], sec="new"))
    else: print("신규 못 읽음", no, b[:80])
for no, b in chunks(600, len(pages)):
    m = re.match(rf"{SCI}(?: \(=[^)]*\))? ({NAME}) ({NAME})", b)
    if m and no >= 592: out[m[1]] = dict(no=no, old=m[2], new=m[3], sec="review")
    elif m: extra.append((m[1], dict(no=no, old=m[2], new=m[3], sec="harm")))
    else: print("재검토 못 읽음", no, b[:80])
for k, v in extra:
    if k not in out: out[k] = v; print("위해우려종 표에만:", k, v)
rv = sorted(v["no"] for v in out.values() if v["sec"] == "review")
print(len(out), "재검토", len(rv), rv[0], rv[-1], "빠진 번호", sorted(set(range(rv[0], rv[-1] + 1)) - set(rv)))
json.dump(out, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
# 이름에 띄어쓰기가 있거나(학명 음역) 칸 안에서 줄이 바뀐 것, 설명문이 이름에 붙은 것: 원문을 보고 바로잡음
FIX = {596: ("마우레미스 아나멘시스", "안남나뭇잎거북"), 606: ("펄비포자라", "중국꼬마자라"), 614: ("인도 올리브뱀", "인도올리브뱀"),
       615: ("바타거 아피니스", "말레이남강거북"), 652: ("크테노사우라 바케리", "우틸라가시꼬리이구아나"),
       653: ("크테노사우라 멜라노스테르나", "검은가슴가시꼬리이구아나"), 654: ("크테노사우라 오이디르히나", "로아탄가시꼬리이구아나"),
       667: ("에라키스토돈 웨스터만니", "인도알섭식뱀"), 684: ("노랑머리늪거북", "노랑머리사원거북"),
       698: ("말라예미스 마크로케팔라", "말레이달팽이섭식거북"), 737: ("피리노소마 위긴시", "세드로스뿔도마뱀"),
       747: ("말라가시거미거북", "마다가스카르거미육지거북"), 748: ("마다카스카르편미거북", "마다가스카르납작꼬리육지거북"),
       757: ("바리우스도마뱀", "척왈라도마뱀"), 724: ("필리핀줄목거북", "필리핀줄무늬목거북"), 760: ("시에벤록키엘라 레이텐시스", "레이테섬늪거북")}
for k, v in out.items():
    if v["sec"] == "review" and v["no"] in FIX:
        v["old"], v["new"] = FIX[v["no"]]
for v in out.values():
    for f in ("old", "new"):
        if v[f]: v[f] = v[f].replace("전 종", "전종")
for k, v in out.items():
    if v["sec"] == "harm":
        v["old"] = None  # 위해우려종 표의 기존국명 칸은 원문에서 한 줄씩 밀려 있어 쓰지 않는다
json.dump(out, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
