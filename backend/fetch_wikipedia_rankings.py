"""
🏸 BWF World Ranking fetcher — Wikipedia source (open MediaWiki API, no key).

bwfbadminton.com is Cloudflare-protected and badmintonranks.com IP-bans
automated access, but Wikipedia mirrors the official BWF World Ranking on
https://en.wikipedia.org/wiki/BWF_World_Ranking and exposes it through the
MediaWiki API — which explicitly permits programmatic access, isn't IP-blocked,
and is freely licensed (CC BY-SA, attribution required). That makes it the right
source to keep backend/data/bwf_rankings.json refreshed.

The "Player rankings" section has a current Men's-singles and Women's-singles
table (Rank · Country · Player · Points · Highest peak), updated weekly with an
"as of <date>" caption. We pull both, normalize names to match src/players.ts,
and rewrite bwf_rankings.json (which the backend already serves at GET /rankings).

USAGE
-----
    backend\\venv\\Scripts\\python.exe backend\\fetch_wikipedia_rankings.py
    # options: --top 15   (rows per division)   --dry-run (print, don't write)

Only depends on the Python standard library.
"""

from __future__ import annotations

import argparse
import html as html_lib
import json
import re
import sys
import urllib.parse
import urllib.request
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT_FILE = HERE / "data" / "bwf_rankings.json"

API = "https://en.wikipedia.org/w/api.php"
WIKI_PAGE = "BWF_World_Ranking"
# A descriptive UA is required by Wikimedia's API etiquette.
UA = ("FYP-badminton-predictor/1.0 (UiTM student project; "
      "contact ikhmalhanif60@gmail.com)")

# Wikipedia country names -> IOC/BWF 3-letter codes (frontend maps these to
# flags). Unknown names fall back to the first 3 letters uppercased.
COUNTRY_CODE = {
    "China": "CHN", "Thailand": "THA", "Denmark": "DEN", "France": "FRA",
    "Indonesia": "INA", "Chinese Taipei": "TPE", "Taiwan": "TPE",
    "South Korea": "KOR", "Korea": "KOR", "Japan": "JPN", "India": "IND",
    "Malaysia": "MAS", "Singapore": "SGP", "Hong Kong": "HKG", "Spain": "ESP",
    "Vietnam": "VIE", "Germany": "GER", "Canada": "CAN", "United States": "USA",
    "England": "ENG", "Scotland": "SCO", "Ireland": "IRL", "Netherlands": "NED",
    "Czech Republic": "CZE", "Czechia": "CZE", "Israel": "ISR", "Finland": "FIN",
    "Estonia": "EST", "Belgium": "BEL", "Switzerland": "SUI", "Brazil": "BRA",
    "Australia": "AUS", "Russia": "RUS", "Ukraine": "UKR", "Poland": "POL",
    "Italy": "ITA", "Sweden": "SWE", "Norway": "NOR", "Mexico": "MEX",
    "Macau": "MAC", "Sri Lanka": "SRI", "Philippines": "PHI", "Myanmar": "MYA",
    "Bulgaria": "BUL", "Portugal": "POR", "Austria": "AUT", "Slovakia": "SVK",
    "Turkey": "TUR", "Iran": "IRI", "New Zealand": "NZL", "South Africa": "RSA",
}

# Wikipedia spelling -> the spelling used in src/players.ts, so the leaderboard
# can join ranking rows to roster avatars / hand / Elo. Names not listed here
# pass through unchanged (and the frontend synthesizes a minimal player).
NAME_ALIAS = {
    "Shi Yuqi": "Shi Yu Qi",
    "Chou Tien-chen": "Chou Tien Chen",
    "Li Shifeng": "Li Shi Feng",
    "Lin Chun-yi": "Lin Chun-Yi",
    "Chen Yufei": "Chen Yu Fei",
    "He Bingjiao": "He Bing Jiao",
    "Anthony Sinisuka Ginting": "Anthony Ginting",
    "Carolina Marín": "Carolina Marin",
    "Pusarla Venkata Sindhu": "P. V. Sindhu",
}


def api(params: dict) -> dict:
    url = API + "?" + urllib.parse.urlencode({**params, "format": "json"})
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def find_section(sections: list[dict], title: str) -> int | None:
    """Index of the FIRST section with this exact line (the current-ranking one;
    the same title recurs later under 'timeline'/'highest career rank')."""
    for s in sections:
        if s.get("line", "").strip().lower() == title.lower():
            return int(s["index"])
    return None


def _cells(row_html: str) -> list[str]:
    """Plain-text cells of a table row, tags stripped, order preserved (empties
    kept so column positions stay aligned)."""
    out = []
    for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row_html, re.S):
        text = re.sub(r"<[^>]+>", "", c)
        text = (text.replace("&#160;", " ").replace("&nbsp;", " ")
                    .replace("&#91;", "[").replace("&#93;", "]"))
        out.append(" ".join(text.split()).strip())
    return out


_POINTS_RE = re.compile(r"^\d{1,3}(?:,\d{3})+$")  # e.g. 108,905 — uniquely points


def parse_section(section_html: str, top: int) -> tuple[list[dict], str]:
    """Parse one singles ranking table -> ([{rank,name,country,points}], as_of).

    Column order is Rank · [movement] · Country · Player · Points · Peak…, but a
    movement arrow column may or may not be present, so we anchor on the points
    cell (the only comma-grouped number) and read player/country just left of it.
    """
    m = re.search(r"<table[^>]*wikitable[^>]*>.*?</table>", section_html, re.S)
    if not m:
        return [], ""
    table = m.group(0)

    as_of = ""
    # The date renders as "as of 26&#160;May&#160;2026" (nbsp-separated, behind a
    # <br/>), so strip tags and decode entities before matching.
    flat = html_lib.unescape(re.sub(r"<[^>]+>", " ", table))
    cap = re.search(r"as of\s+(\d{1,2}\s+[A-Za-z]+\s+\d{4})", flat)
    if cap:
        try:
            as_of = datetime.strptime(cap.group(1), "%d %B %Y").date().isoformat()
        except ValueError:
            pass

    rows: list[dict] = []
    for row in re.findall(r"<tr.*?</tr>", table, re.S):
        cells = _cells(row)
        if not cells or not cells[0].isdigit():
            continue  # header / sub-header / non-data row
        pts_idx = next((i for i, c in enumerate(cells) if _POINTS_RE.match(c)), None)
        if pts_idx is None or pts_idx < 2:
            continue
        name = cells[pts_idx - 1]
        country = cells[pts_idx - 2]
        rows.append({
            "rank": int(cells[0]),
            "name": NAME_ALIAS.get(name, name),
            "country": COUNTRY_CODE.get(country, re.sub(r"[^A-Za-z]", "", country)[:3].upper()),
            "points": int(cells[pts_idx].replace(",", "")),
        })
        if len(rows) >= top:
            break
    return rows, as_of


def _member_display(name: str) -> str:
    """Normalize a doubles member's Wikipedia spelling toward the rest of the UI:
    hyphens -> spaces, each word capitalized. 'Kim Won-ho' -> 'Kim Won Ho'. This
    also makes most pairs line up with the CSV pool's space-separated names; exact
    alignment is order-/spacing-independent on the frontend (norm() set-key)."""
    name = NAME_ALIAS.get(name, name)
    return " ".join(w.capitalize() for w in name.replace("-", " ").replace("–", " ").split())


def parse_doubles_section(section_html: str, top: int) -> tuple[list[dict], str]:
    """Parse one DOUBLES ranking table -> ([{rank,name,country,points}], as_of),
    where name is the pair 'Player 1 / Player 2'. Each doubles row is
    Rank · [move] · Country · Player1 · Points · peak1 · date1 · peak2 · Player2 · date2,
    so we anchor on the points cell (player1 just left of it, country two left) and
    take Player2 as the first name-like cell after points (skipping peak#/date cells)."""
    m = re.search(r"<table[^>]*wikitable[^>]*>.*?</table>", section_html, re.S)
    if not m:
        return [], ""
    table = m.group(0)

    as_of = ""
    flat = html_lib.unescape(re.sub(r"<[^>]+>", " ", table))
    cap = re.search(r"as of\s+(\d{1,2}\s+[A-Za-z]+\s+\d{4})", flat)
    if cap:
        try:
            as_of = datetime.strptime(cap.group(1), "%d %B %Y").date().isoformat()
        except ValueError:
            pass

    rows: list[dict] = []
    for row in re.findall(r"<tr.*?</tr>", table, re.S):
        cells = _cells(row)
        if not cells or not cells[0].isdigit():
            continue
        pts_idx = next((i for i, c in enumerate(cells) if _POINTS_RE.match(c)), None)
        if pts_idx is None or pts_idx < 2:
            continue
        p1 = cells[pts_idx - 1]
        country = cells[pts_idx - 2]
        # Player 2 = first cell after points that has letters and no digits
        # (peak-rank cells are pure digits, peak-date cells contain digits).
        p2 = next((c for c in cells[pts_idx + 1:]
                   if re.search(r"[A-Za-z]", c) and not re.search(r"\d", c)), "")
        if not p1 or not p2:
            continue
        rows.append({
            "rank": int(cells[0]),
            "name": f"{_member_display(p1)} / {_member_display(p2)}",
            "country": COUNTRY_CODE.get(country, re.sub(r"[^A-Za-z]", "", country)[:3].upper()),
            "points": int(cells[pts_idx].replace(",", "")),
        })
        if len(rows) >= top:
            break
    return rows, as_of


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass

    ap = argparse.ArgumentParser(description="Refresh bwf_rankings.json from Wikipedia.")
    ap.add_argument("--top", type=int, default=15, help="rows per division (default 15)")
    ap.add_argument("--dry-run", action="store_true", help="print, don't write the file")
    args = ap.parse_args()

    print(f"🌐 fetching {WIKI_PAGE} from the MediaWiki API…")
    sections = api({"action": "parse", "page": WIKI_PAGE, "prop": "sections"})["parse"]["sections"]

    # (key, Wikipedia section title, parser). Singles + the three doubles draws.
    divisions = [
        ("men", "Men's singles", parse_section),
        ("women", "Women's singles", parse_section),
        ("md", "Men's doubles", parse_doubles_section),
        ("wd", "Women's doubles", parse_doubles_section),
        ("xd", "Mixed doubles", parse_doubles_section),
    ]
    result: dict[str, list[dict]] = {}
    as_of = ""
    for div, title, parser in divisions:
        idx = find_section(sections, title)
        if idx is None:
            print(f"  ⚠️  section {title!r} not found; skipping {div}")
            result[div] = []
            continue
        html = api({"action": "parse", "page": WIKI_PAGE, "prop": "text",
                    "section": idx})["parse"]["text"]["*"]
        rows, div_asof = parser(html, args.top)
        as_of = as_of or div_asof
        result[div] = rows
        head = ", ".join(f"{r['rank']}.{r['name']}" for r in rows[:2])
        print(f"  ✓ {div}: {len(rows)} entries (as of {div_asof or '?'}) — {head}…")

    if not any(result.values()):
        raise SystemExit("❌ parsed 0 entries — the page layout may have changed.")

    out = {
        "_readme": ("Official BWF World Ranking (all 5 disciplines), parsed from "
                    "https://en.wikipedia.org/wiki/BWF_World_Ranking via the "
                    "MediaWiki API. Refresh with: python backend/"
                    "fetch_wikipedia_rankings.py . Singles names normalized to match "
                    "src/players.ts; doubles entries are pairs ('A / B'). Served by "
                    "the backend at GET /rankings."),
        "as_of": as_of or date.today().isoformat(),
        "source": "en.wikipedia.org",
        "men": result.get("men", []),
        "women": result.get("women", []),
        "md": result.get("md", []),
        "wd": result.get("wd", []),
        "xd": result.get("xd", []),
    }

    if args.dry_run:
        print("\n--- dry run, would write: ---")
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return

    OUT_FILE.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n📦 wrote {OUT_FILE}  (men={len(out['men'])}, women={len(out['women'])}, "
          f"md={len(out['md'])}, wd={len(out['wd'])}, xd={len(out['xd'])}, "
          f"as of {out['as_of']})")
    print("↻ Restart the backend (or your `npm run dev`) so /rankings reloads it.")


if __name__ == "__main__":
    main()
