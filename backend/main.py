from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
import joblib
import numpy as np
import os
import csv
import json
from collections import defaultdict
from typing import Optional

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
    print("💡 Make sure 'trained_models' folder exists in the parent directory.")
    raise e

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

# ============ HELPER FUNCTIONS ============
def get_tournament_tier(name: str) -> int:
    name = str(name).lower()
    if any(x in name for x in ['super 1000', 'world tour finals', 'olympic', 'world championship']):
        return 3
    elif any(x in name for x in ['super 750', 'all england', 'china open', 'indonesia open']):
        return 2
    elif 'super 500' in name:
        return 1
    return 0

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


def _load_leaderboard() -> dict:
    """Elo strength ladder from ingested match history (served at /players)."""
    stats, season = _match_stats()
    players = [
        {"name": name, **s} for name, s in stats.items() if s["elo"] is not None
    ]
    players.sort(key=lambda p: p["elo"], reverse=True)
    return {"available": bool(players), "season": season, "players": players}


def _load_rankings() -> dict:
    """Official BWF World Ranking snapshot (served at /rankings), enriched with
    match-derived record + form where we have history. Sorted by world rank.
    The snapshot is refreshed from Wikipedia by fetch_wikipedia_rankings.py.
    Degrades to available=False if the file is missing."""
    try:
        with open(os.path.join(DATA_DIR, "bwf_rankings.json"), encoding="utf-8") as f:
            snapshot = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"available": False, "as_of": "", "source": "", "men": [], "women": []}

    stats, _ = _match_stats()

    def enrich(entries: list[dict]) -> list[dict]:
        out = []
        for e in sorted(entries, key=lambda x: x.get("rank") or 9999):
            s = stats.get(e.get("name"), {})
            out.append({
                "rank": e.get("rank"),
                "name": e.get("name"),
                "country": e.get("country"),
                "points": e.get("points"),
                "tournaments": e.get("tournaments"),
                # match-derived extras (null when we have no history for them)
                "wins": s.get("wins"),
                "losses": s.get("losses"),
                "form": s.get("form"),
                "elo": s.get("elo"),
            })
        return out

    men = enrich(snapshot.get("men", []))
    women = enrich(snapshot.get("women", []))
    return {
        "available": bool(men or women),
        "as_of": snapshot.get("as_of", ""),
        "source": snapshot.get("source", ""),
        "men": men,
        "women": women,
    }


LEADERBOARD = _load_leaderboard()
RANKINGS = _load_rankings()
print(f"📊 /players: {len(LEADERBOARD['players'])} players "
      f"({LEADERBOARD['season'] or 'no matches'})  |  "
      f"📈 /rankings: {len(RANKINGS['men'])} men + {len(RANKINGS['women'])} women "
      f"(as of {RANKINGS['as_of'] or 'n/a'})")

# ============ ENDPOINTS ============
@app.get("/")
def read_root():
    return {
        "message": "🏸 Badminton Match Prediction API",
        "status": "online",
        "model_accuracy": "76.3%"
    }

@app.get("/rankings")
def get_rankings():
    """Official BWF World Ranking snapshot (men + women), sorted by world rank
    and enriched with match-derived record/form where available. Pre-computed at
    startup. Returns {available, as_of, source, men[], women[]}."""
    return RANKINGS

@app.get("/players")
def list_players():
    """Real leaderboard data (Elo + win/loss + last-5 form) for players we have
    ingested match history for, sorted by Elo descending. Pre-computed at
    startup. Returns {available, season, players[]}."""
    return LEADERBOARD

@app.post("/predict", response_model=MatchPredictionResponse)
def predict_match(request: MatchPredictionRequest):
    try:
        # 1. Prepare Features (MUST match training logic exactly)
        # Training: rank_diff = player_b_rank - player_a_rank
        rank_diff = request.player_b_rank - request.player_a_rank
        
        # Training: elo_diff = player_a_elo - player_b_elo
        # Default Elo to 2400 if not provided
        a_elo = request.player_a_elo if request.player_a_elo else 2400
        b_elo = request.player_b_elo if request.player_b_elo else 2400
        elo_diff = a_elo - b_elo
        
        # Encode Categoricals
        round_level = ROUND_MAPPING.get(request.round, 2)
        type_encoded = TYPE_MAPPING.get(request.match_type, 0)
        tournament_tier = get_tournament_tier(request.tournament_name)
        
        # 2. Create Feature Array (Order must match feature_columns.pkl)
        features = np.array([[
            rank_diff,
            elo_diff,
            round_level,
            type_encoded,
            tournament_tier
        ]])
        
        # 3. Make Prediction
        prediction = int(model.predict(features)[0])
        prediction_proba = model.predict_proba(features)[0]

        model_classes = getattr(model, "classes_", None)
        if model_classes is None:
            raise ValueError("Model does not expose class labels for probability mapping.")

        class_probabilities = {
            int(class_label): float(probability)
            for class_label, probability in zip(model_classes, prediction_proba)
        }
        if 0 not in class_probabilities or 1 not in class_probabilities:
            raise ValueError(f"Unexpected model classes: {list(model_classes)}")
        
        # 4. Interpret Results
        # Model predicts: 1 = Player A wins, 0 = Player B wins
        player_a_prob = class_probabilities[1]
        player_b_prob = class_probabilities[0]
        predicted_winner = request.player_a_name if prediction == 1 else request.player_b_name
        
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
            model_used="Decision Tree (76.3% Acc)"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Prediction error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    print("\n" + "="*60)
    print("🚀 Starting Badminton Prediction API...")
    print("📍 Open http://localhost:8000/docs to test")
    print("="*60)
    uvicorn.run(app, host="0.0.0.0", port=8000)
    