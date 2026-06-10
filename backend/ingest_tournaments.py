"""
🏸 Tournament-CSV ingestion (badmintonranks.com exports).

Turns the `cleaned_data/*Combined*.csv` files (one per tournament, with the
non-truncated player names) into two clean artifacts the rest of the app consumes:

    data/tournament_matches.csv   one row per match (ALL disciplines: MS/WS/MD/WD/XD),
                                  with each side's REAL pre-match rank + Elo (the
                                  training set; `type` is itself a feature)
    data/player_ratings.json      current real Elo + rank + record + form, for the
                                  singles roster players AND each doubles/mixed PAIR
                                  treated as one team (powers /players, /predict and
                                  the UI's real-Elo display). Each entry carries a
                                  `type` (MS/WS/MD/WD/XD).

Why these CSVs beat the old SportsAPIPro set:
  * ~1,750 singles matches (2021-2026) vs ~990, with full names where available.
  * The `winner_elo`/`loser_elo` columns are the players' REAL Elo *going into*
    each match (the `(+46)` in the raw string is the change applied after). So the
    Elo is both real (badmintonranks scale) AND already point-in-time — no replay,
    no leakage. `winner_rank`/`loser_rank` are likewise the pre-match world rank.

Source note: these are static CSVs exported by the project owner; we read them
locally and attribute badmintonranks.com — we do not fetch that site live.

Run:  cd backend && python ingest_tournaments.py
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
DATA_DIR = HERE / "data"
SINGLES = {"MS", "WS"}
DOUBLES = {"MD", "WD", "XD"}
ALL_TYPES = SINGLES | DOUBLES
# A doubles/mixed PAIR needs at least this many matches to earn a team rating
# (and to appear in the frontend pool — build_roster.py uses the same cutoff, so
# the pair display names line up and /predict lookups resolve).
MIN_PAIR_MATCHES = 4

# Roster the frontend can pick (mirrors src/players.ts). player_ratings.json is
# keyed by these canonical names so the UI/API can look ratings up by exact name.
ROSTER = [
    "Viktor Axelsen", "Kunlavut Vitidsarn", "Anders Antonsen", "Shi Yu Qi",
    "Jonatan Christie", "Anthony Ginting", "Loh Kean Yew", "Lee Zii Jia",
    "Lee Cheuk Yiu", "Chou Tien Chen", "Kodai Naraoka", "Prannoy H. S.",
    "Lakshya Sen", "Toma Junior Popov", "Kenta Nishimoto", "Christo Popov",
    "Li Shi Feng", "Lin Chun-Yi", "An Se-young", "Chen Yu Fei", "Akane Yamaguchi",
    "Tai Tzu-ying", "Carolina Marin", "P. V. Sindhu", "He Bing Jiao",
    "Pornpawee Chochuwong", "Wang Zhiyi", "Han Yue", "Putri Kusuma Wardani",
    "Ratchanok Intanon",
]
# A few names the dataset spells/spaces differently enough that token overlap fails.
# Map roster name -> the token set to match dataset names against.
ALIASES: dict[str, set[str]] = {
    "Wang Zhiyi": {"wang", "zhi", "yi"},
    "P. V. Sindhu": {"pusarla", "sindhu"},  # dataset spells her "PUSARLA V. Sindhu"
    "Anthony Ginting": {"anthony", "ginting"},
    "Pornpawee Chochuwong": {"pornpawee", "chochuwong"},
}


def tokens(name: str) -> set[str]:
    """Accent-stripped, punctuation-free, lowercased word tokens (drops the
    trailing seed marker like '(2)'). Order-independent for name matching."""
    name = unicodedata.normalize("NFKD", name or "")
    name = "".join(c for c in name if not unicodedata.combining(c))
    name = re.sub(r"\(\d+\)", "", name)
    for ch in ",./-_":
        name = name.replace(ch, " ")
    return {t for t in name.lower().split() if t}


def clean_name(raw: str) -> str:
    """Display name: drop the trailing seed marker, collapse whitespace."""
    return re.sub(r"\s*\(\d+\)\s*$", "", (raw or "").strip())


def display_name(raw: str) -> str:
    """CSV casing -> clean display per person: 'SHI Yu Qi' -> 'Shi Yu Qi', keeps
    initials like 'H.'. Mirrors build_roster.display_name so the two stay in sync."""
    out = []
    for w in clean_name(raw).split():
        if len(w) <= 2 and w.endswith("."):
            out.append(w.upper())
        elif "-" in w:
            out.append("-".join(s.capitalize() for s in w.split("-")))
        else:
            out.append(w.capitalize())
    return " ".join(out)


def pair_display(raw: str) -> str:
    """Canonical team name for a doubles/mixed pair: each side title-cased and
    rejoined with ' / ' -> 'Kim Won Ho / Seo Seung Jae'. MUST match the identical
    function in build_roster.py so the pool names and rating keys line up."""
    sides = [display_name(s) for s in clean_name(raw).split("/")]
    return " / ".join(s for s in sides if s)


def to_int(x: str) -> int | None:
    """Parse '1', '1.0', '144' -> int; blank/garbage -> None."""
    x = (x or "").strip()
    if not x:
        return None
    try:
        return int(float(x))
    except ValueError:
        return None


def iso_date(d: str) -> str:
    """'8/3/2026' (d/m/yyyy) -> '2026-03-08'. Bad input -> '' (sorts first)."""
    try:
        dd, mm, yy = d.split("/")
        return f"{int(yy):04d}-{int(mm):02d}-{int(dd):02d}"
    except (ValueError, AttributeError):
        return ""


def parse_delta(raw: str) -> int:
    """Elo change embedded in the raw cell, e.g. 'Elo 2584 (+46)' -> 46."""
    m = re.search(r"Elo\s+\d+\s*\(([+-]?\d+)\)", raw or "")
    return int(m.group(1)) if m else 0


def load_matches() -> list[dict]:
    """Every match (all 5 disciplines) across the combined cleaned CSVs, parsed +
    deduped. For doubles/mixed, winner_name/loser_name are the PAIR strings."""
    out: list[dict] = []
    seen: set[tuple] = set()
    for f in sorted(glob.glob(str(HERE / "cleaned_data" / "*Combined*.csv"))):
        for r in csv.DictReader(open(f, encoding="utf-8")):
            if r.get("type") not in ALL_TYPES:
                continue
            w_elo, l_elo = to_int(r["winner_elo"]), to_int(r["loser_elo"])
            w_rank, l_rank = to_int(r["winner_rank"]), to_int(r["loser_rank"])
            if w_elo is None or l_elo is None:
                continue  # can't build elo_diff without both ratings
            wname, lname = clean_name(r["winner_name"]), clean_name(r["loser_name"])
            date = iso_date(r["date"])
            key = (date, r["type"], wname, lname, r.get("score", ""))
            if key in seen:
                continue
            seen.add(key)
            out.append({
                "date": date,
                "tournament": r.get("tournament_name", ""),
                "round": r.get("round", ""),
                "type": r["type"],
                "winner_name": wname,
                "winner_rank": w_rank,
                "winner_elo": w_elo,
                "winner_delta": parse_delta(r["winner_raw"]),
                "loser_name": lname,
                "loser_rank": l_rank,
                "loser_elo": l_elo,
                "loser_delta": parse_delta(r["loser_raw"]),
            })
    out.sort(key=lambda m: (m["date"], m["tournament"]))
    return out


def write_matches(matches: list[dict]) -> None:
    cols = ["date", "tournament", "round", "type", "winner_name", "winner_rank",
            "winner_elo", "loser_name", "loser_rank", "loser_elo"]
    with (DATA_DIR / "tournament_matches.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(matches)


def build_ratings(matches: list[dict]) -> dict[str, dict]:
    """Resolve each roster player to their appearances and derive current rating.

    Identity uses only NON-truncated names (truncated '..' rows can't be joined
    reliably). Current Elo = latest match's pre-match Elo + that match's delta
    (i.e. the rating AFTER their most recent match). Rank = latest pre-match rank."""
    # Index every non-truncated SINGLES appearance by token set.
    appearances: list[dict] = []
    for m in matches:
        if m["type"] not in SINGLES:
            continue
        for side in ("winner", "loser"):
            nm = m[f"{side}_name"]
            if ".." in nm:
                continue
            appearances.append({
                "name": nm, "toks": tokens(nm), "date": m["date"], "type": m["type"],
                "won": side == "winner", "elo": m[f"{side}_elo"],
                "delta": m[f"{side}_delta"], "rank": m[f"{side}_rank"],
            })

    ratings: dict[str, dict] = {}
    for roster_name in ROSTER:
        want = ALIASES.get(roster_name, tokens(roster_name))
        mine = [a for a in appearances
                if a["toks"] == want
                or (want and (want <= a["toks"] or a["toks"] <= want)
                    and len(want & a["toks"]) >= 2)]
        if not mine:
            continue
        mine.sort(key=lambda a: a["date"])
        last = mine[-1]
        wins = sum(1 for a in mine if a["won"])
        ratings[roster_name] = {
            "name": roster_name,
            "type": last["type"],                  # MS or WS
            "elo": last["elo"] + last["delta"],   # rating after their latest match
            "rank": last["rank"],
            "wins": wins,
            "losses": len(mine) - wins,
            "played": len(mine),
            "form": [1 if a["won"] else 0 for a in mine[-5:]],
            "as_of": last["date"],
        }
    return ratings


def build_pair_ratings(matches: list[dict]) -> dict[str, dict]:
    """Rate each doubles/mixed PAIR as one team (pairs-as-teams). Identity is the
    canonical `pair_display` name (so it matches build_roster.py and the frontend).
    Only pairs with no truncated member and >= MIN_PAIR_MATCHES matches are kept,
    and only SAME-NATION pairs (a pair whose members resolve to different countries
    is a data artifact — dropped, to stay aligned with the frontend pool). Current
    Elo/rank/form derive from the team's latest match — same maths as the singles
    ratings above, just keyed by the pair instead of one player."""
    import build_roster  # sibling script: reuse its member->country map + same-nation
    lookup = build_roster.load_country_lookup()  # check, so ratings == the pool set
    appearances: dict[str, list[dict]] = defaultdict(list)
    for m in matches:
        if m["type"] not in DOUBLES:
            continue
        for side in ("winner", "loser"):
            raw = m[f"{side}_name"]
            if ".." in raw:
                continue  # a truncated member -> can't identify the pair reliably
            appearances[pair_display(raw)].append({
                "date": m["date"], "type": m["type"], "won": side == "winner",
                "elo": m[f"{side}_elo"], "delta": m[f"{side}_delta"],
                "rank": m[f"{side}_rank"],
            })

    ratings: dict[str, dict] = {}
    for name, apps in appearances.items():
        if len(apps) < MIN_PAIR_MATCHES:
            continue
        if not build_roster.pair_country(name, lookup)[1]:   # cross-country -> drop
            continue
        apps.sort(key=lambda a: a["date"])
        last = apps[-1]
        wins = sum(1 for a in apps if a["won"])
        ratings[name] = {
            "name": name,
            "type": last["type"],                  # MD / WD / XD
            "elo": last["elo"] + last["delta"],
            "rank": last["rank"],
            "wins": wins,
            "losses": len(apps) - wins,
            "played": len(apps),
            "form": [1 if a["won"] else 0 for a in apps[-5:]],
            "as_of": last["date"],
        }
    return ratings


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    matches = load_matches()
    write_matches(matches)

    singles_ratings = build_ratings(matches)
    pair_ratings = build_pair_ratings(matches)
    combined = list(singles_ratings.values()) + list(pair_ratings.values())
    (DATA_DIR / "player_ratings.json").write_text(
        json.dumps(combined, indent=2, ensure_ascii=False),
        encoding="utf-8")

    seasons = [m["date"][:4] for m in matches if m["date"]]
    span = f"{min(seasons)}-{max(seasons)}" if seasons else "n/a"
    by_type = Counter(m["type"] for m in matches)
    mix = ", ".join(f"{t} {by_type[t]}" for t in ("MS", "WS", "MD", "WD", "XD") if by_type[t])
    print(f"📦 {len(matches)} matches ({span}; {mix}) -> data/tournament_matches.csv")
    print(f"📦 {len(singles_ratings)}/{len(ROSTER)} singles roster players + "
          f"{len(pair_ratings)} doubles/mixed pairs rated -> data/player_ratings.json")
    pair_mix = Counter(r["type"] for r in pair_ratings.values())
    print(f"   pairs by discipline: "
          f"{', '.join(f'{t} {pair_mix[t]}' for t in ('MD', 'WD', 'XD') if pair_mix[t])}")
    missing = [n for n in ROSTER if n not in singles_ratings]
    if missing:
        print(f"   (unresolved singles -> 'Unrated' in UI: {', '.join(missing)})")


if __name__ == "__main__":
    main()
