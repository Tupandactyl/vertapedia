"""분포 지도 판정 규칙(사이트 생성 build_site.py 와 자료 받기 fetch_establishment.py 가 같이 쓴다).

- 기록: 야생 출처(eBird·iNaturalist 연구등급·표본) 나라별 기록 w, 없으면 전체 c
- 서식국: 기록이 가장 많은 나라 + 10% 이상이거나 30건·0.5% 이상인 나라, 그리고 이들과 이웃·같은 소지역이며
  0.2%·3건 이상인 나라(늘어나면 다시 확인)
- 원래 서식권: 기준 나라(가장 많은 나라, 단 iNaturalist 가 도입으로 표시하면 토착 가운데 가장 많은 나라)에서
  이웃·같은 소지역으로 이어진 서식국
- 도입 정착지: 원래 서식권과 떨어진 서식국 가운데 iNaturalist 가 도입으로 표시한 나라
"""


def counts(d, gadm=None):
    """나라별 기록 → 지역별 기록. 행정구역 기록 g 가 있으면 나눈 나라(US·ID·RU 등)를 지역(US-HI 등)으로 쪼갠다:
    지역별로 행정구역 기록을 더하고, 나머지는 본토(나라 코드 그대로)에 남긴다."""
    c = {k: v for k, v in ((d or {}).get("w") or (d or {}).get("c") or {}).items() if k != "ZZ" and v > 0}
    if gadm and (d or {}).get("g"):
        reg = {}
        for gid, v in d["g"].items():
            r = gadm.get(gid)
            if r and "-" in r:
                reg[r] = reg.get(r, 0) + v
        for r, v in reg.items():
            base = r.split("-")[0]
            if base in c:
                c[r] = min(v, c[base])
                c[base] -= c[r]
        c = {k: v for k, v in c.items() if v > 0}
    return c


def flags(e, c):
    """iNaturalist 토착/도입 표시. 지역(US-HI 등)은 제 표시가 없으면 나라 표시를 따른다"""
    intro, native = set((e or {}).get("introduced", [])), set((e or {}).get("native", []))
    for k in c:
        if "-" in k and k not in intro and k not in native:
            base = k.split("-")[0]
            if base in intro:
                intro.add(k)
            elif base in native:
                native.add(k)
    return intro, native


def habitat(c, geo):
    if not c:
        return set()
    nb, sub = geo["neighbours"], geo["subregion"]
    tot = sum(c.values())
    share = lambda k: c[k] / tot
    major = {max(c, key=c.get)} | {k for k in c if share(k) >= 0.10 or (c[k] >= 30 and share(k) >= 0.005)}
    near = lambda k: any(linked(k, a, nb, sub) for a in major)
    grew = True
    while grew:
        grew = False
        for k in c:
            if k not in major and c[k] >= 3 and share(k) >= 0.002 and near(k):
                major.add(k)
                grew = True
    return major


def linked(a, b, nb, sub):
    return a in nb.get(b, []) or b in nb.get(a, []) or bool(sub.get(a) and sub.get(a) == sub.get(b))


def home_range(major, c, intro, native, geo):
    nb, sub = geo["neighbours"], geo["subregion"]
    seeds = sorted(major, key=lambda k: -c[k])
    seed = next((k for k in seeds if k not in intro or k in native), seeds[0])
    home, todo = {seed}, [seed]
    while todo:
        a = todo.pop()
        for k in major - home:
            if linked(k, a, nb, sub):
                home.add(k)
                todo.append(k)
    return home
