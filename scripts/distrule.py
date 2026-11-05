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
        # 나눈 나라마다 행정구역별 기록을 지역으로 모으고, 행정구역이 없는 기록(해안 등)은 그 비율대로 나눈다
        per = {}
        for gid, v in d["g"].items():
            r = gadm.get(gid)
            if r:
                base = r.split("-")[0]
                per.setdefault(base, {})
                per[base][r] = per[base].get(r, 0) + v
        for base, reg in per.items():
            tot = sum(reg.values())
            if base not in c or not tot or all(r == base for r in reg):
                continue
            n = c.pop(base)
            for r, v in reg.items():
                c[r] = c.get(r, 0) + round(n * v / tot)
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


def bird_habitat(c, geo, places, intro=()):
    """조류: 기록으로 잡은 서식국을 AviList 분포 설명과 대조한다. 칠하려면 언제나 기록이 있어야 한다.
    - 설명에 이름이 나온 곳(n)은 3건 이상이면 서식국, 도입지로 나온 곳(i)은 10건·0.1% 이상이면 서식국
    - 이름은 없어도 그 사이에 있는 곳(h, 경유지 포함)은 3건·0.1% 이상이면 서식국. 일부만 걸치는 곳(t)은 이미 서식국이면 남긴다
    - 설명에도 그 사이에도 없는 곳은 드문 기록으로 내린다. 단 전 세계 분포·바닷새처럼 나라로 다 못 적는 설명(s),
      iNaturalist 도입 표시가 있고 500건 이상인 곳(설명에 도입지를 다 적지는 않는다. 그보다 적으면 사육 개체일 수 있다),
      기록의 25% 이상을 차지하는 곳은
      남긴다. 25% 규칙은 설명의 지명이 기록의 60% 이상을 이미 설명하면 쓰지 않는다(분류가 달라 다른 종 기록이 섞인 경우)"""
    major = habitat(c, geo)
    named = set(places.get("n", []))
    tot = sum(c.values()) or 1
    said_intro = {k for k in places.get("i", []) if c.get(k, 0) >= 10 and c[k] / tot >= 0.001}
    out = {k for k in named if c.get(k, 0) >= 3} | said_intro
    if not named or places.get("s"):
        return major | out
    between = set(places.get("h", []))
    out |= {k for k in between if c.get(k, 0) >= 3 and c[k] / tot >= 0.001}
    said = named | between | set(places.get("t", [])) | set(places.get("i", []))
    fits = sum(v for k, v in c.items() if k in said) / tot >= 0.6
    out |= {k for k in major if k in said or (k in intro and c[k] >= 500)
            or (not fits and c[k] / tot >= 0.25)}
    return out or major


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
