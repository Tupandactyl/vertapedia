"""분포 나라·지역 코드 → 한국어 이름(data/region_ko.json). 나라는 CLDR(babel), 나눈 지역은 아래 표.

    python scripts/build_region_names.py
"""
import json
from pathlib import Path

from babel import Locale

DATA = Path(__file__).resolve().parent.parent / "data"
# 지도에서 따로 그리는 지역과, 지역을 떼어 낸 나머지 본토(scripts/build_world_map.py)
REGION = {"US": "미국 본토", "US-HI": "하와이", "US-AK": "알래스카", "ID": "인도네시아 서부", "ID-PAP": "인도네시아령 파푸아",
          "ID-WAL": "월리시아", "ES": "스페인 본토", "ES-CN": "카나리아제도", "PT": "포르투갈 본토", "PT-AC": "아조레스제도",
          "PT-MA": "마데이라제도", "EC": "에콰도르 본토", "EC-GAL": "갈라파고스제도", "JP": "일본 본토", "JP-OKI": "오키나와",
          "RU": "러시아(유럽)", "RU-AS": "러시아(아시아)", "CN": "중국 중남부", "CN-NE": "중국 동북부", "CN-W": "중국 서부",
          "AU": "호주 본토", "AU-TAS": "태즈메이니아", "IN": "인도 본토", "IN-AN": "안다만·니코바르제도"}
# CLDR 이름이 길거나 낯선 곳, 나라 코드가 없는 곳
FIX = {"HK": "홍콩", "MO": "마카오", "CD": "콩고민주공화국", "CG": "콩고공화국", "PS": "팔레스타인", "X-CYN": "북키프로스",
       "X-KAS": "시아첸 빙하", "X-SOL": "소말릴란드", "XZ": "공해"}


def main():
    dist = json.loads((DATA / "distribution.json").read_text(encoding="utf-8"))
    world = json.loads((DATA / "world.geojson").read_text(encoding="utf-8"))
    codes = {k for d in dist.values() if d for k in (d.get("w") or d.get("c") or {})} | {
        f["properties"]["c"] for f in world["features"]}
    ter = Locale("ko").territories
    names = {}
    for k in sorted(codes):
        if k == "ZZ":
            continue
        names[k] = REGION.get(k) or ter.get(k) or next(
            (f["properties"]["n"] for f in world["features"] if f["properties"]["c"] == k), k)
    names.update(REGION)
    names.update(FIX)
    (DATA / "region_ko.json").write_text(json.dumps(names, ensure_ascii=False, indent=0, sort_keys=True), encoding="utf-8")
    print(len(names), "개 ·", "한국어 이름 없음:", [k for k, v in names.items() if not any("가" <= ch <= "힣" for ch in v)])


if __name__ == "__main__":
    main()
