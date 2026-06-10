from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
import joblib
import numpy as np
import os
import csv
import json
import re
import unicodedata
from collections import defaultdict
from typing import Optional

# Feature engineering is shared with train.py so serving matches training exactly.
from features import build_features

app = FastAPI(title="🏸 Badminton Match Predictor API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============ LOAD MODELS ============
print("📂 Loading models...")
try:
    # Adjust path if needed (looks for trained_models in parent directory)
    model_path = os.path.join(os.path.dirname(__file__), ".", "trained_models", "best_model.pkl")
    features_path = os.path.join(os.path.dirname(__file__), ".", "trained_models", "feature_columns.pkl")
    mappings_path = os.path.join(os.path.dirname(__file__), ".", "trained_models", "mappings.pkl")
    
    model = joblib.load(model_path)
    feature_columns = joblib.load(features_path)
    mappings = joblib.load(mappings_path)

    ROUND_MAPPING = mappings['round_mapping']
    TYPE_MAPPING = mappings['type_mapping']
    print("✅ Models loaded successfully!")
except Exception as e:
    print(f"❌ Error loading models: {e}")
    print("💡 Run `python train.py` to (re)generate the trained_models artifacts.")
    raise e

# Model name + measured accuracy come from train.py's metrics.json, so the figures
# the UI shows always reflect the model that's actually loaded (no hardcoded number).
try:
    metrics_path = os.path.join(os.path.dirname(__file__), "trained_models", "metrics.json")
    with open(metrics_path, encoding="utf-8") as f:
        METRICS = json.load(f)
    MODEL_LABEL = METRICS.get("best_model_label", "Model")
    MODEL_ACCURACY_PCT = METRICS.get("headline_accuracy_pct", "")
    MODEL_USED = f"{MODEL_LABEL} ({MODEL_ACCURACY_PCT} Acc)" if MODEL_ACCURACY_PCT else MODEL_LABEL
except (OSError, json.JSONDecodeError):
    METRICS, MODEL_LABEL, MODEL_ACCURACY_PCT = {}, "Model", ""
    MODEL_USED = "Model"

# ============ REQUEST SCHEMA ============
class MatchPredictionRequest(BaseModel):
    player_a_name: str = Field(min_length=1)
    player_b_name: str = Field(min_length=1)
    player_a_rank: int = Field(ge=1, le=500)
    player_b_rank: int = Field(ge=1, le=500)
    player_a_elo: Optional[int] = Field(default=None, ge=1000, le=3500)
    player_b_elo: Optional[int] = Field(default=None, ge=1000, le=3500)
    tournament_name: str = Field(min_length=1)
    round: str
    match_type: str  # MS, WS, MD, WD, XD

    @field_validator("player_a_name", "player_b_name", "tournament_name")
    @classmethod
    def validate_non_empty_text(cls, value: str) -> str:
        normalized = " ".join(value.strip().split())
        if not normalized:
            raise ValueError("must not be blank")
        return normalized

    @field_validator("round")
    @classmethod
    def validate_round(cls, value: str) -> str:
        normalized = " ".join(value.strip().split())
        for valid_round in ROUND_MAPPING:
            if normalized.casefold() == valid_round.casefold():
                return valid_round
        raise ValueError(f"round must be one of: {', '.join(ROUND_MAPPING.keys())}")

    @field_validator("match_type")
    @classmethod
    def validate_match_type(cls, value: str) -> str:
        normalized = value.strip().upper()
        if normalized not in TYPE_MAPPING:
            raise ValueError(f"match_type must be one of: {', '.join(TYPE_MAPPING.keys())}")
        return normalized

class MatchPredictionResponse(BaseModel):
    player_a_win_probability: float
    player_b_win_probability: float
    predicted_winner: str
    confidence: str
    model_used: str

# ---- Tournament bracket simulation schema ----
class TournamentPlayer(BaseModel):
    name: str = Field(min_length=1)
    rank: int = Field(ge=1, le=2000)
    elo: Optional[int] = Field(default=None, ge=1000, le=3500)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        normalized = " ".join(value.strip().split())
        if not normalized:
            raise ValueError("must not be blank")
        return normalized

class TournamentRequest(BaseModel):
    players: list[TournamentPlayer]
    tournament_name: str = Field(min_length=1)
    match_type: str

    @field_validator("tournament_name")
    @classmethod
    def clean_tournament(cls, value: str) -> str:
        normalized = " ".join(value.strip().split())
        if not normalized:
            raise ValueError("must not be blank")
        return normalized

    @field_validator("match_type")
    @classmethod
    def validate_type(cls, value: str) -> str:
        normalized = value.strip().upper()
        if normalized not in TYPE_MAPPING:
            raise ValueError(f"match_type must be one of: {', '.join(TYPE_MAPPING.keys())}")
        return normalized

    @field_validator("players")
    @classmethod
    def validate_draw(cls, value: list[TournamentPlayer]) -> list[TournamentPlayer]:
        if len(value) not in (2, 4, 8, 16, 32):
            raise ValueError("players must contain 2, 4, 8, 16 or 32 entrants (a power of two)")
        return value

class BracketMatch(BaseModel):
    player_a: str
    player_b: str
    prob_a: float
    prob_b: float
    winner: str

class BracketRound(BaseModel):
    name: str
    size: int
    matches: list[BracketMatch]

class TournamentResponse(BaseModel):
    champion: str
    model_used: str
    rounds: list[BracketRound]

# Draw size -> model round label (feature) and human round name (display).
_ROUND_LABEL_BY_SIZE = {32: "Round of 32", 16: "Round of 16", 8: "Quarter final",
                        4: "Semi final", 2: "Final"}
_ROUND_NAME_BY_SIZE = {32: "Round of 32", 16: "Round of 16", 8: "Quarterfinals",
                       4: "Semifinals", 2: "Final"}

# ============ LEADERBOARD / RANKINGS (real data, pre-computed at startup) ============
# Two real-data sources live in backend/data/:
#   * players.json + matches.csv  -> match-derived Elo / win-loss / form
#     (from the SportsAPIPro ingestion, see ingest_data.py)
#   * bwf_rankings.json           -> official BWF World Ranking snapshot
#     (rank + points, parsed from Wikipedia; see fetch_wikipedia_rankings.py)
# /players serves the Elo ladder; /rankings serves the BWF ladder enriched with
# the match stats. Both degrade to available=False if their data files are
# missing, so the frontend can fall back to its static demo roster.
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


def _match_stats() -> tuple[dict, str]:
    """Per-player match-derived stats keyed by name (real Elo from players.json +
    win/loss + last-5 form from matches.csv), plus the season span string.
    Returns ({}, "") if the data files are absent."""
    try:
        with open(os.path.join(DATA_DIR, "players.json"), encoding="utf-8") as f:
            roster = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}, ""

    elo_by_name = {e.get("name"): e.get("elo") for e in roster}
    history: dict[str, list[dict]] = defaultdict(list)
    dates: list[str] = []
    try:
        with open(os.path.join(DATA_DIR, "matches.csv"), encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                if row.get("player"):
                    history[row["player"]].append(row)
                if row.get("date"):
                    dates.append(row["date"])
    except OSError:
        pass

    stats: dict[str, dict] = {}
    for name, rows in history.items():
        rows.sort(key=lambda r: r.get("date") or "")
        wins = sum(1 for r in rows if r.get("won") == "True")
        played = len(rows)
        elo = elo_by_name.get(name)
        stats[name] = {
            "elo": int(elo) if elo is not None else None,
            "wins": wins,
            "losses": played - wins,
            "played": played,
            # Last 5 results, oldest -> newest (left -> right in the UI).
            "form": [1 if r.get("won") == "True" else 0 for r in rows[-5:]],
        }

    season = ""
    if dates:
        lo, hi = min(dates)[:4], max(dates)[:4]
        season = lo if lo == hi else f"{lo}–{hi[2:]}"  # e.g. "2022–26"
    return stats, season


def _load_player_ratings() -> tuple[dict, dict]:
    """Real tournament ratings — Elo + world rank + record + last-5 form per player,
    from data/player_ratings.json (built by ingest_tournaments.py from the
    badmintonranks tournament CSVs). Served at /players and used by /predict.

    Returns (payload, by_name) where payload is the /players response and by_name
    maps player name -> rating (incl. a casefold alias for resilient lookups).
    Degrades to available=False if the file is missing."""
    try:
        with open(os.path.join(DATA_DIR, "player_ratings.json"), encoding="utf-8") as f:
            players = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"available": False, "season": "", "players": []}, {}

    players.sort(key=lambda p: p.get("elo") or 0, reverse=True)
    by_name: dict[str, dict] = {}
    for p in players:
        by_name[p["name"]] = p
        by_name[p["name"].casefold()] = p

    years = [p["as_of"][:4] for p in players if p.get("as_of")]
    season = ""
    if years:
        lo, hi = min(years), max(years)
        season = lo if lo == hi else f"{lo}–{hi[2:]}"  # e.g. "2021–26"
    return {"available": bool(players), "season": season, "players": players}, by_name


def _pair_key(pair_name: str) -> frozenset:
    """Order-/spacing-/accent-independent identity for a doubles pair: the set of
    its two members each reduced to lowercase letters+digits. So 'Liu Shengshu / Tan
    Ning' (Wikipedia) and 'Liu Sheng Shu / Tan Ning' (CSV pool) collapse to the same
    key, regardless of which member is listed first."""
    def norm(m: str) -> str:
        s = unicodedata.normalize("NFKD", m or "")
        s = "".join(c for c in s if not unicodedata.combining(c))
        return re.sub(r"[^a-z0-9]", "", s.lower())
    return frozenset(norm(m) for m in pair_name.split(" / ") if m.strip())


def _load_rankings() -> dict:
    """Official BWF World Ranking snapshot (served at /rankings), all 5 disciplines,
    enriched with record + form + Elo where we have history. Sorted by world rank.
    The snapshot is refreshed from Wikipedia by fetch_wikipedia_rankings.py.
    Degrades to available=False if the file is missing."""
    empty = {"available": False, "as_of": "", "source": "",
             "men": [], "women": [], "md": [], "wd": [], "xd": []}
    try:
        with open(os.path.join(DATA_DIR, "bwf_rankings.json"), encoding="utf-8") as f:
            snapshot = json.load(f)
    except (OSError, json.JSONDecodeError):
        return empty

    stats, _ = _match_stats()
    # Doubles enrichment source: the pair team ratings (real Elo/record/form),
    # indexed by order-independent pair key so Wikipedia spellings still join.
    pair_index = {_pair_key(p["name"]): p for p in LEADERBOARD["players"]
                  if p.get("type") in ("MD", "WD", "XD")}

    def row(e: dict, extra: dict) -> dict:
        return {
            "rank": e.get("rank"),
            "name": e.get("name"),
            "country": e.get("country"),
            "points": e.get("points"),
            "tournaments": e.get("tournaments"),
            # match-derived extras (null when we have no history for them)
            "wins": extra.get("wins"),
            "losses": extra.get("losses"),
            "form": extra.get("form"),
            "elo": extra.get("elo"),
        }

    def enrich_singles(entries: list[dict]) -> list[dict]:
        return [row(e, stats.get(e.get("name"), {}))
                for e in sorted(entries, key=lambda x: x.get("rank") or 9999)]

    def enrich_doubles(entries: list[dict]) -> list[dict]:
        return [row(e, pair_index.get(_pair_key(e.get("name", "")), {}))
                for e in sorted(entries, key=lambda x: x.get("rank") or 9999)]

    men = enrich_singles(snapshot.get("men", []))
    women = enrich_singles(snapshot.get("women", []))
    md = enrich_doubles(snapshot.get("md", []))
    wd = enrich_doubles(snapshot.get("wd", []))
    xd = enrich_doubles(snapshot.get("xd", []))
    return {
        "available": bool(men or women or md or wd or xd),
        "as_of": snapshot.get("as_of", ""),
        "source": snapshot.get("source", ""),
        "men": men,
        "women": women,
        "md": md,
        "wd": wd,
        "xd": xd,
    }


LEADERBOARD, RATINGS_BY_NAME = _load_player_ratings()
RANKINGS = _load_rankings()
print(f"📊 /players: {len(LEADERBOARD['players'])} rated players "
      f"({LEADERBOARD['season'] or 'no data'})  |  "
      f"📈 /rankings (as of {RANKINGS['as_of'] or 'n/a'}): "
      f"MS {len(RANKINGS['men'])}, WS {len(RANKINGS['women'])}, "
      f"MD {len(RANKINGS['md'])}, WD {len(RANKINGS['wd'])}, XD {len(RANKINGS['xd'])}")
print(f"🧠 Predictor: {MODEL_USED}")


def _rating(name: str) -> Optional[dict]:
    """Real rating (elo + rank + ...) for a player name, or None when we have no
    tournament history for them — the model then falls back to neutral values."""
    return RATINGS_BY_NAME.get(name) or RATINGS_BY_NAME.get(name.casefold())


# Module-level probability helpers shared by /predict and /simulate, so a single
# bracket match is scored exactly like a head-to-head prediction.
MODEL_CLASSES = getattr(model, "classes_", None)
if MODEL_CLASSES is None:
    raise RuntimeError("Model does not expose class labels for probability mapping.")


def _prob_a_wins(feat: list[float]) -> float:
    """Raw P(side A wins) for one feature vector, via the model's class order."""
    proba = model.predict_proba(np.array([feat]))[0]
    cp = {int(c): float(p) for c, p in zip(MODEL_CLASSES, proba)}
    if 0 not in cp or 1 not in cp:
        raise ValueError(f"Unexpected model classes: {list(MODEL_CLASSES)}")
    return cp[1]


def _symmetric_prob_a(elo_a, rank_a, elo_b, rank_b,
                      round_label: str, match_type: str, tournament: str) -> float:
    """Symmetrized P(A beats B): average P(A wins | A-vs-B) with 1 - P(B wins | B-vs-A)
    so swapping the two players just mirrors the result (a tree model on difference
    features isn't antisymmetric on its own)."""
    feat_ab = build_features(elo_a, rank_a, elo_b, rank_b, round_label, match_type, tournament)
    feat_ba = [-feat_ab[0], -feat_ab[1], feat_ab[2], feat_ab[3], feat_ab[4]]
    return (_prob_a_wins(feat_ab) + (1.0 - _prob_a_wins(feat_ba))) / 2.0


# ============ ENDPOINTS ============
@app.get("/")
def read_root():
    return {
        "message": "🏸 Badminton Match Prediction API",
        "status": "online",
        "model_used": MODEL_USED,
        "model_label": MODEL_LABEL,
        "model_accuracy": MODEL_ACCURACY_PCT or "n/a",
        "matches_trained": METRICS.get("n_matches"),
    }

@app.get("/rankings")
def get_rankings():
    """Official BWF World Ranking snapshot (men + women), sorted by world rank
    and enriched with match-derived record/form where available. Pre-computed at
    startup. Returns {available, as_of, source, men[], women[]}."""
    return RANKINGS

@app.get("/players")
def list_players():
    """Real tournament ratings (Elo + world rank + win/loss + last-5 form), sorted
    by Elo descending. Pre-computed at startup. Returns {available, season,
    players[]}."""
    return LEADERBOARD

@app.post("/predict", response_model=MatchPredictionResponse)
def predict_match(request: MatchPredictionRequest):
    try:
        # 1. Build features the SAME way train.py did (see features.py), from each
        #    player's REAL Elo + world rank (resolved server-side from the tournament
        #    ratings — NOT the request's elo/rank, which may be stale UI values).
        #    Unknown players fall back to neutral, so we still answer.
        ra = _rating(request.player_a_name)
        rb = _rating(request.player_b_name)
        player_a_prob = _symmetric_prob_a(
            ra["elo"] if ra else None, ra["rank"] if ra else None,
            rb["elo"] if rb else None, rb["rank"] if rb else None,
            request.round, request.match_type, request.tournament_name,
        )
        player_b_prob = 1.0 - player_a_prob
        predicted_winner = (request.player_a_name if player_a_prob >= 0.5
                            else request.player_b_name)
        
        # 5. Determine Confidence
        max_prob = max(player_a_prob, player_b_prob)
        if max_prob >= 0.70:
            confidence = "High"
        elif max_prob >= 0.60:
            confidence = "Medium"
        else:
            confidence = "Low"
        
        return MatchPredictionResponse(
            player_a_win_probability=round(player_a_prob, 4),
            player_b_win_probability=round(player_b_prob, 4),
            predicted_winner=predicted_winner,
            confidence=confidence,
            model_used=MODEL_USED,
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Prediction error: {str(e)}")

@app.post("/simulate", response_model=TournamentResponse)
def simulate_tournament(request: TournamentRequest):
    """Single-elimination bracket simulation. `players` arrive in bracket order
    (slot 0 plays slot 1, slot 2 plays slot 3, ...); each round every pairing is
    scored with the same symmetrized model used by /predict, the more likely
    winner advances, and we repeat until one player remains. Returns every
    round's matchups with win probabilities, plus the predicted champion."""
    try:
        # (name, rank, elo) tuples; rebuilt each round from the previous winners.
        contenders = [(p.name, p.rank, p.elo) for p in request.players]
        rounds: list[BracketRound] = []
        while len(contenders) > 1:
            size = len(contenders)
            round_label = _ROUND_LABEL_BY_SIZE.get(size, "Round of 32")
            round_name = _ROUND_NAME_BY_SIZE.get(size, f"Round of {size}")
            matches: list[BracketMatch] = []
            winners: list[tuple] = []
            for i in range(0, size, 2):
                na, rka, ea = contenders[i]
                nb, rkb, eb = contenders[i + 1]
                # Prefer real server ratings; fall back to the values the client
                # sent (from the rankings) when we have no history on file.
                ra = _rating(na)
                rb = _rating(nb)
                prob_a = _symmetric_prob_a(
                    ra["elo"] if ra else ea, ra["rank"] if ra else rka,
                    rb["elo"] if rb else eb, rb["rank"] if rb else rkb,
                    round_label, request.match_type, request.tournament_name,
                )
                winner = contenders[i] if prob_a >= 0.5 else contenders[i + 1]
                matches.append(BracketMatch(
                    player_a=na, player_b=nb,
                    prob_a=round(prob_a, 4), prob_b=round(1.0 - prob_a, 4),
                    winner=winner[0],
                ))
                winners.append(winner)
            rounds.append(BracketRound(name=round_name, size=size, matches=matches))
            contenders = winners
        return TournamentResponse(
            champion=contenders[0][0], model_used=MODEL_USED, rounds=rounds,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Simulation error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    print("\n" + "="*60)
    print("🚀 Starting Badminton Prediction API...")
    print("📍 Open http://localhost:8000/docs to test")
    print("="*60)
    uvicorn.run(app, host="0.0.0.0", port=8000)
    