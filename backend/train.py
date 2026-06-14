"""
🏸 Reproducible training + evaluation pipeline for the badminton predictor.

Rebuilds the model from `backend/data/tournament_matches.csv` (produced by
ingest_tournaments.py) using LEAKAGE-FREE features, compares it honestly against
naive baselines with cross-validation AND a chronological hold-out, then calibrates
the winner and saves it for the API.

USAGE
-----
    cd backend
    python train.py
    # or, inside the project venv:
    venv\\Scripts\\python.exe train.py   (Windows)
    venv/bin/python train.py             (macOS/Linux)

OUTPUTS  (backend/trained_models/)
----------------------------------
    best_model.pkl          calibrated best model, fitted on ALL matches
    feature_columns.pkl     ordered feature names the API must feed, in order
    mappings.pkl            round/type code maps (kept so request validation works)
    metrics.json            machine-readable results (the API reads the headline here)
    training_report.md      human-readable summary table
    model_<name>.pkl        each candidate model refit on all data (for inspection)
    plot_*.png              figures: model comparison, confusion matrix, ROC,
                            reliability/calibration curve, feature importance
                            (needs matplotlib — `pip install -r requirements-dev.txt`)

WHY NO LEAKAGE?
---------------
Each row carries the players' REAL Elo + world rank as they stood GOING INTO that
match (badmintonranks.com snapshots; the `(+/-)` in the source is applied after). So
every feature uses only pre-match information — no need to replay history, and no
risk of leaking the outcome via a final/aggregate rating. Serving (`main.py`) uses a
player's latest-known rating, which is the same "rating going into the match" idea
applied to an upcoming, unseen match.

Training needs numpy + scikit-learn + xgboost (all in requirements.txt); the plots
also need matplotlib (requirements-dev.txt). XGBoost is the gradient-boosting
candidate. The deployed API (main.py) does NOT import matplotlib, so
requirements.txt stays lean.
"""

from __future__ import annotations

import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, roc_auc_score
from sklearn.model_selection import GridSearchCV, StratifiedKFold, cross_validate
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier
from xgboost import XGBClassifier

# Feature engineering lives in features.py so training and serving stay identical.
from features import FEATURES, ROUND_MAPPING, TYPE_MAPPING, build_features

# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
HERE = Path(__file__).resolve().parent
DATA_DIR = HERE / "data"
OUT_DIR = HERE / "trained_models"

RANDOM_STATE = 42
N_FOLDS = 5
HOLDOUT_FRAC = 0.20  # last 20% of matches (by date) become the chronological test set.


def _to_int(x: str) -> int | None:
    x = (x or "").strip()
    try:
        return int(float(x))
    except ValueError:
        return None


def load_dataset() -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Read data/tournament_matches.csv and build the feature matrix.

    Each row is a real match with the winner's and loser's PRE-MATCH Elo + rank, so
    features come straight from build_features (no leakage). Every row starts as
    winner=A (label 1); we randomly flip orientation (negating the diff features and
    the label) so the classes are ~50/50 and 'always predict A' isn't a free win."""
    rng = np.random.default_rng(RANDOM_STATE)
    X, y, dates = [], [], []
    path = DATA_DIR / "tournament_matches.csv"
    for r in csv.DictReader(path.open(encoding="utf-8")):
        we, le = _to_int(r["winner_elo"]), _to_int(r["loser_elo"])
        if we is None or le is None:
            continue
        feat = build_features(we, _to_int(r["winner_rank"]), le, _to_int(r["loser_rank"]),
                              r["round"], r["type"], r["tournament"])
        if bool(rng.integers(0, 2)):  # flip A<->B
            feat = [-feat[0], -feat[1], feat[2], feat[3], feat[4]]
            label = 0
        else:
            label = 1
        X.append(feat)
        y.append(label)
        dates.append(r["date"])
    return np.asarray(X, dtype=float), np.asarray(y, dtype=int), dates


# --------------------------------------------------------------------------- #
# 3. Models + baselines
# --------------------------------------------------------------------------- #
def candidate_models() -> dict[str, object]:
    """The pool we compare. LogReg is scaled (Elo dwarfs the others); the tree is
    tuned with a small grid so it competes fairly with the ensembles."""
    tuned_tree = GridSearchCV(
        DecisionTreeClassifier(random_state=RANDOM_STATE),
        {"max_depth": [3, 4, 5, 6, 8, None],
         "min_samples_leaf": [5, 10, 20, 40]},
        scoring="accuracy", cv=N_FOLDS,
    )
    return {
        "logistic_regression": make_pipeline(
            StandardScaler(), LogisticRegression(max_iter=1000)),
        "decision_tree": tuned_tree,
        "random_forest": RandomForestClassifier(
            n_estimators=400, min_samples_leaf=5, random_state=RANDOM_STATE,
            n_jobs=-1),
        "xgboost": XGBClassifier(
            n_estimators=100, max_depth=4, learning_rate=0.1,
            subsample=0.8, colsample_bytree=0.8, eval_metric="logloss",
            random_state=RANDOM_STATE, n_jobs=-1),
    }


def _rule_accuracy(diff: np.ndarray, y: np.ndarray) -> float:
    """Accuracy of 'whoever has the positive diff wins' (ties -> majority class)."""
    majority = int(round(y.mean()))
    pred = np.where(diff > 0, 1, np.where(diff < 0, 0, majority))
    return accuracy_score(y, pred)


def elo_rule_accuracy(X: np.ndarray, y: np.ndarray) -> float:
    """Baseline: the higher-Elo player wins (elo_diff is FEATURES column 1)."""
    return _rule_accuracy(X[:, FEATURES.index("elo_diff")], y)


def rank_rule_accuracy(X: np.ndarray, y: np.ndarray) -> float:
    """Baseline: the better-ranked player wins (rank_diff is FEATURES column 0)."""
    return _rule_accuracy(X[:, FEATURES.index("rank_diff")], y)


# --------------------------------------------------------------------------- #
# 4. Train / evaluate / save
# --------------------------------------------------------------------------- #
def main() -> None:
    for stream in (sys.stdout, sys.stderr):  # emoji-safe on Windows consoles
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    import joblib  # local import so the module docstring/usage prints even if absent

    X, y, dates = load_dataset()
    print(f"📊 {len(X)} singles matches | features={FEATURES} | "
          f"label balance: {y.mean():.1%} class-1")

    # --- baselines ---
    majority_acc = max(y.mean(), 1 - y.mean())
    elo_acc = elo_rule_accuracy(X, y)
    rank_acc = rank_rule_accuracy(X, y)
    print(f"\n📏 Baselines (full data):")
    print(f"   majority-class  : {majority_acc:.3f}")
    print(f"   higher-Elo-wins : {elo_acc:.3f}")
    print(f"   better-rank-wins: {rank_acc:.3f}")

    # --- k-fold CV for every candidate ---
    skf = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=RANDOM_STATE)
    scoring = {"acc": "accuracy", "auc": "roc_auc", "brier": "neg_brier_score"}
    models = candidate_models()
    cv_results: dict[str, dict] = {}
    print(f"\n🤖 {N_FOLDS}-fold cross-validation:")
    print(f"   {'model':22s} {'acc':>14s} {'roc_auc':>9s} {'brier':>8s}")
    for name, model in models.items():
        cv = cross_validate(model, X, y, cv=skf, scoring=scoring, n_jobs=-1)
        acc_m, acc_s = cv["test_acc"].mean(), cv["test_acc"].std()
        auc_m = cv["test_auc"].mean()
        brier_m = -cv["test_brier"].mean()
        cv_results[name] = {"acc": acc_m, "acc_std": acc_s, "auc": auc_m,
                            "brier": brier_m}
        print(f"   {name:22s} {acc_m:.3f} ± {acc_s:.3f}  {auc_m:9.3f} {brier_m:8.3f}")

    # Also score the dummy baseline through the same CV for an apples-to-apples row.
    dummy_cv = cross_validate(DummyClassifier(strategy="most_frequent"), X, y,
                              cv=skf, scoring={"acc": "accuracy"})
    cv_results["baseline_majority"] = {"acc": dummy_cv["test_acc"].mean(),
                                       "acc_std": dummy_cv["test_acc"].std(),
                                       "auc": 0.5, "brier": None}
    cv_results["baseline_higher_elo"] = {"acc": elo_acc, "acc_std": 0.0,
                                         "auc": None, "brier": None}
    cv_results["baseline_better_rank"] = {"acc": rank_acc, "acc_std": 0.0,
                                          "auc": None, "brier": None}

    # --- chronological hold-out: train on the past, test on the most recent slice.
    # This is the SELECTION metric: it mirrors real use (forecast upcoming matches),
    # whereas random k-fold mildly leaks temporal structure. CV is reported too. ---
    from sklearn.base import clone
    order = np.argsort(dates, kind="stable")
    cut = int(len(order) * (1 - HOLDOUT_FRAC))
    tr, te = order[:cut], order[cut:]
    holdout = {}
    for name, model in models.items():
        m = clone(model)
        m.fit(X[tr], y[tr])
        pred = m.predict(X[te])
        proba = m.predict_proba(X[te])[:, 1]
        holdout[name] = {
            "acc": accuracy_score(y[te], pred),
            "auc": roc_auc_score(y[te], proba),
        }
    ho_elo = elo_rule_accuracy(X[te], y[te])
    ho_rank = rank_rule_accuracy(X[te], y[te])
    print(f"\n📅 Chronological hold-out (train {len(tr)} oldest, test {len(te)} "
          f"newest — {dates[order[cut]]} →):")
    print(f"   {'higher-Elo-wins':22s} {ho_elo:.3f}")
    print(f"   {'better-rank-wins':22s} {ho_rank:.3f}")
    for name in models:
        print(f"   {name:22s} {holdout[name]['acc']:.3f}  "
              f"(auc {holdout[name]['auc']:.3f})")

    # --- pick the best learned model by chronological hold-out accuracy ---
    best_name = max(models, key=lambda n: holdout[n]["acc"])
    best_acc = holdout[best_name]["acc"]
    print(f"\n🏆 Best by hold-out accuracy: {best_name} ({best_acc:.3f}) "
          f"| CV acc {cv_results[best_name]['acc']:.3f}")

    # --- calibrate the winner, then fit on ALL data for serving ---
    base_best = clone(models[best_name])
    # small dataset -> sigmoid (Platt) is safer than isotonic
    calibrated = CalibratedClassifierCV(base_best, method="sigmoid", cv=N_FOLDS)
    calibrated.fit(X, y)

    # Brier before/after calibration, via CV, to show calibration actually helps.
    brier_raw = -cross_validate(clone(models[best_name]), X, y, cv=skf,
                                scoring="neg_brier_score")["test_score"].mean()
    brier_cal = -cross_validate(
        CalibratedClassifierCV(clone(models[best_name]), method="sigmoid",
                               cv=N_FOLDS),
        X, y, cv=skf, scoring="neg_brier_score")["test_score"].mean()
    print(f"\n🎯 Brier (lower=better)  raw {brier_raw:.3f}  ->  "
          f"calibrated {brier_cal:.3f}")

    # --- persist everything ---
    joblib.dump(calibrated, OUT_DIR / "best_model.pkl")
    joblib.dump(FEATURES, OUT_DIR / "feature_columns.pkl")
    joblib.dump({"round_mapping": ROUND_MAPPING, "type_mapping": TYPE_MAPPING},
                OUT_DIR / "mappings.pkl")
    for name, model in models.items():
        joblib.dump(clone(model).fit(X, y), OUT_DIR / f"model_{name}.pkl")

    pretty = {"logistic_regression": "Logistic Regression",
              "decision_tree": "Decision Tree",
              "random_forest": "Random Forest",
              "xgboost": "XGBoost"}
    metrics = {
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_matches": int(len(X)),
        "features": FEATURES,
        "best_model": best_name,
        "best_model_label": pretty.get(best_name, best_name),
        "selection_metric": "chronological_holdout_accuracy",
        "headline_accuracy": round(best_acc, 4),           # chronological hold-out
        "headline_accuracy_pct": f"{best_acc * 100:.1f}%",
        "holdout_accuracy": round(holdout[best_name]["acc"], 4),
        "cv_accuracy": round(cv_results[best_name]["acc"], 4),
        "calibrated": True,
        "brier_raw": round(brier_raw, 4),
        "brier_calibrated": round(brier_cal, 4),
        "baselines": {
            "majority_class": round(float(majority_acc), 4),
            "higher_elo_wins": round(float(elo_acc), 4),
            "better_rank_wins": round(float(rank_acc), 4),
            "higher_elo_wins_holdout": round(float(ho_elo), 4),
            "better_rank_wins_holdout": round(float(ho_rank), 4),
        },
        "cv": {n: {k: (round(v, 4) if isinstance(v, float) else v)
                   for k, v in r.items()} for n, r in cv_results.items()},
        "holdout": {n: {k: round(v, 4) for k, v in r.items()}
                    for n, r in holdout.items()},
    }
    (OUT_DIR / "metrics.json").write_text(json.dumps(metrics, indent=2),
                                          encoding="utf-8")
    _write_report(metrics)
    _make_plots(X, y, tr, te, models, best_name, metrics)
    print(f"\n✅ Saved best_model.pkl ({pretty.get(best_name, best_name)}), "
          f"feature_columns.pkl, mappings.pkl, metrics.json, training_report.md")
    print(f"   Headline accuracy the API will show: {metrics['headline_accuracy_pct']}")


def _write_report(metrics: dict) -> None:
    """Human-readable markdown summary for the FYP write-up."""
    lines = [
        "# Badminton Predictor — Training Report",
        "",
        f"_Generated {metrics['trained_at']} · {metrics['n_matches']} unique "
        "matches · leakage-free point-in-time features_",
        "",
        f"**Features:** `{', '.join(metrics['features'])}`  ",
        f"**Best model:** {metrics['best_model_label']} · calibrated (Platt)  ",
        f"**Selected by:** chronological hold-out accuracy (forecasting the most "
        "recent matches)  ",
        f"**Headline accuracy (chronological hold-out):** "
        f"{metrics['headline_accuracy_pct']}  ",
        f"**5-fold CV accuracy (same model):** {metrics['cv_accuracy']:.1%}",
        "",
        "## Baselines to beat",
        "",
        f"- Majority class: **{metrics['baselines']['majority_class']:.1%}**",
        f"- Higher-Elo-wins (full / hold-out): "
        f"**{metrics['baselines']['higher_elo_wins']:.1%}** / "
        f"**{metrics['baselines']['higher_elo_wins_holdout']:.1%}**",
        f"- Better-rank-wins (full / hold-out): "
        f"**{metrics['baselines']['better_rank_wins']:.1%}** / "
        f"**{metrics['baselines']['better_rank_wins_holdout']:.1%}**",
        "",
        "## Cross-validation (5-fold)",
        "",
        "| Model | Accuracy | ROC-AUC | Brier |",
        "|---|---|---|---|",
    ]
    for name, r in metrics["cv"].items():
        acc = f"{r['acc']:.3f} ± {r.get('acc_std', 0):.3f}"
        auc = "—" if r.get("auc") in (None,) else f"{r['auc']:.3f}"
        brier = "—" if r.get("brier") in (None,) else f"{r['brier']:.3f}"
        lines.append(f"| {name} | {acc} | {auc} | {brier} |")
    lines += [
        "",
        "## Chronological hold-out (train on oldest 80%, test on newest 20%)",
        "",
        "| Model | Accuracy | ROC-AUC |",
        "|---|---|---|",
    ]
    for name, r in metrics["holdout"].items():
        lines.append(f"| {name} | {r['acc']:.3f} | {r['auc']:.3f} |")
    lines += [
        "",
        "## Calibration",
        "",
        f"Brier score (lower is better): raw **{metrics['brier_raw']:.3f}** → "
        f"calibrated **{metrics['brier_calibrated']:.3f}**.",
        "",
        "_The model is selected and headlined on the chronological hold-out (train on"
        " the oldest 80%, test on the newest 20%) — the honest 'forecast the next"
        " matches' setting. 5-fold CV is reported alongside for completeness._",
        "",
        "## Figures",
        "",
        "![Model accuracy vs baselines](plot_model_comparison.png)",
        "![Confusion matrix (hold-out)](plot_confusion_matrix.png)",
        "![ROC curve (hold-out)](plot_roc_curve.png)",
        "![Reliability / calibration curve (hold-out)](plot_calibration_curve.png)",
        "![Permutation feature importance](plot_feature_importance.png)",
        "",
        "_Figures need matplotlib (`pip install -r requirements-dev.txt`)._",
        "",
    ]
    (OUT_DIR / "training_report.md").write_text("\n".join(lines), encoding="utf-8")


def _make_plots(X, y, tr, te, models, best_name, metrics) -> None:
    """Write FYP-ready figures to trained_models/. All hold-out plots evaluate the
    selected model in the honest 'forecast the newest 20%' setting. Skips cleanly
    (with a hint) if matplotlib isn't installed — it's a training-only dependency,
    see requirements-dev.txt."""
    try:
        import matplotlib
        matplotlib.use("Agg")  # headless: write PNGs without a display
        import matplotlib.pyplot as plt
        from sklearn.base import clone
        from sklearn.calibration import CalibratedClassifierCV, CalibrationDisplay
        from sklearn.inspection import permutation_importance
        from sklearn.metrics import (ConfusionMatrixDisplay, RocCurveDisplay,
                                      confusion_matrix)
    except ImportError:
        print("ℹ️  matplotlib not installed — skipping plots "
              "(pip install -r requirements-dev.txt to enable them).")
        return

    label = metrics["best_model_label"]
    names = list(models.keys())
    best = clone(models[best_name]).fit(X[tr], y[tr])  # uncalibrated, matches headline

    # 1) Model accuracy vs baselines (CV + hold-out, with baseline reference lines).
    cv_acc = [metrics["cv"][n]["acc"] for n in names]
    ho_acc = [metrics["holdout"][n]["acc"] for n in names]
    x = np.arange(len(names))
    w = 0.38
    fig, ax = plt.subplots(figsize=(8, 5))
    b1 = ax.bar(x - w / 2, cv_acc, w, label="5-fold CV", color="#9bb8d3")
    b2 = ax.bar(x + w / 2, ho_acc, w, label="Chronological hold-out", color="#16a34a")
    ax.axhline(metrics["baselines"]["majority_class"], ls=":", c="gray",
               label=f"Majority ({metrics['baselines']['majority_class']:.1%})")
    ax.axhline(metrics["baselines"]["higher_elo_wins_holdout"], ls="--", c="#444",
               label=f"Higher-Elo, hold-out "
                     f"({metrics['baselines']['higher_elo_wins_holdout']:.1%})")
    ax.bar_label(b1, fmt="%.2f", fontsize=7, padding=1)
    ax.bar_label(b2, fmt="%.2f", fontsize=7, padding=1)
    ax.set_xticks(x, [n.replace("_", "\n") for n in names], fontsize=8)
    ax.set_ylabel("Accuracy")
    ax.set_ylim(0.4, 0.85)
    ax.set_title("Model accuracy vs naive baselines")
    ax.legend(loc="lower right", fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "plot_model_comparison.png", dpi=130)
    plt.close(fig)

    # 2) Confusion matrix of the selected model on the hold-out.
    fig, ax = plt.subplots(figsize=(4.6, 4.2))
    ConfusionMatrixDisplay(
        confusion_matrix(y[te], best.predict(X[te])),
        display_labels=["B wins (0)", "A wins (1)"],
    ).plot(ax=ax, cmap="Blues", colorbar=False)
    ax.set_title(f"{label} — hold-out confusion\n"
                 f"(accuracy {metrics['holdout'][best_name]['acc']:.1%})")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "plot_confusion_matrix.png", dpi=130)
    plt.close(fig)

    # 3) ROC curve on the hold-out.
    fig, ax = plt.subplots(figsize=(5, 4.6))
    RocCurveDisplay.from_estimator(best, X[te], y[te], ax=ax, name=label,
                                   curve_kwargs={"color": "#16a34a"})
    ax.plot([0, 1], [0, 1], ls="--", c="gray", lw=1)
    ax.set_title("ROC curve — chronological hold-out")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "plot_roc_curve.png", dpi=130)
    plt.close(fig)

    # 4) Reliability curve: raw vs calibrated, to justify the calibration step.
    cal = CalibratedClassifierCV(clone(models[best_name]), method="sigmoid",
                                 cv=N_FOLDS).fit(X[tr], y[tr])
    fig, ax = plt.subplots(figsize=(5, 4.6))
    CalibrationDisplay.from_estimator(best, X[te], y[te], n_bins=5, ax=ax,
                                      name="raw", color="#9bb8d3")
    CalibrationDisplay.from_estimator(cal, X[te], y[te], n_bins=5, ax=ax,
                                      name="calibrated", color="#16a34a")
    ax.set_title(f"Reliability curve — hold-out\n"
                 f"(Brier {metrics['brier_raw']:.3f} → {metrics['brier_calibrated']:.3f})")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "plot_calibration_curve.png", dpi=130)
    plt.close(fig)

    # 5) Permutation importance (model-agnostic, measured as hold-out accuracy drop).
    r = permutation_importance(best, X[te], y[te], n_repeats=20,
                               random_state=RANDOM_STATE, scoring="accuracy")
    order = np.argsort(r.importances_mean)
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.barh(np.array(FEATURES)[order], r.importances_mean[order],
            xerr=r.importances_std[order], color="#16a34a")
    ax.axvline(0, c="gray", lw=0.8)
    ax.set_xlabel("Permutation importance (drop in hold-out accuracy)")
    ax.set_title(f"{label} — feature importance")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "plot_feature_importance.png", dpi=130)
    plt.close(fig)

    print("🖼️  Saved plots: plot_model_comparison, plot_confusion_matrix, "
          "plot_roc_curve, plot_calibration_curve, plot_feature_importance (.png)")


if __name__ == "__main__":
    main()
