from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
import joblib
import numpy as np
import os
from typing import Optional

app = FastAPI(title="🏸 Badminton Match Predictor API")

# Enable CORS for React Frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
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

# ============ ENDPOINTS ============
@app.get("/")
def read_root():
    return {
        "message": "🏸 Badminton Match Prediction API",
        "status": "online",
        "model_accuracy": "76.3%"
    }

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
