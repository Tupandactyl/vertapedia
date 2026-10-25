"""분포 지도 판정 규칙(사이트 생성 build_site.py 와 자료 받기 fetch_establishment.py 가 같이 쓴다).

- 기록: 야생 출처(eBird·iNaturalist 연구등급·표본) 나라별 기록 w, 없으면 전체 c
- 서식국: 기록이 가장 많은 나라 + 10% 이상이거나 30건·0.5% 이상인 나라, 그리고 이들과 이웃·같은 소지역이며
  0.2%·3건 이상인 나라(늘어나면 다시 확인)
- 원래 서식권: 기준 나라(가장 많은 나라, 단 iNaturalist 가 도입으로 표시하면 토착 가운데 가장 많은 나라)에서
  이웃·같은 소지역으로 이어진 서식국
- 도입 정착지: 원래 서식권과 떨어진 서식국 가운데 iNaturalist 가 도입으로 표시한 나라
"""


def counts(d):
    return {k: v for k, v in ((d or {}).get("w") or (d or {}).get("c") or {}).items() if k != "ZZ" and v > 0}


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
