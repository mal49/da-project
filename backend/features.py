"""
🏸 Shared feature engineering — the single source of truth for how a match becomes
model features, used by BOTH train.py (training) and main.py (serving), so the
model is trained and queried identically.

The tournament dataset gives each player's REAL pre-match Elo and world rank per
match (see ingest_tournaments.py), so features come straight from those numbers —
no Elo replay, no leakage. Training uses each match's own pre-match values; serving
uses a player's latest-known rating (the same "rating going into the match" idea).
"""

from __future__ import annotations

# Feature order is the contract with the model. Do NOT reorder.
FEATURES = ["rank_diff", "elo_diff", "round_level", "type_encoded", "tier"]

# Map every round label we see (dataset vocab + the UI's request vocab) onto one
# monotonic "how deep in the draw" scale. round_level is a weak feature, so the
# small vocab overlaps don't matter much.
ROUND_MAPPING = {
    "Qualification": 0,
    "Group A": 1, "Group B": 1, "Group": 1,
    "Round 1": 1, "Round of 64": 1,
    "Round 2": 2, "Round of 32": 2,
    "Round 3": 3, "Round of 16": 3,
    "Quarter final": 4, "Quarterfinal": 4, "Quarter-final": 4,
    "Semi final": 5, "Semifinal": 5, "Semi-final": 5,
    "Final": 6,
}
TYPE_MAPPING = {"MS": 0, "WS": 1, "MD": 2, "WD": 3, "XD": 4}

# Neutral fallbacks for an unknown player (no rating on file) -> prediction leans
# on the rest and lands near a coin flip rather than erroring.
NEUTRAL_ELO = 2200
NEUTRAL_RANK = 200


def get_tournament_tier(name: str) -> int:
    """Coarse prestige tier from the tournament name."""
    name = str(name).lower()
    if any(x in name for x in ("super 1000", "world tour finals", "olympic",
                               "world championship")):
        return 3
    if any(x in name for x in ("super 750", "all england", "china open",
                               "indonesia open")):
        return 2
    if "super 500" in name:
        return 1
    return 0


def build_features(elo_a: int | None, rank_a: int | None,
                   elo_b: int | None, rank_b: int | None,
                   round_label: str, match_type: str, tournament: str) -> list[float]:
    """Feature vector (in FEATURES order) for an A-vs-B match. Differences are
    A-minus-B: rank_diff > 0 when A is the better-ranked (lower number) player,
    elo_diff > 0 when A is higher rated."""
    ea = NEUTRAL_ELO if elo_a is None else elo_a
    eb = NEUTRAL_ELO if elo_b is None else elo_b
    ra = NEUTRAL_RANK if rank_a is None else rank_a
    rb = NEUTRAL_RANK if rank_b is None else rank_b
    return [
        float(rb - ra),                                  # rank_diff
        float(ea - eb),                                  # elo_diff
        float(ROUND_MAPPING.get(round_label, 2)),        # round_level
        float(TYPE_MAPPING.get(match_type, 0)),          # type_encoded
        float(get_tournament_tier(tournament)),          # tier
    ]
