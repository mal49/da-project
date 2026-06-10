"""
🏸 Roster expander — turns the cleaned tournament CSVs into extra frontend
players so the bracket simulator has a deep enough pool (32+ per division → the
R32 draw unlocks).

The cleaned CSVs hold real names + match history (pre-match rank, Elo, results)
but NO nationality, and they only spell out non-truncated names. So this script:

  1. Derives current Elo / rank / form / record for each clean singles player
     straight from the CSV history (same maths as ingest_tournaments.py).
  2. Joins a curated {CSV name -> display name, country, hand} table for the
     well-known players we want to add (country comes from knowledge of these
     real pros, since the CSVs don't carry it).
  3. Emits src/players.generated.ts (GENERATED_PLAYERS: Player[]), which
     src/players.ts concatenates onto its hand-authored core roster.

Adding players:
  * See every name in the CSVs (and its match count):
        python build_roster.py --list          (or --list men / --list women)
  * Add a player with REAL history: put an entry in NEW keyed by the exact CSV
    name from --list. If that name is truncated ('..'), key it by a distinctive
    PREFIX instead (e.g. "Putri Kusuma WAR") — history_for() merges the rows.
  * Add a player with no/clean CSV match: put a full entry in MANUAL (you set the
    stats). The display name there is never truncated.
  Then re-run `python build_roster.py` and the frontend picks it up automatically.

Automating the whole thing:
  * `python build_roster.py --auto`  adds EVERY singles player it can identify a
    country for (from the rankings/players files + the roster you already have),
    on top of NEW/MANUAL. `--min N` sets the match-count cutoff (default 12).
  * It prints anyone whose country it couldn't find — paste those into COUNTRY
    once (name -> ISO-3) and they're included on every future run.

Run:  cd backend && python build_roster.py            # curated (NEW + MANUAL)
      cd backend && python build_roster.py --auto      # + everyone identifiable
Stdlib only.
"""

from __future__ import annotations

import csv
import glob
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
OUT = HERE.parent / "src" / "players.generated.ts"
SINGLES = {"MS", "WS"}
DOUBLES = {"MD", "WD", "XD"}
# A doubles/mixed PAIR needs this many matches to enter the pool. MUST match
# ingest_tournaments.MIN_PAIR_MATCHES so the rating keys and pool names line up.
MIN_PAIR_MATCHES = 4

# ISO-3 (IOC/BWF) -> flag emoji. Matches the codes used in src/players.ts.
FLAG = {
    "CHN": "🇨🇳", "THA": "🇹🇭", "DEN": "🇩🇰", "FRA": "🇫🇷", "INA": "🇮🇩",
    "TPE": "🇹🇼", "IND": "🇮🇳", "MAS": "🇲🇾", "SGP": "🇸🇬", "JPN": "🇯🇵",
    "KOR": "🇰🇷", "ESP": "🇪🇸", "HKG": "🇭🇰", "CAN": "🇨🇦", "USA": "🇺🇸",
    "NED": "🇳🇱", "IRL": "🇮🇪", "GER": "🇩🇪", "VIE": "🇻🇳", "BEL": "🇧🇪",
    "SCO": "🏴\U000e0067\U000e0062\U000e0073\U000e0063\U000e0074\U000e007f",
    "ENG": "🏴\U000e0067\U000e0062\U000e0065\U000e006e\U000e0067\U000e007f",
    "MAC": "🇲🇴", "AUS": "🇦🇺", "RUS": "🇷🇺",
}

# Left-handers among the additions (everyone else defaults to 'R').
LEFTIES = {"Kento Momota"}

# New players to add, keyed by the EXACT name as it appears in the cleaned CSVs
# (so the history join is exact). value = (display name, ISO-3 country, women?).
# The 30 core players already in src/players.ts are intentionally NOT listed.
NEW: dict[str, tuple[str, str, bool]] = {
    # ---- men's singles ----
    "LU Guang Zu": ("Lu Guang Zu", "CHN", False),
    "NG Ka Long Angus": ("Ng Ka Long Angus", "HKG", False),
    "WANG Tzu Wei": ("Wang Tzu Wei", "TPE", False),
    "Rasmus GEMKE": ("Rasmus Gemke", "DEN", False),
    "KIDAMBI Srikanth": ("Kidambi Srikanth", "IND", False),
    "Brian YANG": ("Brian Yang", "CAN", False),
    "WENG Hong Yang": ("Weng Hong Yang", "CHN", False),
    "ZHAO Jun Peng": ("Zhao Jun Peng", "CHN", False),
    "Koki WATANABE": ("Koki Watanabe", "JPN", False),
    "Kanta TSUNEYAMA": ("Kanta Tsuneyama", "JPN", False),
    "Kento MOMOTA": ("Kento Momota", "JPN", False),
    "LEE Chia Hao": ("Lee Chia Hao", "TPE", False),
    "Nhat NGUYEN": ("Nhat Nguyen", "IRL", False),
    "Alex LANIER": ("Alex Lanier", "FRA", False),
    "LEONG Jun Hao": ("Leong Jun Hao", "MAS", False),
    "NG Tze Yong": ("Ng Tze Yong", "MAS", False),
    "Yushi TANAKA": ("Yushi Tanaka", "JPN", False),
    "LIEW Daren": ("Liew Daren", "MAS", False),
    "Mark CALJOUW": ("Mark Caljouw", "NED", False),
    "Alwi FARHAN": ("Alwi Farhan", "INA", False),
    # ---- women's singles ----
    "KIM Ga Eun": ("Kim Ga Eun", "KOR", True),
    "YEO Jia Min": ("Yeo Jia Min", "SGP", True),
    "ZHANG Beiwen": ("Zhang Beiwen", "USA", True),
    "Michelle LI": ("Michelle Li", "CAN", True),
    "Kirsty GILMOUR": ("Kirsty Gilmour", "SCO", True),
    "Yvonne LI": ("Yvonne Li", "GER", True),
    "Nozomi OKUHARA": ("Nozomi Okuhara", "JPN", True),
    "Tomoka MIYAZAKI": ("Tomoka Miyazaki", "JPN", True),
    "GAO Fang jie": ("Gao Fangjie", "CHN", True),
    "Mia BLICHFELDT": ("Mia Blichfeldt", "DEN", True),
    "ZHANG Yi Man": ("Zhang Yi Man", "CHN", True),
    "Supanida KATETHONG": ("Supanida Katethong", "THA", True),
    "Aya OHORI": ("Aya Ohori", "JPN", True),
    "Line CHRISTOPHERSEN": ("Line Christophersen", "DEN", True),
    "NGUYEN Thuy Linh": ("Nguyen Thuy Linh", "VIE", True),
    "SIM Yu Jin": ("Sim Yu Jin", "KOR", True),
    "GOH Jin Wei": ("Goh Jin Wei", "MAS", True),
    "Iris WANG": ("Iris Wang", "USA", True),
    "Malvika BANSOD": ("Malvika Bansod", "IND", True),
    "Sayaka TAKAHASHI": ("Sayaka Takahashi", "JPN", True),
    "Lianne TAN": ("Lianne Tan", "BEL", True),
    "Natsuki NIDAIRA": ("Natsuki Nidaira", "JPN", True),
    "Lalinrat CHAIWAN": ("Lalinrat Chaiwan", "THA", True),
    "Julie Dawall JAKOBSEN": ("Julie Dawall Jakobsen", "DEN", True),
}

# Fully hand-entered players — use this when a player's CSV name is truncated
# (shows '..') or they aren't in the CSVs at all. Nothing is looked up, so the
# name you type is exactly what appears (never truncated). Set the stats yourself
# (copy Elo/rank off the rankings, or eyeball them). `women` and `hand` optional.
#   Example:
#   {"name": "Putri Kusuma Wardani", "country": "INA", "women": True,
#    "elo": 2247, "rank": 7, "form": [1, 1, 0, 1, 1]},
MANUAL: list[dict] = [
]

# --auto fills countries from the rankings/players files + the roster we already
# have. For anyone it still can't identify, drop a line here (name -> ISO-3) once
# and they're picked up forever after.
COUNTRY: dict[str, str] = {
    # "Busanan Ongbamrungphan": "THA",
}

# Country for prominent doubles/mixed players (the CSVs carry no nationality, and
# doubles specialists rarely show up in the singles rankings, so pair flags would
# otherwise all be neutral). Keyed by individual member name; pair_country resolves
# a pair from its members. Matching is normalized (case/space/hyphen-insensitive),
# so exact punctuation need not match the CSV. Add more to fill in neutral flags.
DOUBLES_COUNTRY: dict[str, str] = {
    # --- China ---
    "Zheng Si Wei": "CHN", "Huang Ya Qiong": "CHN", "Huang Dong Ping": "CHN",
    "Feng Yan Zhe": "CHN", "Wang Chang": "CHN", "Liang Wei Keng": "CHN",
    "He Ji Ting": "CHN", "Zhou Hao Dong": "CHN", "Liu Sheng Shu": "CHN",
    "Tan Ning": "CHN", "Jia Yi Fan": "CHN", "Chen Qing Chen": "CHN",
    "Li Wen Mei": "CHN", "Zhang Shu Xian": "CHN", "Liu Yu Chen": "CHN",
    "Ou Xuan Yi": "CHN", "Ren Xiang Yu": "CHN", "Jiang Zhen Bang": "CHN",
    "Wei Ya Xin": "CHN", "Zhang Wei": "CHN", "Li Yi Jing": "CHN",
    "Xu Wei": "CHN", "Jia Yi": "CHN",
    # --- Korea ---
    "Seo Seung Jae": "KOR", "Kim Won Ho": "KOR", "Kang Min Hyuk": "KOR",
    "Choi Sol Gyu": "KOR", "Jeong Na Eun": "KOR", "Chae Yu Jung": "KOR",
    "Kong Hee Yong": "KOR", "Baek Ha Na": "KOR", "Lee So Hee": "KOR",
    "Lee Yu Lim": "KOR", "Kim So Yeong": "KOR", "Jin Yong": "KOR",
    "Na Sung Seung": "KOR", "Kim Hye Jeong": "KOR",
    # --- Malaysia ---
    "Aaron Chia": "MAS", "Soh Wooi Yik": "MAS", "Chen Tang Jie": "MAS",
    "Tan Wee Kiong": "MAS", "Chan Peng Soon": "MAS", "Hoo Pang Ron": "MAS",
    "Tan Kian Meng": "MAS", "Teoh Mei Xing": "MAS", "Cheah Yee See": "MAS",
    "Lim Chiew Sien": "MAS", "Pearly Tan": "MAS", "Thinaah Muralitharan": "MAS",
    "Goh Sze Fei": "MAS", "Nur Izzuddin": "MAS", "Man Wei Chong": "MAS",
    "Tee Kai Wun": "MAS", "Toh Ee Wei": "MAS", "Pang Ron": "MAS",
    # --- Indonesia ---
    "Muhammad Shohibul Fikri": "INA", "Gloria Emanuelle Widjaja": "INA",
    "Siti Fadia Silva Ramadhanti": "INA", "Apriyani Rahayu": "INA",
    "Febriana Dwipuji Kusuma": "INA", "Ribka Sugiarto": "INA",
    "Rehan Naufal Kusharjanto": "INA", "Leo Rolly Carnando": "INA",
    "Daniel Marthin": "INA", "Bagas Maulana": "INA", "Fajar Alfian": "INA",
    "Muhammad Rian Ardianto": "INA", "Dejan Ferdinansyah": "INA",
    "Lanny Tria Mayasari": "INA", "Sabar Karyaman Gutama": "INA",
    "Moh Reza Pahlevi Isfahani": "INA",
    # --- Thailand ---
    "Dechapol Puavaranukroh": "THA", "Sapsiree Taerattanachai": "THA",
    "Supissara Pacharamongkol": "THA", "Puttita Supajirakul": "THA",
    "Supak Jomkoh": "THA", "Kittinupong Kedren": "THA",
    "Benyapa Aimsaard": "THA", "Nuntakarn Aimsaard": "THA",
    "Jongkolphan Kititharakul": "THA", "Rawinda Prajongjai": "THA",
    # --- Japan ---
    "Sayaka Hirota": "JPN", "Hiroki Okamura": "JPN", "Yuta Watanabe": "JPN",
    "Arisa Higashino": "JPN", "Takuro Hoki": "JPN", "Yugo Kobayashi": "JPN",
    "Akira Koga": "JPN", "Taichi Saito": "JPN", "Nami Matsuyama": "JPN",
    "Chiharu Shida": "JPN", "Ayako Sakuramoto": "JPN", "Yukiko Takahata": "JPN",
    "Rin Iwanaga": "JPN", "Kie Nakanishi": "JPN",
    # --- Chinese Taipei ---
    "Yang Po Hsuan": "TPE", "Lee Yang": "TPE", "Wang Chi-Lin": "TPE",
    "Lee Jhe-Huei": "TPE", "Yang Ching Tun": "TPE", "Chiu Hsiang Chieh": "TPE",
    "Hu Ling Fang": "TPE", "Lin Bing Wei": "TPE",
    # --- India ---
    "Dhruv Kapila": "IND", "Tanisha Crasto": "IND", "Ashwini Ponnappa": "IND",
    "Satwiksairaj Rankireddy": "IND", "Chirag Shetty": "IND",
    # --- Germany / France / Denmark / GB ---
    "Mark Lamsfuss": "GER", "Isabel Lohau": "GER", "Linda Efler": "GER",
    "Thom Gicquel": "FRA", "Delphine Delrue": "FRA", "William Villeger": "FRA",
    "Mathias Thyrri": "DEN", "Kim Astrup": "DEN", "Anders Skaarup Rasmussen": "DEN",
    "Alexandra Boje": "DEN", "Maiken Fruergaard": "DEN", "Sara Thygesen": "DEN",
    "Julie Macpherson": "SCO", "Alexander Dunn": "SCO", "Adam Hall": "SCO",
    "Lauren Smith": "ENG", "Callum Hemming": "ENG", "Sean Vendy": "ENG",
    "Ben Lane": "ENG", "Estelle Van Leeuwen": "NED", "Ties Van Der Lecq": "NED",
    # --- Hong Kong / others ---
    "Chang Tak Ching": "HKG", "Tang Chun Man": "HKG", "Tse Ying Suet": "HKG",
    "Yeung Pui Lam": "HKG", "Jennie Gai": "USA",
    # --- second wave (most-common unresolved members) ---
    # Indonesia
    "Marcus Fernaldi Gideon": "INA", "Kevin Sanjaya Sukamuljo": "INA",
    "Mohammad Ahsan": "INA", "Hendra Setiawan": "INA", "Greysia Polii": "INA",
    "Praveen Jordan": "INA", "Melati Daeva Oktavianti": "INA", "Hafiz Faizal": "INA",
    "Rinov Rivaldy": "INA", "Pitha Haningtyas Mentari": "INA",
    "Pramudya Kusumawardana": "INA", "Zachariah Josiahno Sumitro": "INA",
    "Hediana Julimarbela": "INA", "Amallia Cahaya Pratiwi": "INA",
    # Malaysia
    "Goh Soon Huat": "MAS", "Lai Shevon Jemie": "MAS", "Ong Yew Sin": "MAS",
    "Teo Ee Yi": "MAS", "Chow Mei Kuan": "MAS", "Lee Meng Yean": "MAS",
    "Goh Liu Ying": "MAS", "Peck Yen Wei": "MAS", "Lai Pei Jing": "MAS",
    # Japan
    "Yuki Fukushima": "JPN", "Mayu Matsumoto": "JPN", "Misaki Matsutomo": "JPN",
    "Rui Hirokami": "JPN", "Yuichi Shimabukuro": "JPN", "Yuki Kaneko": "JPN",
    "Masayuki Morizono": "JPN", "Keiichiro Matsui": "JPN", "Yoshinori Takeuti": "JPN",
    "Jacqueline Funaoka": "JPN",
    # China
    "Guo Xin Wa": "CHN", "Tan Qiang": "CHN", "Liu Xuan Xuan": "CHN",
    # Korea
    "Ko Sung Hyun": "KOR", "Eom Hye Won": "KOR", "Kim Hye Rin": "KOR",
    "Hee Yong Kwon": "KOR",
    # Chinese Taipei
    "Hsu Yin-Hui": "TPE", "Hung En-Tzu": "TPE", "Lu Ching Yao": "TPE",
    # India
    "Venkat Gaurav Prasad": "IND", "Juhi Dewangan": "IND", "M.r.arjun": "IND",
    # Europe
    "Amalie Magelund": "DEN", "Mads Vestergaard": "DEN", "Julie Finne-Ipsen": "DEN",
    "Mai Surrow": "DEN", "Anne Tran": "FRA", "Margot Lambert": "FRA",
    "Marvin Seidel": "GER", "Jones Ralfy Jansen": "GER", "Marcus Ellis": "ENG",
    "Clara Azurmendi": "ESP", "Beatriz Corrales": "ESP", "Debora Jille": "NED",
    "Vladimir Ivanov": "RUS", "Ivan Sozonov": "RUS",
    # North America
    "Josephine Wu": "CAN", "Valeree Sietsema": "USA",
}

# Full country name (data/players.json) -> ISO-3, for the auto country lookup.
_CNAME = {
    "China": "CHN", "Thailand": "THA", "Denmark": "DEN", "France": "FRA",
    "Indonesia": "INA", "Chinese Taipei": "TPE", "Taiwan": "TPE", "Japan": "JPN",
    "South Korea": "KOR", "Korea": "KOR", "India": "IND", "Malaysia": "MAS",
    "Singapore": "SGP", "Hong Kong": "HKG", "Spain": "ESP", "Canada": "CAN",
    "United States": "USA", "Netherlands": "NED", "Ireland": "IRL", "Germany": "GER",
    "Vietnam": "VIE", "Belgium": "BEL", "Scotland": "SCO", "England": "ENG",
}


def clean(raw: str) -> str:
    return re.sub(r"\s*\(\d+\)\s*$", "", (raw or "").strip())


def to_int(x: str) -> int | None:
    x = (x or "").strip()
    try:
        return int(float(x))
    except ValueError:
        return None


def iso_date(d: str) -> str:
    try:
        dd, mm, yy = d.split("/")
        return f"{int(yy):04d}-{int(mm):02d}-{int(dd):02d}"
    except (ValueError, AttributeError):
        return d if re.match(r"\d{4}-", d or "") else ""


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def collect() -> tuple[dict[str, list[tuple]], dict[str, str]]:
    """Returns (app, typ): CSV name -> chronological appearances, and CSV name ->
    'MS'/'WS'. Truncated names (with '..') are KEPT now, so they can be reached by
    a prefix (see history_for) instead of being dropped."""
    app: dict[str, list[tuple]] = defaultdict(list)
    typ: dict[str, str] = {}
    for f in glob.glob(str(HERE / "cleaned_data" / "*Combined*.csv")):
        for r in csv.DictReader(open(f, encoding="utf-8")):
            t = r.get("type")
            if t not in SINGLES:
                continue
            for side in ("winner", "loser"):
                nm = clean(r[f"{side}_name"])
                if not nm:
                    continue
                d = re.search(r"Elo\s+\d+\s*\(([+-]?\d+)\)", r[f"{side}_raw"] or "")
                app[nm].append((
                    iso_date(r["date"]),
                    side == "winner",
                    to_int(r[f"{side}_elo"]),
                    int(d.group(1)) if d else 0,
                    to_int(r[f"{side}_rank"]),
                ))
                typ[nm] = t
    return app, typ


def history_for(key: str, app: dict[str, list[tuple]]) -> list[tuple]:
    """Appearances for a player. Exact CSV name if it exists; otherwise treat the
    key as a name PREFIX and merge every (possibly truncated) row that starts with
    it — so a truncated player like 'Putri Kusuma WAR..' is reachable via a stem
    such as 'Putri Kusuma WAR'. Pick a prefix distinctive enough to hit one player."""
    if key in app:
        return list(app[key])
    stem = key.lower().replace("..", "").strip()
    merged: list[tuple] = []
    for nm, apps in app.items():
        if nm.lower().replace("..", "").strip().startswith(stem):
            merged += apps
    return merged


def flag_for(country: str, unknown: set[str]) -> str:
    f = FLAG.get(country)
    if not f:
        unknown.add(country)
        return "🏳️"  # add the code to FLAG to get a real flag
    return f


def display_name(raw: str) -> str:
    """CSV casing -> clean display: 'SHI Yu Qi' -> 'Shi Yu Qi', keeps initials."""
    out = []
    for w in clean(raw).split():
        if len(w) <= 2 and w.endswith("."):       # initials: 'H.' 'S.'
            out.append(w.upper())
        elif "-" in w:
            out.append("-".join(s.capitalize() for s in w.split("-")))
        else:
            out.append(w.capitalize())
    return " ".join(out)


def pair_display(raw: str) -> str:
    """Canonical doubles/mixed team name: each side title-cased, rejoined ' / '.
    MUST match ingest_tournaments.pair_display so pool names == rating keys."""
    sides = [display_name(s) for s in clean(raw).split("/")]
    return " / ".join(s for s in sides if s)


def collect_pairs() -> tuple[dict[str, list[tuple]], dict[str, str]]:
    """pair name -> chronological appearances, and pair name -> 'MD'/'WD'/'XD'.
    Pairs with any truncated member are skipped (can't be identified reliably)."""
    app: dict[str, list[tuple]] = defaultdict(list)
    typ: dict[str, str] = {}
    for f in glob.glob(str(HERE / "cleaned_data" / "*Combined*.csv")):
        for r in csv.DictReader(open(f, encoding="utf-8")):
            t = r.get("type")
            if t not in DOUBLES:
                continue
            for side in ("winner", "loser"):
                raw = r[f"{side}_name"]
                if ".." in raw:
                    continue
                name = pair_display(raw)
                d = re.search(r"Elo\s+\d+\s*\(([+-]?\d+)\)", r[f"{side}_raw"] or "")
                app[name].append((
                    iso_date(r["date"]),
                    side == "winner",
                    to_int(r[f"{side}_elo"]),
                    int(d.group(1)) if d else 0,
                    to_int(r[f"{side}_rank"]),
                ))
                typ[name] = t
    return app, typ


def pair_country(name: str, lookup: dict[str, str]) -> tuple[str, bool]:
    """(country, same_country_ok) for a pair. Real BWF pairs are SAME-NATION, so a
    pair whose two members resolve to DIFFERENT countries is a data artifact —
    same_country_ok is False and the caller drops it. Otherwise country is the
    agreed (both members same) or the single resolved ISO3, or '' when neither
    member is known (-> neutral flag; trusted as same-country since the source only
    pairs same-nation players and we can't disprove it). Resolution is via the
    member country lookup (DOUBLES_COUNTRY + the singles sources)."""
    resolved = [c for member in name.split(" / ")
                if (c := lookup.get(member.lower()) or lookup.get(norm(member)))]
    if len(resolved) >= 2 and len(set(resolved)) > 1:
        return "", False
    return (resolved[0] if resolved else ""), True


def norm(name: str) -> str:
    """Loose identity key: accent-free, lowercase, letters+digits only — so
    'An Se-young', 'An Se Young' and 'An Seyoung' all collapse to the same id."""
    s = unicodedata.normalize("NFKD", name or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", s.lower())


def core_names() -> set[str]:
    """Lowercased names already hand-listed in src/players.ts (the core roster)."""
    try:
        ts = (HERE.parent / "src" / "players.ts").read_text(encoding="utf-8")
        return {m.lower() for m in re.findall(r"name: '([^']+)'", ts)}
    except OSError:
        return set()


def load_country_lookup() -> dict[str, str]:
    """name (lowercased) -> ISO-3, merged from everything that carries a country:
    this script's NEW table, the existing roster, the Wikipedia rankings, and
    players.json. The hand-kept COUNTRY dict wins over all of them."""
    lk: dict[str, str] = {}

    def add(name: str, country: str, *, force: bool = False) -> None:
        for k in (name.lower(), norm(name)):
            if force or k not in lk:
                lk[k] = country

    for _csv, (display, country, _w) in NEW.items():
        add(display, country)
    for f in ("players.ts", "players.generated.ts"):
        try:
            ts = (HERE.parent / "src" / f).read_text(encoding="utf-8")
            for nm, co in re.findall(r"name: '([^']+)',\s*country: '([^']+)'", ts):
                add(nm, co)
        except OSError:
            pass
    try:
        rk = json.loads((DATA / "bwf_rankings.json").read_text(encoding="utf-8"))
        for div in ("men", "women"):
            for p in rk.get(div, []):
                add(p["name"], p["country"])
    except OSError:
        pass
    try:
        for p in json.loads((DATA / "players.json").read_text(encoding="utf-8")):
            c = _CNAME.get(p.get("country") or "")
            if c:
                add(p["name"], c)
    except OSError:
        pass
    for nm, co in DOUBLES_COUNTRY.items():
        add(nm, co)
    for nm, co in COUNTRY.items():
        add(nm, co, force=True)
    return lk


def list_names() -> None:
    """`python build_roster.py --list [men|women]` — print every singles name in
    the CSVs with its match count, so you can copy the exact key into NEW."""
    app, typ = collect()
    want = next((a for a in sys.argv[1:] if a in ("men", "women", "all")), "all")
    for code, label, key in (("MS", "MEN", "men"), ("WS", "WOMEN", "women")):
        if want not in ("all", key):
            continue
        names = sorted((n for n in app if typ.get(n) == code), key=lambda n: -len(app[n]))
        print(f"=== {label}: {len(names)} names ===")
        for n in names:
            mark = "   << truncated — match by a prefix" if ".." in n else ""
            print(f"{len(app[n]):3}  {n}{mark}")
        print()


def main() -> None:
    if "--list" in sys.argv:
        list_names()
        return

    app, typ = collect()
    rows: list[dict] = []
    missing: list[str] = []
    unknown_flags: set[str] = set()

    # 1) players resolved from CSV match history (real Elo/rank/form)
    for key, (display, country, women) in NEW.items():
        apps = sorted(history_for(key, app), key=lambda a: a[0])
        if not apps:
            missing.append(key)
            continue
        last = apps[-1]
        rows.append({
            "id": slug(display),
            "name": display,
            "country": country,
            "flag": flag_for(country, unknown_flags),
            "rank": last[4] if last[4] else 999,
            "elo": (last[2] or 2000) + last[3],
            "form": [1 if a[1] else 0 for a in apps[-5:]],
            "hand": "L" if display in LEFTIES else "R",
            "height": 178,
            "women": women,
            "discipline": "WS" if women else "MS",
        })

    # 2) fully hand-entered players (never truncated; stats are whatever you set)
    for m in MANUAL:
        women = bool(m.get("women", False))
        rows.append({
            "id": slug(m["name"]),
            "name": m["name"],
            "country": m["country"],
            "flag": flag_for(m["country"], unknown_flags),
            "rank": m.get("rank", 999),
            "elo": m.get("elo", 2000),
            "form": m.get("form", [0, 0, 0, 0, 0]),
            "hand": m.get("hand", "R"),
            "height": m.get("height", 178),
            "women": women,
            "discipline": "WS" if women else "MS",
        })

    # 3) --auto: pull in EVERY other singles player we can identify a country for.
    #    --min N sets the minimum match count (default 12). Truncated names are
    #    skipped here (use NEW with a prefix for those).
    if "--auto" in sys.argv:
        min_matches = 12
        if "--min" in sys.argv:
            i = sys.argv.index("--min")
            if i + 1 < len(sys.argv) and sys.argv[i + 1].isdigit():
                min_matches = int(sys.argv[i + 1])
        lookup = load_country_lookup()
        # already-present identities (normalized), so variant spellings like
        # 'An Se Young' vs 'An Se-young' aren't re-added as duplicates.
        existing = {norm(r["name"]) for r in rows} | {norm(n) for n in core_names()}
        by_name: dict[str, list[tuple]] = defaultdict(list)
        womanly: dict[str, bool] = {}
        for nm, apps in app.items():
            if ".." in nm:
                continue
            d = display_name(nm)
            by_name[d] += apps
            womanly[d] = typ.get(nm) == "WS"
        no_country: list[tuple[int, str]] = []
        for d, apps in by_name.items():
            key = norm(d)
            if len(apps) < min_matches or key in existing:
                continue
            country = lookup.get(d.lower()) or lookup.get(key)
            if not country:
                no_country.append((len(apps), d))
                continue
            apps.sort(key=lambda a: a[0])
            last = apps[-1]
            rows.append({
                "id": slug(d), "name": d, "country": country,
                "flag": flag_for(country, unknown_flags),
                "rank": last[4] if last[4] else 999,
                "elo": (last[2] or 2000) + last[3],
                "form": [1 if a[1] else 0 for a in apps[-5:]],
                "hand": "L" if d in LEFTIES else "R", "height": 178,
                "women": womanly[d], "discipline": "WS" if womanly[d] else "MS",
            })
            existing.add(key)
        if no_country:
            top = sorted(no_country, reverse=True)[:25]
            print(f"   ℹ️  --auto skipped {len(no_country)} players with no known "
                  f"country. Add the ones you want to COUNTRY, e.g.:")
            for cnt, d in top:
                print(f"        \"{d}\": \"\",   # {cnt} matches")

    # 4) doubles/mixed PAIRS as teams (always added; the CSVs now spell pair names
    #    out, so each pair gets a real team Elo/rank/form). Same-nation only — a pair
    #    whose members resolve to different countries is a data artifact and dropped.
    #    Discipline (MD/WD/XD) is the authoritative divider.
    pair_app, pair_typ = collect_pairs()
    pair_lookup = load_country_lookup()
    pair_count = 0
    cross_country = 0
    for name, apps in pair_app.items():
        if len(apps) < MIN_PAIR_MATCHES:
            continue
        country, same_country_ok = pair_country(name, pair_lookup)
        if not same_country_ok:   # members from different nations -> not a real team
            cross_country += 1
            continue
        apps = sorted(apps, key=lambda a: a[0])
        last = apps[-1]
        t = pair_typ[name]
        rows.append({
            "id": slug(name),
            "name": name,
            "country": country,
            "flag": flag_for(country, unknown_flags) if country else "🏳️",
            "rank": last[4] if last[4] else 999,
            "elo": (last[2] or 2000) + last[3],
            "form": [1 if a[1] else 0 for a in apps[-5:]],
            "hand": "R",
            "height": 178,
            "women": t == "WD",          # legacy flag; discipline is authoritative
            "discipline": t,
        })
        pair_count += 1

    # Dedupe by name (first wins) so a MANUAL entry overrides a NEW one cleanly.
    seen: set[str] = set()
    rows = [r for r in rows if not (r["name"] in seen or seen.add(r["name"]))]

    disc_counts = Counter(r["discipline"] for r in rows)
    singles_n = disc_counts["MS"] + disc_counts["WS"]
    pairs_n = disc_counts["MD"] + disc_counts["WD"] + disc_counts["XD"]

    lines = [
        "// AUTO-GENERATED by backend/build_roster.py — do not edit by hand.",
        "// Singles players AND doubles/mixed PAIRS (as teams) mined from the cleaned",
        "// tournament CSVs (real Elo/rank/form from match history). `discipline` is",
        "// MS/WS/MD/WD/XD; nationality is curated/best-effort (CSVs carry no country).",
        "import type { Player } from './players'",
        "",
        "export const GENERATED_PLAYERS: Player[] = [",
    ]
    for r in rows:
        women_field = ", women: true" if r["women"] else ""
        disc_field = f", discipline: '{r['discipline']}'" if r.get("discipline") else ""
        lines.append(
            f"  {{ id: '{r['id']}', name: {r['name']!r}, country: '{r['country']}', "
            f"flag: '{r['flag']}', rank: {r['rank']}, elo: {r['elo']}, "
            f"form: {r['form']}, hand: '{r['hand']}', height: {r['height']}{women_field}{disc_field} }},"
        )
    lines.append("]")
    text = "\n".join(lines) + "\n"
    # Use JS-style single quotes for names too (TS is fine with either).
    text = text.replace('name: "', "name: '").replace('",', "',")
    OUT.write_text(text, encoding="utf-8")

    print(f"📦 wrote {OUT}")
    print(f"   added {len(rows)} entries — {singles_n} singles "
          f"(MS {disc_counts['MS']}, WS {disc_counts['WS']}) + {pairs_n} pairs "
          f"(MD {disc_counts['MD']}, WD {disc_counts['WD']}, XD {disc_counts['XD']})")
    if cross_country:
        print(f"   ⛔ dropped {cross_country} cross-country pair(s) "
              f"(members from different nations — not a real team)")
    if missing:
        print(f"   ⚠️  no CSV history (skipped — try a prefix or use MANUAL): {', '.join(missing)}")
    if unknown_flags:
        print(f"   ⚠️  no flag for country code(s) {', '.join(sorted(unknown_flags))} "
              f"— add them to FLAG at the top of this script.")


if __name__ == "__main__":
    main()
