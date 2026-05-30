"""
🏸 SportsAPIPro badminton data ingestion.

Pulls real BWF rankings + match history from the SportsAPIPro Badminton V2 API
and caches everything locally, so the predictor can stop relying on the demo
ranks/Elo hardcoded in `src/players.ts`.

Designed around the FREE plan limit: 100 requests/day, SHARED across all sports.
Safeguards baked in so a single run can't blow your quota:
  - Every response is cached to disk (re-runs read cache for free, fully resumable).
  - A request budget caps how many NEW network calls a run may make.
  - Rate-limit response headers are honoured; a 429 or remaining<=0 stops cleanly.

USAGE
-----
1. Get a free key at https://sportsapipro.com/register and set it:
       PowerShell:  $env:SPORTSAPIPRO_KEY = "your_key_here"
       bash:        export SPORTSAPIPRO_KEY="your_key_here"

2. Verify the free key works and SEE the real JSON shapes (costs ~3 requests):
       python ingest_data.py probe --name "Viktor Axelsen"

3. Run the full ingestion (resumable; safe to re-run across days):
       python ingest_data.py run --pages 1 --budget 90

Outputs land in  backend/data/  :
   data/raw/...        cached raw API responses (gitignored)
   data/players.json   resolved roster: real rank, country, hand, computed Elo
   data/matches.csv    flat match history, ready to build a training set

Only depends on the Python standard library (no pip install needed).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
BASE_URL = "https://v2.badminton.sportsapipro.com"
API_KEY_ENV = "SPORTSAPIPRO_KEY"

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE / "data"
RAW_DIR = DATA_DIR / "raw"

# Seed names taken from src/players.ts. The API needs a player :id, so we
# resolve each name -> id via /api/search, then cache the mapping.
SEED_PLAYERS: list[str] = [
    # Men's singles
    "Viktor Axelsen", "Kunlavut Vitidsarn", "Anders Antonsen", "Shi Yu Qi",
    "Jonatan Christie", "Anthony Ginting", "Loh Kean Yew", "Lee Zii Jia",
    "Lee Cheuk Yiu", "Chou Tien Chen", "Kodai Naraoka", "Prannoy H. S.",
    "Lakshya Sen", "Toma Junior Popov", "Kenta Nishimoto",
    # Women's singles
    "An Se-young", "Chen Yu Fei", "Akane Yamaguchi", "Tai Tzu-ying",
    "Carolina Marin", "P. V. Sindhu", "He Bing Jiao", "Pornpawee Chochuwong",
]


def load_dotenv() -> None:
    """Load KEY=VALUE pairs from backend/.env (and project-root .env) into the
    environment, without adding a python-dotenv dependency. Real environment
    variables already set take precedence over the file."""
    for env_file in (HERE / ".env", HERE.parent / ".env"):
        if not env_file.exists():
            continue
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


class BudgetExhausted(Exception):
    """Raised when the run hits its request budget or the API rate limit."""


class NotFound(Exception):
    """Raised on a 404 — resource/page has no data; caller should skip it."""


# --------------------------------------------------------------------------- #
# Quota-aware HTTP client
# --------------------------------------------------------------------------- #
class Client:
    def __init__(self, api_key: str, budget: int):
        self.api_key = api_key
        self.budget = budget          # max NEW network calls this run
        self.spent = 0                # network calls actually made
        self.cache_hits = 0
        self.remaining: int | None = None  # from x-ratelimit-remaining header

    def _cache_path(self, path: str, params: dict | None) -> Path:
        # Build a filesystem-safe key from the endpoint + sorted params.
        key = path.strip("/")
        if params:
            qs = "&".join(f"{k}={params[k]}" for k in sorted(params))
            key = f"{key}__{qs}"
        safe = "".join(c if c.isalnum() or c in "-_=&." else "_" for c in key)
        return RAW_DIR / f"{safe}.json"

    def get(self, path: str, params: dict | None = None) -> Any:
        """GET a path, using the on-disk cache first. Counts toward budget only
        when an actual network request is made."""
        cache_file = self._cache_path(path, params)
        if cache_file.exists():
            self.cache_hits += 1
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            if cached is None:  # cached 404 sentinel -> still "no data"
                raise NotFound(path)
            return cached

        if self.spent >= self.budget:
            raise BudgetExhausted(
                f"request budget of {self.budget} reached "
                f"(spent={self.spent}). Re-run later to resume from cache."
            )
        if self.remaining is not None and self.remaining <= 0:
            raise BudgetExhausted("API daily quota exhausted (remaining=0).")

        url = BASE_URL + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        # SportsAPIPro sits behind Cloudflare, which blocks the default
        # "Python-urllib" user-agent (error 1010). Send a normal browser UA so
        # the request reaches the API; the x-api-key header still does the auth.
        req = urllib.request.Request(url, headers={
            "x-api-key": self.api_key,
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/124.0.0.0 Safari/537.36"),
            "Accept": "application/json",
        })

        # Retry transient network errors (read timeouts, dropped connections)
        # a few times before giving up — a single blip shouldn't kill the run.
        body = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    self.spent += 1
                    self._read_rate_headers(resp.headers)
                    body = resp.read().decode("utf-8")
                break
            except urllib.error.HTTPError as e:  # definitive status — don't retry
                self.spent += 1
                self._read_rate_headers(e.headers)
                if e.code == 401:
                    raise SystemExit(
                        "❌ 401 Unauthorized — check that SPORTSAPIPRO_KEY is set "
                        "and valid."
                    )
                if e.code == 429:
                    raise BudgetExhausted("429 Too Many Requests — daily quota hit.")
                if e.code == 404:
                    # No data here. Cache an empty sentinel so a resume doesn't
                    # re-spend quota re-discovering the same 404.
                    cache_file.parent.mkdir(parents=True, exist_ok=True)
                    cache_file.write_text(json.dumps(None), encoding="utf-8")
                    raise NotFound(path) from None
                if e.code in (500, 502, 503, 504):
                    # Transient upstream error — retry, but never cache it.
                    if attempt < 2:
                        print(f"    … upstream {e.code}; retrying ({attempt + 1}/2)")
                        time.sleep(2 * (attempt + 1))
                        continue
                    raise NotFound(path) from None  # give up on this page, skip
                detail = e.read().decode("utf-8", "replace")[:300]
                raise RuntimeError(f"HTTP {e.code} for {path}: {detail}") from None
            except (TimeoutError, urllib.error.URLError, ConnectionError) as e:
                if attempt < 2:
                    print(f"    … network hiccup ({e}); retrying ({attempt + 1}/2)")
                    time.sleep(2 * (attempt + 1))
                    continue
                raise BudgetExhausted(
                    f"network error after retries: {e}. Re-run to resume from "
                    "cache (already-fetched players cost nothing)."
                ) from None

        data = json.loads(body)
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return data

    def _read_rate_headers(self, headers) -> None:
        for name in ("x-ratelimit-remaining", "ratelimit-remaining",
                     "X-RateLimit-Remaining"):
            val = headers.get(name)
            if val is not None:
                try:
                    self.remaining = int(val)
                except ValueError:
                    pass
                break

    def report(self) -> str:
        rem = "?" if self.remaining is None else self.remaining
        return (f"network calls this run: {self.spent} | cache hits: "
                f"{self.cache_hits} | quota remaining (API): {rem}")


# --------------------------------------------------------------------------- #
# Defensive parsers — exact JSON shapes aren't documented, so we search for the
# fields we need rather than assuming a structure. `probe` dumps raw JSON so you
# can tighten these if the live shapes differ.
# --------------------------------------------------------------------------- #
def _walk(obj: Any) -> Iterable[Any]:
    """Yield every dict found anywhere in a nested JSON structure."""
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v)


def _first_key(d: dict, *candidates: str) -> Any:
    """Return the first present, non-empty value among case-insensitive keys."""
    lowered = {k.lower(): v for k, v in d.items()}
    for c in candidates:
        v = lowered.get(c.lower())
        if v not in (None, "", []):
            return v
    return None


def _tokens(name: str) -> set[str]:
    """Normalize a name to an order-independent set of word tokens: strip
    accents, drop punctuation (commas/hyphens/periods), lowercase, split.

    Handles the API's varied formats for the same person, e.g.
    'An Se-young' / 'Se Young An.' / 'Tai, Tzu Ying' / 'Marín, Carolina'."""
    decomposed = unicodedata.normalize("NFKD", name)
    ascii_name = "".join(c for c in decomposed if not unicodedata.combining(c))
    for ch in ",.-_/":
        ascii_name = ascii_name.replace(ch, " ")
    return {t for t in ascii_name.lower().split() if t}


def extract_player_entity(search_json: Any, wanted_name: str) -> dict | None:
    """Pick the best-matching player/team entity from a /api/search response.

    Search shape: data.results[].entity = {id, name, slug, gender, country, ...}.
    Returns the entity dict so callers can read id + country + gender in one call
    (no extra request needed). Matches on token SETS, so word order, commas, and
    accents don't matter."""
    target = _tokens(wanted_name)
    best: tuple[int, dict] | None = None  # (score, entity)
    for node in _walk(search_json):
        if not isinstance(node, dict):
            continue
        # An entity is a badminton player/team: has a numeric id, a name, and a
        # gender field (distinguishes it from nested sport/country/tournament).
        ent_id = node.get("id")
        name = node.get("name")
        if not (isinstance(ent_id, int) and isinstance(name, str)
                and "gender" in node):
            continue
        cand = _tokens(name)
        shared = target & cand
        if cand == target:
            score = 3
        elif target and (target <= cand or cand <= target) and min(
                len(target), len(cand)) >= 2:
            score = 2
        elif len(shared) >= 2:
            score = 1
        else:
            continue
        if best is None or score > best[0]:
            best = (score, node)
    return best[1] if best else None


def extract_player_id(search_json: Any, wanted_name: str) -> str | None:
    """Convenience wrapper: just the id of the best entity match (used by probe)."""
    ent = extract_player_entity(search_json, wanted_name)
    return str(ent["id"]) if ent else None


_DISCIPLINES = {"MS": "MS", "WS": "WS", "MD": "MD", "WD": "WD", "XD": "XD"}


def _discipline(tournament: str) -> str:
    """Tournament names carry the discipline as a suffix, e.g.
    'European Championships 2024, MS' -> 'MS'."""
    tail = tournament.rsplit(",", 1)[-1].strip().upper()
    return _DISCIPLINES.get(tail, "")


def extract_matches(events_json: Any, player_name: str, player_id: int) -> list[dict]:
    """Pull one row per FINISHED match from a /api/teams/:id/events page.

    Tuned to the live SofaScore-style shape: events at data.events[], each with
    homeTeam/awayTeam (.name, .id), winnerCode (1=home,2=away), status.type,
    homeScore/awayScore (.current = sets, .period1/2/3 = points), startTimestamp.
    Each row carries the match `event_id` so duplicates (the same match seen from
    both players' histories) can be deduped before computing Elo.

    `is_home` is decided by team id, not name: the API reorders/abbreviates names
    ('Se Young An.', 'Axelsen V.'), so id comparison is the only reliable test."""
    rows: list[dict] = []
    for node in _walk(events_json):
        home = node.get("homeTeam") if isinstance(node, dict) else None
        away = node.get("awayTeam") if isinstance(node, dict) else None
        if not (isinstance(home, dict) and isinstance(away, dict)):
            continue

        status = node.get("status") or {}
        if isinstance(status, dict) and status.get("type") not in ("finished", None):
            continue  # skip scheduled / inprogress / canceled / walkover

        hn = _first_key(home, "name", "shortName")
        an = _first_key(away, "name", "shortName")
        if not (isinstance(hn, str) and isinstance(an, str)):
            continue

        winner_code = node.get("winnerCode")
        if winner_code not in (1, 2):
            continue  # no decided winner -> useless for training/Elo

        # Decide which side is our player. The /api/search entity id does NOT
        # always equal the event's team id, so comparing ids alone mislabels
        # ~a third of matches — it tags the player's own side as the opponent,
        # producing bogus "player vs themselves" rows. Use the id only when
        # exactly one side matches; otherwise fall back to name-token overlap
        # with the seed name (robust to abbreviations like "Vitidsarn K.").
        pid_toks = _tokens(player_name)
        home_id = home.get("id") == player_id
        away_id = away.get("id") == player_id
        if home_id != away_id:
            is_home = home_id
        else:
            h_ov = len(_tokens(hn) & pid_toks)
            a_ov = len(_tokens(an) & pid_toks)
            if h_ov == a_ov:
                continue  # can't tell which side is our player -> skip the row
            is_home = h_ov > a_ov
        opponent = an if is_home else hn
        opp_team = away if is_home else home
        won = (winner_code == 1) if is_home else (winner_code == 2)

        hs = node.get("homeScore") or {}
        as_ = node.get("awayScore") or {}
        sets_for = (hs if is_home else as_).get("current")
        sets_against = (as_ if is_home else hs).get("current")

        ts = node.get("startTimestamp")
        when = ""
        if isinstance(ts, (int, float)):
            when = datetime.fromtimestamp(int(ts), timezone.utc).date().isoformat()

        tnode = node.get("tournament") or {}
        tournament = (tnode.get("name") if isinstance(tnode, dict) else "") or ""

        rows.append({
            "event_id": node.get("id") or node.get("customId"),
            "date": when,
            "tournament": str(tournament),
            "discipline": _discipline(str(tournament)),
            "player": player_name,
            "player_id": player_id,
            "opponent": str(opponent),
            "opponent_id": opp_team.get("id") if isinstance(opp_team, dict) else None,
            "sets_for": sets_for,
            "sets_against": sets_against,
            "won": won,
        })
    return rows


# --------------------------------------------------------------------------- #
# Elo — computed offline from cached match history (costs zero requests).
# --------------------------------------------------------------------------- #
def compute_elo(matches: list[dict], k: float = 32.0, base: float = 1500.0
                ) -> dict[int, float]:
    """Standard Elo over chronologically sorted, decided matches, keyed by TEAM
    ID (returns {team_id: rating}).

    Keying by id (not name) matters: the same person appears under different
    name strings ('Viktor Axelsen' as a seed, 'Axelsen V.' as an opponent), and
    name-keying would split one player into several phantom ratings.
    Dedupes by event_id first, since each match shows up in both players' pages."""
    ratings: dict[int, float] = {}
    seen: set = set()
    decided: list[dict] = []
    for m in matches:
        if not (isinstance(m["won"], bool)
                and m.get("player_id") is not None
                and m.get("opponent_id") is not None):
            continue
        eid = m.get("event_id")
        if eid is not None:
            if eid in seen:
                continue
            seen.add(eid)
        decided.append(m)
    decided.sort(key=lambda m: m["date"] or "")
    for m in decided:
        a, b = m["player_id"], m["opponent_id"]
        ra = ratings.setdefault(a, base)
        rb = ratings.setdefault(b, base)
        ea = 1.0 / (1.0 + 10 ** ((rb - ra) / 400.0))
        sa = 1.0 if m["won"] else 0.0
        ratings[a] = ra + k * (sa - ea)
        ratings[b] = rb + k * ((1.0 - sa) - (1.0 - ea))
    return {tid: round(r) for tid, r in ratings.items()}


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
def cmd_probe(client: Client, name: str) -> None:
    """Cheap end-to-end check (~3 requests): search -> profile -> 1 history page.
    Confirms the free key works AND prints real JSON so you can verify history
    is actually returned before committing your daily quota to a full run."""
    print(f"🔎 probe: {name}\n")

    search = client.get("/api/search", {"q": name})
    print("=== /api/search (truncated) ===")
    print(json.dumps(search, indent=2)[:1500], "\n")

    pid = extract_player_id(search, name)
    if not pid:
        print("⚠️  Could not auto-detect a player id from the search response.")
        print("    Inspect the JSON above and adjust extract_player_id().")
        print(client.report())
        return
    print(f"✅ resolved id: {pid}\n")

    try:
        events = client.get(f"/api/teams/{pid}/events/last/1")
    except NotFound:
        print("⚠️  /events/last/1 returned 404 — this entity has no match history "
              "(possibly a doubles pair or a namesake). Try another --name.")
        print(client.report())
        return
    rows = extract_matches(events, name, int(pid))
    print("=== /api/teams/:id/events/last/1 ===")
    print(json.dumps(events, indent=2)[:1500], "\n")
    print(f"✅ history page returned {len(rows)} parsed match rows.")
    if rows:
        print("   sample:", json.dumps(rows[0], indent=2))
    else:
        print("   ⚠️  0 rows parsed — history may be empty OR the JSON shape "
              "differs; inspect the dump above and adjust extract_matches().")
    print("\n" + client.report())


def cmd_run(client: Client, pages: int) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Resume id-resolution from a saved map so re-runs don't re-search.
    id_map_path = DATA_DIR / "player_ids.json"
    id_map: dict[str, str] = {}
    if id_map_path.exists():
        id_map = json.loads(id_map_path.read_text(encoding="utf-8"))

    players_out: list[dict] = []
    all_matches: list[dict] = []
    stopped_early = False

    try:
        for name in SEED_PLAYERS:
            # 1) Resolve name -> entity via search (id + country + gender in one
            #    call). The search response is cached on disk, so re-runs are free;
            #    id_map just keeps a clean human-readable name->id record.
            entity = extract_player_entity(client.get("/api/search", {"q": name}), name)
            if not entity:
                print(f"  ⚠️  no match for {name!r}, skipping")
                continue
            pid = int(entity["id"])
            id_map[name] = str(pid)
            id_map_path.write_text(json.dumps(id_map, indent=2), encoding="utf-8")

            country = entity.get("country") or {}
            country = country.get("name") if isinstance(country, dict) else country

            # 2) Match history pages. (No separate profile call: /api/teams/:id
            #    carries no ranking or hand, only country — already have that.)
            player_matches: list[dict] = []
            for page in range(1, pages + 1):
                try:
                    events = client.get(f"/api/teams/{pid}/events/last/{page}")
                except NotFound:
                    break  # no more pages for this player
                player_matches.extend(extract_matches(events, name, pid))
            all_matches.extend(player_matches)

            players_out.append({
                "name": name,
                "id": pid,
                "country": country,
                "gender": entity.get("gender"),
                "rank": None,  # not exposed by this API — see README note
                "matches_pulled": len(player_matches),
            })
            print(f"  ✓ {name}: matches={len(player_matches)}")

    except BudgetExhausted as e:
        stopped_early = True
        print(f"\n⏸️  {e}")

    # Compute Elo from whatever history we have so far, then write outputs.
    # Elo is keyed by team id; map it back onto each seed player.
    elo = compute_elo(all_matches)
    for p in players_out:
        p["elo"] = elo.get(p["id"])

    (DATA_DIR / "players.json").write_text(
        json.dumps(players_out, indent=2, ensure_ascii=False), encoding="utf-8")

    with (DATA_DIR / "matches.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[
            "event_id", "date", "tournament", "discipline", "player", "player_id",
            "opponent", "opponent_id", "sets_for", "sets_against", "won"])
        w.writeheader()
        w.writerows(all_matches)

    print(f"\n📦 wrote {len(players_out)} players -> data/players.json")
    print(f"📦 wrote {len(all_matches)} matches  -> data/matches.csv")
    print(client.report())
    if stopped_early:
        print("\n↻ Run again later (e.g. after quota resets at 00:00 UTC) to "
              "resume — cached players are free, only new ones cost requests.")


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main() -> None:
    # Windows consoles often default to cp1252; force UTF-8 so the emoji prints
    # below don't raise UnicodeEncodeError.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass

    load_dotenv()
    parser = argparse.ArgumentParser(description="SportsAPIPro badminton ingestion")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_probe = sub.add_parser("probe", help="cheap key/shape check (~3 requests)")
    p_probe.add_argument("--name", default="Viktor Axelsen")
    p_probe.add_argument("--budget", type=int, default=5)

    p_run = sub.add_parser("run", help="full ingestion (resumable)")
    p_run.add_argument("--pages", type=int, default=1,
                       help="history pages per player (1 page ≈ 1 request)")
    p_run.add_argument("--budget", type=int, default=90,
                       help="max NEW network calls this run (free plan = 100/day)")

    args = parser.parse_args()

    api_key = os.environ.get(API_KEY_ENV)
    if not api_key:
        raise SystemExit(
            f"❌ Set your API key first:  $env:{API_KEY_ENV} = 'your_key'  "
            f"(PowerShell)  /  export {API_KEY_ENV}=your_key  (bash)")

    client = Client(api_key=api_key, budget=args.budget)
    if args.cmd == "probe":
        cmd_probe(client, args.name)
    elif args.cmd == "run":
        cmd_run(client, pages=args.pages)


if __name__ == "__main__":
    main()
