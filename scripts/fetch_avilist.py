"""AviList 확장판(v2026)에서 조류 종·속의 명명자와 연도를 뽑아 data/bird_authority.json 에 둔다 → {학명: "Gould, 1845"}
eBird 종 코드(SPECIES CODE CORNELL LAB)도 data/bird_codes.json 에 둔다(eBird·Macaulay 링크용).

- Authority 「Reichenow, A, 1883」 → 「Reichenow, 1883」 (이름 머리글자는 뺀다)
- 원래 속에서 옮겨진 종의 괄호 「(Linnaeus, 1758)」는 AviList 표기를 그대로 둔다(국제동물명명규약 관례)
- 우리 목록(eBird 학명)과 학명이 다르면 같은 속의 종소명(어간)으로 잇는다.
AviList 원본(data/avilist2026.xlsx)은 저장소에 올리지 않는다(없으면 scripts/fetch_types.py 가 받는다).

    python scripts/fetch_avilist.py
"""
import json
import re
from pathlib import Path

import openpyxl

from fetch_types import AVILIST, AVILIST_FILE, avilist_index, stem  # noqa: F401  (원본 주소는 fetch_types 와 같이 쓴다)

DATA = Path(__file__).resolve().parent.parent / "data"


def clean_author(a):
    """AviList 「(Linnaeus, C, 1758)」·「Cabanis, JL; Heine, F, 1860」 → 「(Linnaeus, 1758)」·「Cabanis & Heine, 1860」
    괄호(원래 속에서 옮겨진 종)는 AviList 표기를 그대로 둔다."""
    a = str(a or "").strip()
    paren = a.startswith("(") and a.endswith(")")
    a = a.strip("() ")
    m = re.search(r"(\d{4})\s*$", a)
    year = m.group(1) if m else None
    body = a[: m.start()].strip(" ,;") if m else a
    names = []
    for p in re.split(r"\s*(?:;|&| and )\s*", body):
        p = re.sub(r",\s*[A-Z][A-Za-z.\-]{0,5}$", "", p.strip())  # 「Linnaeus, C」 → 「Linnaeus」
        if p:
            names.append(p)
    who = " & ".join(names) if len(names) <= 2 else ", ".join(names[:-1]) + " & " + names[-1]
    out = f"{who}, {year}" if year else who
    return f"({out})" if paren else out


def main():
    names = json.loads((DATA / "names.json").read_text(encoding="utf-8"))
    ours = {t["sci"] for t in names if t["group"] == "AVES" and t["rank"] in ("species", "genus")}
    by_genus = {}
    for s in ours:
        if " " in s:
            by_genus.setdefault(s.split()[0], []).append(s)
    rows = list(openpyxl.load_workbook(DATA / AVILIST_FILE, read_only=True).worksheets[0].iter_rows(values_only=True))
    h = list(rows[0])
    ix = avilist_index(h, ("Taxon_rank", "Scientific_name", "Authority", "Protonym"))
    try:
        i_code = avilist_index(h, ("SPECIES CODE CORNELL LAB",))["SPECIES CODE CORNELL LAB"]
    except ValueError:
        i_code = None
    codes = {r[ix["Scientific_name"]]: r[i_code] for r in rows[1:] if i_code is not None and r[i_code]
             and r[ix["Taxon_rank"]] == "species"}
    (DATA / "bird_codes.json").write_text(json.dumps(codes, ensure_ascii=False, indent=0, sort_keys=True), encoding="utf-8")
    out = {}
    for r in rows[1:]:
        rank, sci, auth = r[ix["Taxon_rank"]], r[ix["Scientific_name"]], r[ix["Authority"]]
        if rank not in ("species", "genus") or not sci or not auth:
            continue
        a = clean_author(auth)
        if rank == "species":
            target = sci if sci in ours else None
            if not target:
                same = [s for s in by_genus.get(sci.split()[0], []) if stem(s.split()[1]) == stem(sci.split()[1])]
                target = same[0] if len(same) == 1 else None
        else:
            target = sci if sci in ours else None
        if target:
            out.setdefault(target, a)
    (DATA / "bird_authority.json").write_text(json.dumps(out, ensure_ascii=False, indent=0, sort_keys=True), encoding="utf-8")
    sp = [s for s in ours if " " in s]
    print("명명자 붙은 종", sum(1 for s in sp if s in out), "/", len(sp), "· 속", sum(1 for s in ours if " " not in s and s in out))


if __name__ == "__main__":
    main()
