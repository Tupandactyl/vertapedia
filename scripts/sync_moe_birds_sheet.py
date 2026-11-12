"""조류 시트에 환경부 지정명 반영 (data/moe_birds.json → 구글 시트)

1. 종 탭(… v2026)마다 'ENGLISH NAME: AVILIST' 오른쪽에 '환경부 지정명', '국내 통용/유통명' 열을 끼워 넣고,
   법정 목록에 종 단위로 지정된 종의 행에 환경부 지정명을 채운다. 국내 통용/유통명은 편집진이 채운다.
2. '지정관리종목록' 탭을 만든다(파충류 시트의 같은 탭 구성을 따른다). 법정 목록에 실린 조류 종만 모은다.

환경부 지정명 고르기
- 국립생물자원관(2018) 보고서의 개칭명이 있으면 그것을 앞에 둔다.
- 법령마다 이름이 다르면, 개칭 전 이름(보고서의 기존 국명)이 아닌 다른 이름을 뒤에 함께 적는다.
- 보고서에 없는 종은 법령 이름들을 그대로(서로 다르면 모두) 적는다.

    python scripts/sync_moe_birds_sheet.py           # 미리보기(data/moe_birds_preview.csv)
    python scripts/sync_moe_birds_sheet.py --apply   # 시트에 쓴다(먼저 .secrets/backup 에 xlsx 백업)
"""
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
sys.path.insert(0, str(ROOT / "scripts"))

# 법령에 남은 옛 학명 → AviList v2026 학명 (GBIF 대조 + 같은 종소명·영명으로 확인)
SYN = {
    "Accipiter gentilis": "Astur gentilis", "Anas americana": "Mareca americana", "Anas clypeata": "Spatula clypeata",
    "Anas falcata": "Mareca falcata", "Anas formosa": "Sibirionetta formosa", "Anas penelope": "Mareca penelope",
    "Anas querquedula": "Spatula querquedula", "Anas strepera": "Mareca strepera", "Baillonius bailloni": "Pteroglossus bailloni",
    "Bubulcus ibis": "Ardea ibis", "Burhinus bistriatus": "Hesperoburhinus bistriatus", "Carduelis cannabina": "Linaria cannabina",
    "Carduelis cucullata": "Spinus cucullatus", "Carduelis flammea": "Acanthis flammea", "Carduelis spinus": "Spinus spinus",
    "Carduelis yarrellii": "Spinus yarrellii", "Carpodacus mexicanus": "Haemorhous mexicanus",
    "Charadrius alexandrinus": "Anarhynchus alexandrinus", "Charadrius dubius": "Thinornis dubius",
    "Charadrius leschenaultii": "Anarhynchus leschenaultii", "Charadrius mongolus": "Anarhynchus mongolus",
    "Charadrius veredus": "Anarhynchus veredus", "Cuculus hyperythrus": "Hierococcyx hyperythrus",
    "Cygnus melanocorypha": "Cygnus melancoryphus", "Dendrocopos canicapillus": "Yungipicus canicapillus",
    "Dendrocopos kizuki": "Yungipicus kizuki", "Dendrocopos minor": "Dryobates minor", "Dupetor flavicollis": "Botaurus flavicollis",
    "Egretta intermedia": "Ardea intermedia", "Eos histrio": "Trichoglossus histrio",
    "Garrulax perspicillatus": "Pterorhinus perspicillatus", "Garrulax sannio": "Pterorhinus sannio",
    "Grus leucogeranus": "Leucogeranus leucogeranus", "Grus vipio": "Antigone vipio", "Guarouba guarouba": "Guaruba guarouba",
    "Heteroglaux blewitti": "Athene blewitti", "Heteroscelus brevipes": "Tringa brevipes",
    "Hypopicus hyperythrus": "Dendrocopos hyperythrus", "Hypotaenidia sylvestris": "Gallirallus sylvestris",
    "Ixobrychus cinnamomeus": "Botaurus cinnamomeus", "Ixobrychus sinensis": "Botaurus sinensis",
    "Larus genei": "Chroicocephalus genei", "Larus relictus": "Ichthyaetus relictus", "Larus ridibundus": "Chroicocephalus ridibundus",
    "Limicola falcinellus": "Calidris falcinellus", "Lonchura oryzivora": "Padda oryzivora", "Mimizuku gurneyi": "Otus gurneyi",
    "Oceanodroma monorhis": "Hydrobates monorhis", "Parus ater": "Periparus ater", "Phalacrocorax pelagicus": "Urile pelagicus",
    "Phalacrocorax urile": "Urile urile", "Philomachus pugnax": "Calidris pugnax", "Pitta guajana": "Hydrornis guajanus",
    "Pitta gurneyi": "Hydrornis gurneyi", "Pitta kochi": "Erythropitta kochi", "Porzana fusca": "Zapornia fusca",
    "Porzana paykullii": "Zapornia paykullii", "Porzana pusilla": "Zapornia pusilla",
    "Psephotus chrysopterygius": "Psephotellus chrysopterygius", "Psephotus dissimilis": "Psephotellus dissimilis",
    "Psephotus pulcherrimus": "Psephotellus pulcherrimus", "Psittacula echo": "Psittacula eques",
    "Pterocnemia pennata": "Rhea pennata", "Puffinus carneipes": "Ardenna carneipes", "Puffinus tenuirostris": "Ardenna tenuirostris",
    "Sporophila maximilliani": "Sporophila maximiliani", "Sterna albifrons": "Sternula albifrons", "Sterna bergii": "Thalasseus bergii",
    "Sterna caspia": "Hydroprogne caspia", "Sterna fuscata": "Onychoprion fuscatus", "Sterna nilotica": "Gelochelidon nilotica",
    "Streptopelia chinensis": "Spilopelia chinensis", "Sylvia curruca": "Curruca curruca", "Sylvia nisoria": "Curruca nisoria",
    "Troglodytes troglodytes": "Nannus troglodytes", "Tryngites subruficollis": "Calidris subruficollis",
}
# AviList 에서 다른 종에 합쳐져 아종이 된 것: 종 단위가 아니므로 넣지 않는다
LUMPED = {"Anas carolinensis", "Larus heuglini", "Falco pelegrinoides", "Apus nipalensis", "Carduelis hornemanni",
          "Pezoporus flaviventris"}
ORDER = ("cites", "white", "inflow", "export", "facility")
LIST_COLS = [("cites", "국제적 멸종위기종 (CITES) 부속서"), ("white", "지정관리야생동물"), ("inflow", "유입주의생물"),
             ("facility", "사육시설등록대상"), ("export", "수출입허가대상야생생물")]
TAB = "지정관리종목록"


def moe_name(r):
    law = []
    for k in ORDER:
        n = r["names"].get(k)
        if n and n not in law:
            law.append(n)
    nb = r.get("nibr")
    if nb:
        first = nb["new"]
        rest = [n for n in law if n not in (first, nb.get("old"))]
        return ", ".join([first] + rest)
    return ", ".join(law) or None


def merged():
    """AviList 학명별로 합친 기록"""
    avi = {t["sci"]: t for t in json.loads((DATA / "names.json").read_text(encoding="utf-8"))
           if t["group"] == "AVES" and t["rank"] == "species"}
    out, skipped = {}, []
    for r in json.loads((DATA / "moe_birds.json").read_text(encoding="utf-8")):
        s = SYN.get(r["sci"], r["sci"])
        if r["sci"] in LUMPED or s not in avi:
            skipped.append(r["sci"])
            continue
        m = out.setdefault(s, dict(sci=s, law_sci=[], lists={}, names={}, nibr=None))
        if r["sci"] != s:
            m["law_sci"].append(r["sci"])
        m["lists"].update(r["lists"])
        for k, v in r["names"].items():
            m["names"].setdefault(k, v)
        m["nibr"] = m["nibr"] or r.get("nibr")
    for m in out.values():
        m["moe"] = moe_name(m)
        m["family"] = avi[m["sci"]].get("family")
        m["order"] = avi[m["sci"]].get("order")
    return out, skipped


def main(apply):
    rec, skipped = merged()
    print(f"맞춘 종 {len(rec)} · 뺀 학명 {len(skipped)}: {skipped}")
    from sheets_api import Sheet
    sh = Sheet("birds")
    meta = sh.meta()
    tabs = [s["properties"] for s in meta["sheets"]]
    species_tabs = []
    for p in tabs:
        if not p["title"].endswith("v2026") or p["title"].startswith("과단위"):
            continue
        species_tabs.append(p)
    # 시트 순서대로 종 행을 모은다(지정관리종목록 순서용)
    seq, cells = [], []
    allv = sh.values_many([p["title"] for p in species_tabs])
    for p in species_tabs:
        vals = allv[p["title"]]
        h = vals[0]
        if "환경부 지정명" in h:
            sys.exit(f"{p['title']}: 이미 '환경부 지정명' 열이 있다")
        assert h[3:6] == ["SCIENTIFIC NAME", "ENGLISH NAME: AVILIST", "명칭 제안"], (p["title"], h[:6])
        for i, r in enumerate(vals[1:], start=2):
            rank = (r[0] if r else "").strip().lower()
            sci = (r[3] if len(r) > 3 else "").strip()
            if rank == "species" and sci in rec:
                seq.append(sci)
                cells.append((p["title"], i, rec[sci]["moe"]))
    missing = [s for s in rec if s not in seq]
    print(f"종 탭에서 찾은 행 {len(cells)} · 못 찾은 종 {missing}")

    # 지정관리종목록 행
    head = ["과(Family)", "학명", "속명", "종명", "환경부 지정명", "국내 통용/유통명"] + [c for _, c in LIST_COLS] + \
           ["법령 학명(옛 학명)", "국명·영명 부여 보고서(2018) 기존국명", "국명·영명 부여 보고서(2018) 개칭명", "법령별 국명"]
    rows, cur_order = [head], None
    order_ko = {t["sci"]: t.get("name") for t in json.loads((DATA / "names.json").read_text(encoding="utf-8"))
                if t["group"] == "AVES" and t["rank"] == "order"}
    label = {"cites": "CITES", "white": "백색목록", "inflow": "유입주의", "export": "수출입", "facility": "사육시설"}
    for s in seq:
        m = rec[s]
        if m["order"] != cur_order:
            cur_order = m["order"]
            rows.append([f"{order_ko.get(cur_order) or ''} ({cur_order})".strip()])
        nb = m["nibr"] or {}
        rows.append([m["family"] or "", s, s.split()[0], s.split()[1], m["moe"] or "", ""] +
                    [m["lists"].get(k, "") for k, _ in LIST_COLS] +
                    [", ".join(m["law_sci"]), nb.get("old") or "", nb.get("new") or "",
                     " / ".join(f"{label[k]}: {v}" for k, v in m["names"].items())])
    with open(DATA / "moe_birds_preview.csv", "w", encoding="utf-8-sig", newline="") as f:
        csv.writer(f).writerows(rows)
    print("미리보기:", DATA / "moe_birds_preview.csv", len(rows) - 1, "행")
    if not apply:
        return

    # 백업
    import urllib.request
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    with urllib.request.urlopen(f"https://docs.google.com/spreadsheets/d/{sh.id}/export?format=xlsx", timeout=120) as r:
        body = r.read()
    if not body.startswith(b"PK"):
        sys.exit("백업 실패: xlsx 가 아닌 응답")
    bk = ROOT / ".secrets" / "backup" / f"birds_before_moe_{stamp}.xlsx"
    bk.write_bytes(body)
    print("백업:", bk)

    # 1) 열 끼워 넣기(종 탭마다 F 앞에 2열), 2) 새 탭
    req = [{"insertDimension": {"range": {"sheetId": p["sheetId"], "dimension": "COLUMNS", "startIndex": 5, "endIndex": 7},
                                "inheritFromBefore": True}} for p in species_tabs]
    if TAB not in [p["title"] for p in tabs]:
        req.append({"addSheet": {"properties": {"title": TAB, "index": 1,
                                                "gridProperties": {"rowCount": len(rows) + 20, "columnCount": len(head),
                                                                   "frozenRowCount": 1}}}})
    sh.batch(req)
    data = [{"range": f"'{p['title']}'!F1:G1", "values": [["환경부 지정명", "국내 통용/유통명"]]} for p in species_tabs]
    data += [{"range": f"'{t}'!F{i}", "values": [[v or ""]]} for t, i, v in cells]
    data.append({"range": f"'{TAB}'!A1", "values": rows})
    sh.update(data)
    print("시트에 반영:", len(species_tabs), "탭 ·", len(cells), "행 · 지정관리종목록", len(rows) - 1, "행")


if __name__ == "__main__":
    main("--apply" in sys.argv)
