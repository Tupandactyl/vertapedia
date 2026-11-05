"""AviList 분포 설명(data/bird_range.json)의 지명을 나라·지역 코드로 바꿔 data/bird_range_places.json 에 둔다.
→ {학명: {"n": [이름이 나온 곳], "h": [이름은 없지만 그 사이에 있는 곳], "t": [그 사이에 일부만 걸치는 곳], "i": [도입지],
          "s": 바닷새 등 나라로 다 못 적는 설명이면 1}}

분포 설명은 'A 에서 B 까지' 처럼 양 끝만 적는 경우가 많으므로, 같은 절(; 로 나눔)에 나온 곳들을 잇는 볼록 껍질 안의 나라를
'h' 로 둔다. 실제 판정(기록이 있어야 칠함)은 scripts/distrule.py 의 bird_habitat.

Natural Earth 원본은 저장소에 올리지 않는다:
    python scripts/build_range_places.py <ne_10m_admin_1_states_provinces 폴더>
"""
import json
import re
import sys
from pathlib import Path

import shapefile
from babel import Locale
from shapely.geometry import MultiPoint, Point, shape
from shapely.prepared import prep

from build_world_map import SPLIT, region

DATA = Path(__file__).resolve().parent.parent / "data"

EUROPE = "AL AD AT BY BE BA BG HR CY CZ DK EE FI FR DE GR HU IE IT XK LV LI LT LU MT MD MC ME NL MK NO PL PT RO RU SM RS SK SI ES SE CH UA GB IS"
WEST_AF = "SN GM GW GN SL LR CI GH TG BJ NG ML BF NE MR"
CENT_AF = "CM CF TD CG CD GA GQ AO ST"
EAST_AF = "ET ER DJ SO KE UG TZ RW BI SS SD"
SOUTH_AF = "ZA NA BW ZW MZ ZM MW LS SZ AO"
NORTH_AF = "MA DZ TN LY EG EH"
SSA = f"{WEST_AF} {CENT_AF} {EAST_AF} {SOUTH_AF}"
SE_ASIA = "MM TH LA VN KH MY SG BN ID ID-WAL ID-PAP PH TL"
CENT_ASIA = "KZ KG TJ TM UZ"
MIDEAST = "SA YE OM AE QA BH KW IQ IR SY JO LB IL PS TR"
ARABIA = "SA YE OM AE QA BH KW"
S_ASIA = "IN PK NP BT BD LK AF MV"
E_ASIA = "CN CN-NE CN-W JP JP-OKI KR KP TW MN HK MO"
ASIA = f"{SE_ASIA} {CENT_ASIA} {MIDEAST} {S_ASIA} {E_ASIA} RU-AS"
CENT_AM = "BZ GT SV HN NI CR PA"
SOUTH_AM = "CO VE GY SR GF EC PE BO CL AR PY UY BR"
GREATER_ANT = "CU JM HT DO PR KY"
LESSER_ANT = "AG AI BB BL BQ DM GD GP KN LC MF MQ MS SX TT VC VG VI AW CW"
CARIB = f"{GREATER_ANT} {LESSER_ANT} BS TC"
POLY = "PF WS TO CK NU TV WF AS TK PN"
MICRO = "FM PW MH GU MP KI NR"
MELA = "SB VU NC FJ PG"
AMAZON = "BR PE CO EC BO VE GY SR GF"
ANDES = "CO EC PE BO CL AR VE"

# 긴 이름부터 맞춘다. 빈 값은 '지명이 아니라 바다·강 등' 이라 건너뛴다
CURATED = {
    # 넓은 지역
    "Europe": EUROPE, "Palearctic": f"{EUROPE} RU-AS {CENT_ASIA} MN CN CN-NE CN-W JP KR KP {NORTH_AF}",
    "Eurasia": f"{EUROPE} {ASIA}", "Asia": ASIA, "Africa": f"{SSA} {NORTH_AF}", "Saharan Africa": SSA,
    "Africa south of the Sahara": SSA, "sub-Saharan Africa": SSA, "Sub-Saharan Africa": SSA,
    "North Africa": NORTH_AF, "northern Africa": NORTH_AF, "northwestern Africa": "MA DZ TN EH MR",
    "northeastern Africa": "EG SD ER ET DJ SO", "West Africa": WEST_AF, "western Africa": WEST_AF,
    "East Africa": EAST_AF, "eastern Africa": EAST_AF, "Central Africa": CENT_AF, "central Africa": CENT_AF,
    "southern Africa": SOUTH_AF, "southeastern Africa": "ZA MZ ZW MW TZ SZ", "southwestern Africa": "NA AO ZA BW",
    "Southeast Asia": SE_ASIA, "southeastern Asia": SE_ASIA, "South Asia": S_ASIA, "southern Asia": f"{S_ASIA} {SE_ASIA}",
    "East Asia": E_ASIA, "eastern Asia": f"{E_ASIA} RU-AS", "Central Asia": CENT_ASIA, "central Asia": f"{CENT_ASIA} MN CN-W",
    "western Asia": MIDEAST, "southwestern Asia": f"{MIDEAST} AF PK", "northern Asia": "RU-AS MN", "northeastern Asia": "RU-AS CN-NE JP KR KP",
    "Middle East": MIDEAST, "Levant": "IL PS JO LB SY", "Arabian Peninsula": ARABIA, "Arabia": ARABIA,
    "North America": "CA US US-AK MX", "Central America": CENT_AM, "South America": SOUTH_AM, "Neotropics": f"MX {CENT_AM} {SOUTH_AM}",
    "Caribbean": CARIB, "West Indies": CARIB, "Greater Antilles": GREATER_ANT, "Lesser Antilles": LESSER_ANT, "Antilles": CARIB,
    "Arctic": "CA US-AK RU RU-AS GL NO SJ IS FI SE", "Polynesia": POLY, "Micronesia": MICRO, "Melanesia": MELA,
    "Oceania": f"{POLY} {MICRO} {MELA}", "Australasia": "AU AU-TAS NZ PG ID-PAP", "Mediterranean": "ES PT FR IT GR TR HR AL ME MT CY MA DZ TN LY EG IL LB SY",
    "Balkans": "AL BA BG GR HR ME MK RO RS XK", "Scandinavia": "NO SE FI DK", "Fennoscandia": "NO SE FI", "British Isles": "GB IE",
    "Iberian Peninsula": "ES PT", "Iberia": "ES PT", "Baltic": "EE LV LT FI SE PL", "Caucasus": "GE AM AZ RU",
    "Sahara": "MA DZ TN LY EG MR ML NE TD SD EH", "Sahel": "SN MR ML BF NE TD SD ER NG", "Senegambia": "SN GM",
    "Horn of Africa": "SO ET DJ ER", "Congo Basin": "CD CG CF CM GA", "Congolian": "CD CG CF CM GA", "Karoo": "ZA NA",
    "Indochina": "MM TH LA VN KH", "Malayan Peninsula": "MY TH SG MM", "Malay Peninsula": "MY TH SG MM", "Thai-Malay Peninsula": "MY TH SG MM",
    "Greater Sundas": "ID MY BN", "Lesser Sundas": "ID-WAL TL", "Indonesian Archipelago": "ID ID-WAL ID-PAP", "Wallacea": "ID-WAL TL",
    "Himalayas": "IN NP BT PK CN-W AF", "Himalayan": "IN NP BT PK CN-W", "Peninsular India": "IN", "Indian subcontinent": "IN PK NP BT BD LK",
    "Korean Peninsula": "KR KP", "Korea": "KR KP", "Manchuria": "CN-NE RU-AS", "Tibet": "CN-W", "Tibetan Plateau": "CN-W",
    "Siberia": "RU-AS", "Ussuriland": "RU-AS", "Kamchatka": "RU-AS", "Sakhalin": "RU-AS", "Kuril Islands": "RU-AS", "Commander Islands": "RU-AS", "Sea of Okhotsk": "RU-AS JP",
    "Bering Sea": "RU-AS US-AK", "Russia": "RU RU-AS", "China": "CN CN-NE CN-W", "Indonesia": "ID ID-WAL ID-PAP", "Japan": "JP JP-OKI",
    "Australia": "AU AU-TAS", "United States": "US", "USA": "US", "US": "US", "Aleutians": "US-AK", "Aleutian Islands": "US-AK", "Hawaiian Islands": "US-HI",
    # 아메리카
    "Guianas": "GY SR GF", "Guiana Shield": "VE GY SR GF BR", "Andes": ANDES, "Andean": ANDES, "Amazon": AMAZON, "Amazonia": AMAZON, "Amazonian": AMAZON,
    "Amazonian Brazil": "BR", "Amazonian Peru": "PE", "Amazonian Ecuador": "EC", "Amazonian Colombia": "CO", "Amazonian Bolivia": "BO",
    "Amazon River": "", "Andes of": "", "Amazon of": "", "Orinoco and Amazon": "", "Atlantic Forest": "BR AR PY", "Cerrado": "BR PY BO", "Caatinga": "BR",
    "Chaco": "AR PY BO", "Pantanal": "BR BO PY", "Patagonia": "AR CL", "Tierra del Fuego": "AR CL", "Llanos": "CO VE", "Orinoco": "CO VE",
    "Magdalena Valley": "CO", "Cauca and Magdalena": "CO", "Chocó": "CO EC PA", "Sierra de Perijá": "CO VE", "Sierra Nevada de Santa Marta": "CO",
    "Paría Peninsula": "VE", "Marañón Valley": "PE", "Río Marañón": "PE", "Marañón": "PE", "Yucatan Peninsula": "MX GT BZ", "Baja California": "MX",
    "Cozumel": "MX", "Hispaniola": "HT DO", "Trinidad and Tobago": "TT", "Trinidad": "TT", "Tobago": "TT", "French Guiana": "GF", "Cape Breton": "CA", "Labrador": "CA", "Newfoundland": "CA",
    "Falkland Islands": "FK", "South Georgia": "GS", "Galapagos": "EC-GAL", "Galápagos": "EC-GAL", "Greenland": "GL",
    # 아프리카·인도양
    "Democratic Republic of Congo": "CD", "Democratic Republic of the Congo": "CD", "Democratic Republic": "CD", "Republic of Congo": "CG", "Republic of the Congo": "CG", "Congo": "CD CG",
    "Bioko": "GQ", "Zanzibar": "TZ", "Pemba": "TZ", "São Tomé": "ST", "Príncipe": "ST", "Annobón": "GQ", "Gulf of Guinea": "", "Mascarenes": "RE MU", "Rodrigues": "MU", "Socotra": "YE",
    "Canary Islands": "ES-CN", "Madeira": "PT-MA", "Azores": "PT-AC", "Balearic Islands": "ES", "Corsica": "FR", "Sardinia": "IT", "Sicily": "IT", "Crete": "GR", "Cabo Verde": "CV", "Comoros": "KM YT",
    # 아시아 섬·산지
    "New Guinea": "ID-PAP PG", "Papua New Guinea": "PG", "Bismarck Archipelago": "PG", "New Britain": "PG", "New Ireland": "PG", "Bougainville": "PG", "Louisiade Archipelago": "PG", "D'Entrecasteaux": "PG",
    "Borneo": "BN MY ID", "Sumatra": "ID", "Java": "ID", "Bali": "ID", "Bangka": "ID", "Lombok": "ID-WAL", "Flores": "ID-WAL", "Sumba": "ID-WAL", "Sumbawa": "ID-WAL", "Timor": "ID-WAL TL",
    "Sulawesi": "ID-WAL", "Moluccas": "ID-WAL", "Halmahera": "ID-WAL", "Tanimbar Islands": "ID-WAL", "Aru Islands": "ID-WAL", "Banggai": "ID-WAL", "Sangihe": "ID-WAL", "Talaud": "ID-WAL", "Seram": "ID-WAL", "Buru": "ID-WAL",
    "Raja Ampat Islands": "ID-PAP", "Cenderawasih Bay": "ID-PAP", "Yapen": "ID-PAP", "Biak": "ID-PAP", "Luzon": "PH", "Mindanao": "PH", "Palawan": "PH", "Mindoro": "PH", "Sulu Archipelago": "PH", "Visayas": "PH", "Negros": "PH", "Panay": "PH",
    "Honshu": "JP", "Hokkaido": "JP", "Kyushu": "JP", "Shikoku": "JP", "Ryukyu Islands": "JP-OKI JP", "Izu Islands": "JP", "Bonin Islands": "JP", "Andaman Islands": "IN-AN", "Nicobar Islands": "IN-AN", "Andaman and Nicobar": "IN-AN",
    "Western Ghats": "IN", "Eastern Ghats": "IN", "Kashmir": "IN PK", "Assam": "IN", "Hainan": "CN", "Lakshadweep": "IN", "Maldives": "MV", "Chagos": "IO",
    # 오세아니아
    "Wet Tropics": "AU", "Kimberley": "AU", "Cape York Peninsula": "AU", "Cape York": "AU", "Top End": "AU", "Lord Howe Island": "AU", "Norfolk Island": "NF", "South Island": "NZ", "North Island": "NZ", "Stewart": "NZ", "Chatham Islands": "NZ",
    "Solomon Islands": "SB PG", "Solomon Archipelago": "SB PG", "Vanuatu": "VU", "Caroline Islands": "FM PW", "Mariana Islands": "GU MP", "Marianas": "GU MP", "Marquesas Islands": "PF", "Society Islands": "PF", "Tuamotu": "PF",
    # 나라 다른 표기
    "Türkiye": "TR", "Turkey": "TR", "Myanmar": "MM", "Burma": "MM", "Vietnam": "VN", "Laos": "LA", "Eswatini": "SZ", "Swaziland": "SZ", "Ivory Coast": "CI", "Côte d'Ivoire": "CI", "UK": "GB", "Great Britain": "GB", "Britain": "GB", "Scotland": "GB", "England": "GB", "Wales": "GB", "Ireland": "IE", "Holland": "NL", "Czechia": "CZ", "East Timor": "TL", "Timor-Leste": "TL", "South Korea": "KR", "North Korea": "KP",
    # 작은 섬·산지·지방
    "Sula": "ID-WAL", "Bacan": "ID-WAL", "Kai": "ID-WAL", "Wetar": "ID-WAL", "Alor": "ID-WAL", "Ambon": "ID-WAL", "Togian": "ID-WAL", "Morotai": "ID-WAL", "Obi": "ID-WAL", "Rote": "ID-WAL", "Peleng": "ID-WAL", "Buton": "ID-WAL", "Taliabu": "ID-WAL", "Babar": "ID-WAL", "Ternate": "ID-WAL", "Mangole": "ID-WAL", "Lembeh": "ID-WAL", "Muna": "ID-WAL", "Yamdena": "ID-WAL", "Banda": "ID-WAL", "Larat": "ID-WAL", "Tukangbesi": "ID-WAL", "Sanana": "ID-WAL", "Semau": "ID-WAL",
    "Natuna": "ID", "Belitung": "ID", "Nias": "ID", "Mentawai": "ID", "Kangean": "ID", "Lingga": "ID", "Simeulue": "ID",
    "Salawati": "ID-PAP", "Misool": "ID-PAP", "Numfor": "ID-PAP", "Waigeo": "ID-PAP", "Batanta": "ID-PAP", "Bird's Head Peninsula": "ID-PAP", "Arfak": "ID-PAP", "Arfak Mountains": "ID-PAP", "Tamrau": "ID-PAP", "Foja Mountains": "ID-PAP", "Snow Mountains": "ID-PAP", "Trans-Fly": "ID-PAP PG",
    "Admiralty": "PG", "Huon Peninsula": "PG", "Huon": "PG", "Buka": "PG", "Mussau": "PG", "St. Matthias Group": "PG", "Torres Strait": "AU PG", "Rennell": "SB", "Kolombangara": "SB",
    "Balabac": "PH", "Busuanga": "PH", "Calamian": "PH", "Culion": "PH", "Tawitawi": "PH", "Jolo": "PH", "Ticao": "PH", "Tablas": "PH",
    "Kauai": "US-HI", "Oahu": "US-HI", "Maui": "US-HI", "Molokai": "US-HI", "Lanai": "US-HI", "Alaskan": "US-AK",
    "Ogasawara": "JP", "Bonin": "JP", "Iwo": "JP", "Yakushima": "JP", "Izu": "JP",
    "Chukotskiy Peninsula": "RU-AS", "Chukotka": "RU-AS", "Amurland": "RU-AS", "Russian Far East": "RU-AS", "Transbaikalia": "RU-AS", "Lake Baikal": "RU-AS", "Wrangel Island": "RU-AS", "New Siberian": "RU-AS", "Lena": "RU-AS", "Kuril": "RU-AS", "Commander": "RU-AS", "Ural Mountains": "RU RU-AS", "Novaya Zemlya": "RU", "Altai": "RU-AS MN CN-W KZ", "Inner Mongolia": "CN-NE",
    "Holarctic": f"{EUROPE} RU-AS CA US US-AK GL", "Old World": f"{EUROPE} {ASIA} {SSA} {NORTH_AF}",
    "Tenasserim": "MM TH", "Tonkin": "VN", "Langbian": "VN", "Hong Kong": "HK", "Goa": "IN", "Indian Peninsula": "IN", "Indian Subcontinent": "IN PK NP BT BD LK", "Indus Valley": "PK", "Punjab": "IN PK", "Brahmaputra": "IN BD", "Peninsular Malaysia": "MY", "Sinai Peninsula": "EG", "Nile Valley": "EG SD", "Nile River": "EG SD",
    "Unguja": "TZ", "Mafia Island": "TZ", "Aldabra": "SC", "Mahé": "SC", "Malagasy": "MG", "Mascarene": "RE MU", "Mohéli": "KM", "Grand Comoro Island": "KM", "Fynbos": "ZA", "Cape Province": "ZA", "Albertine Rift": "CD UG RW BI TZ", "Namib and Kalahari": "NA BW ZA", "Kalahari": "NA BW ZA",
    "Pyrenees": "ES FR", "European Alps": "FR IT CH AT DE SI",
    "Rocky Mountains": "US CA", "Quebec": "CA", "Hudson Bay": "CA", "Great Plains": "US CA", "Great Basin": "US", "Appalachians": "US", "Appalachian Mountains": "US", "Florida": "US", "Maryland": "US", "Montana": "US", "Sierra Madre": "MX", "Sierra Madre Occidental": "MX", "Michoacan": "MX", "Tres Marias": "MX", "Tres Marías": "MX", "Tuxtlas": "MX", "Revillagigedo": "MX", "Isthmus of Tehuantepec": "MX", "Guadalupe Island": "MX", "Socorro Island": "MX", "Holbox": "MX",
    "Coiba": "PA", "Azuero Peninsula": "PA", "Cerro Pirre": "PA", "Cerro Tacarcuna": "PA CO", "Cocos Island": "CR", "St. Vincent": "VC", "Vieques": "PR", "Gonâve": "HT", "Gonâve Island": "HT", "Grand Cayman": "KY", "Grand Bahama": "BS", "Grand Bahama and Abaco": "BS", "Andros": "BS", "San Andrés": "CO",
    "Margarita": "VE", "Guajira Peninsula": "CO VE", "Paria Peninsula": "VE", "Santa Marta and Perijá": "CO VE", "Caqueta": "CO", "Río Patía": "CO", "Río Patía Valley": "CO", "Yungas": "BO PE", "Beni": "BO", "Ancash": "PE", "Ica": "PE", "Apurimac": "PE", "Vilcabamba": "PE", "Río Huallaga": "PE", "Cerros del Sira": "PE", "Pampas del Heath": "PE BO", "Manabí": "EC", "Zamora-Chinchipe": "EC", "Fernandina": "EC-GAL", "Floreana": "EC-GAL",
    "Brazilian": "BR", "Espirito Santo": "BR", "Paraiba": "BR", "Piaui": "BR", "Santa Catarina": "BR", "Rio Tapajós": "BR", "Rio Tapajos": "BR", "Rio Xingu": "BR", "Rio Branco": "BR", "Misiones": "AR PY", "Tucuman": "AR", "Cape Horn": "CL AR", "Cape Horn Archipelago": "CL AR", "Juan Fernández": "CL", "Arica": "CL",
    "Pilbara": "AU", "Arnhem Land": "AU", "Eyre Peninsula": "AU", "Kangaroo Island": "AU", "Flinders Ranges": "AU", "Mount Lofty Range": "AU", "Lord Howe": "AU", "Chatham": "NZ", "Loyalty": "NC", "Grande Terre": "NC", "Tahiti": "PF", "Moorea": "PF", "Marquesas": "PF", "Gambier": "PF", "Yap": "FM", "Babelthuap": "PW", "Viti Levu": "FJ", "Vanua Levu": "FJ", "Taveuni": "FJ", "Pitcairn": "PN", "Henderson Island": "PN",
    # 나눈 나라의 방향 표현
    "southeastern Russia": "RU-AS", "eastern Russia": "RU-AS", "far eastern Russia": "RU-AS", "northeastern Russia": "RU-AS", "Asian Russia": "RU-AS", "western Russia": "RU", "European Russia": "RU", "northwestern Russia": "RU",
    "western China": "CN-W", "northwestern China": "CN-W", "northeastern China": "CN-NE", "eastern China": "CN", "southern China": "CN", "southeastern China": "CN", "central China": "CN", "southwestern China": "CN",
    "eastern Indonesia": "ID-WAL ID-PAP", "western Indonesia": "ID", "mainland Australia": "AU", "Anadyrland": "RU-AS", "Faroe": "FO", "Faroes": "FO", "Shetland": "GB",
    # 지명이 아닌 것
    "Bass Strait": "", "Arabian Sea": "", "Tasman Sea": "", "Arafura Sea": "", "Yellow Sea": "", "Brahmaputra River": "", "Indus River": "", "Fly River": "",
    "Gulf of Mexico": "", "Gulf of California": "", "Gulf of Alaska": "", "Gulf of Aden": "", "Gulf of Oman": "", "Persian Gulf": "", "Red Sea": "", "Black Sea": "", "Caspian Sea": "", "Atlantic": "", "Pacific": "", "Indian Ocean": "", "North Atlantic": "", "North Pacific": "", "Niger River": "", "Congo River": "", "New Mexico": "US", "Rio Grande": "", "Río Negro": "", "Rio Negro": "", "Rio Madeira": "",
    "Polylepis": "", "Puerto Rico": "PR", "Georgia": "GE", "Santa Cruz": "", "La Paz": "BO", "Victoria": "AU", "Buenos Aires": "AR",
}
MARINE = re.compile(r"\b(oceans?|pelagic|at sea|seas\b|waters|worldwide|cosmopolitan|global(?:ly)?|all (?:\w+ )?continents|circumpolar|subantarctic|Antarctic|tropical and)\b", re.I)
MIGRANT = re.compile(r"\b(?:breeds?|breeding|winters?|wintering|nonbreeding|migrat\w+|summers?)\b", re.I)
NOT_HERE = re.compile(r"\((?:except|but absent|excluding|absent)[^)]*\)", re.I)
NOT_HERE_END = re.compile(r"\b(?:except|excluding|(?:breeding |now |but )?absent)\b.*$", re.I)
# 이 낱말 뒤로는 지금 서식지가 아니다(그 절 끝까지). 절멸종처럼 다른 지명이 없으면 이것을 쓴다
FORMER = re.compile(r"\b(?:formerly|extirpated|historically|vagrants?|casual(?:ly)?|accidental|rarely)\b", re.I)
INTRO = re.compile(r"\b(?:(?:perhaps|possibly|likely|widely|now|locally|and)\s+)*introduced\b", re.I)


def gazetteer(adm1_dir):
    ter = Locale("en").territories
    gaz = {}
    for k, name in ter.items():
        if len(k) == 2 and k.isalpha() and k not in ("ZZ", "EU", "UN", "QO", "XA", "XB"):
            gaz[name] = k
    # 나라 영어 이름 가운데 흔히 쓰는 짧은 꼴
    for name, k in list(gaz.items()):
        short = re.sub(r"\s*\(.*\)$|^The |^St\. ", "", name)
        gaz.setdefault(short, k)
    r1 = shapefile.Reader(str(next(Path(adm1_dir).glob("*.shp"))), encoding="utf-8")
    fields = [f[0] for f in r1.fields[1:]]
    seen = {}
    for sr in r1.iterShapeRecords():
        rec = dict(zip(fields, sr.record))
        name, a3, iso = rec.get("name") or "", rec.get("adm0_a3"), rec.get("iso_a2")
        if len(name) < 4 or not iso or iso == "-1":
            continue
        code = iso
        if a3 in SPLIT:
            c = shape(sr.shape.__geo_interface__).representative_point()
            code = region(a3, name, c.x, c.y)
        seen.setdefault(name, set()).add(code)
    # 두 나라 이상에 같은 이름이면(Amazonas 등) 설명에 그 나라가 함께 나올 때만 쓴다
    ambig = {}
    for name, codes in seen.items():
        if name in gaz or name in CURATED:
            continue
        if len({c.split("-")[0] for c in codes}) == 1:
            gaz[name] = " ".join(sorted(codes))
        else:
            ambig[name] = codes
    gaz.update(CURATED)
    return gaz, ambig


def compile_gaz(names):
    names = sorted(names, key=len, reverse=True)
    return re.compile(r"(?<![\w'’-])(" + "|".join(re.escape(n) for n in names) + r")(?![\w'’-])")


def centres():
    """지도 코드별 안쪽 표본점과 윤곽 꼭짓점(조각마다 볼록 껍질로 줄여 둔다)"""
    world = json.loads((DATA / "world.geojson").read_text(encoding="utf-8"))
    cen, outline = {}, {}
    for f in world["features"]:
        g = shape(f["geometry"]).buffer(0)
        if g.is_empty:  # 단순화에서 사라진 아주 작은 섬
            continue
        p = g.representative_point()
        x0, y0, x1, y1 = g.bounds
        grid = [Point(x0 + (x1 - x0) * (i + .5) / 6, y0 + (y1 - y0) * (j + .5) / 6) for i in range(6) for j in range(6)]
        cen[f["properties"]["c"]] = [(q.x, q.y) for q in grid if g.contains(q)] or [(p.x, p.y)]
        pts = []
        for part in (g.geoms if g.geom_type == "MultiPolygon" else [g]):
            if part.area > 0.05:
                pts += list(part.convex_hull.exterior.coords)
        outline[f["properties"]["c"]] = pts or [(p.x, p.y)]
    return cen, outline


def between(codes, cen, outline):
    """이름이 나온 곳들의 윤곽을 잇는 볼록 껍질 안의 지도 코드: (표본점 4분의 1 이상이 안, 일부라도 안).
    지구 반 바퀴 넘게 벌어지면(대륙을 건너뛰는 설명) 없음"""
    pts = [p for k in codes if k in outline for p in outline[k]]
    if not pts or len({k for k in codes if k in outline}) < 2:
        return set(), set()
    for cut in (-180, -34):
        xy = [((x + 360) if x < cut else x, y) for x, y in pts]
        xs = [x for x, _ in xy]
        if max(xs) - min(xs) <= 200:
            hull = prep(MultiPoint(xy).convex_hull)
            core, touch = set(), set()
            for k, sample in cen.items():
                n = sum(hull.contains(Point((x + 360) if x < cut else x, y)) for x, y in sample)
                if n:
                    touch.add(k)
                if n * 4 >= len(sample):
                    core.add(k)
            return core, touch
    return set(), set()


def parse(text, rx, gaz, ambig_rx, ambig, cen, outline):
    native, intro, hull, touch, former = set(), set(), set(), set(), set()
    found_all = {m.group(1) for m in rx.finditer(text)}
    base_named = {c.split("-")[0] for n in found_all for c in gaz[n].split()}
    text = NOT_HERE.sub(" ", text)  # '(except ...)', 'absent from ...' 는 분포가 아니다
    for clause in re.split(r";|\.\s+(?=[A-Z])", text):
        clause = NOT_HERE_END.sub("", clause)
        m = INTRO.search(clause)
        parts = [(clause[: m.start()], False), (clause[m.end():], True)] if m else [(clause, False)]
        here = set()
        for part, is_intro in parts:
            old = FORMER.search(part)
            past = part[old.end():] if old else ""
            part = part[:old.start()] if old else part
            for g in rx.finditer(past):
                former |= set(gaz[g.group(1)].split())
            codes = set()
            for g in rx.finditer(part):
                codes |= set(gaz[g.group(1)].split())
            if ambig_rx:
                for g in ambig_rx.finditer(part):
                    codes |= {c for c in ambig[g.group(1)] if c.split("-")[0] in base_named}
            if is_intro:
                intro |= codes
            else:
                native |= codes
                here |= codes
        core, part_in = between(here, cen, outline)
        hull |= core
        touch |= part_in
    if MIGRANT.search(text):  # 번식지와 월동지 사이의 경유지
        core, part_in = between(native, cen, outline)
        hull |= core
        touch |= part_in
    native = native or former
    return native, hull - native, touch - hull - native, intro - native


def main(adm1_dir):
    ranges = json.loads((DATA / "bird_range.json").read_text(encoding="utf-8"))
    gaz, ambig = gazetteer(adm1_dir)
    rx, ambig_rx = compile_gaz(gaz), compile_gaz(ambig) if ambig else None
    cen, outline = centres()
    out = {}
    for sci, text in ranges.items():
        n, h, t, i = parse(text, rx, gaz, ambig_rx, ambig, cen, outline)
        rec = dict(n=sorted(n), h=sorted(h), t=sorted(t), i=sorted(i))
        if MARINE.search(text):
            rec["s"] = 1
        out[sci] = rec
    (DATA / "bird_range_places.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print("종", len(out), "· 지명 하나도 못 읽음", sum(not v["n"] and not v["i"] for v in out.values()),
          "· 바닷새 등", sum("s" in v for v in out.values()), "· 도입 설명", sum(bool(v["i"]) for v in out.values()))


if __name__ == "__main__":
    main(sys.argv[1])
