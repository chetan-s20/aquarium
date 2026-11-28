"""Early warning from water readings: will dissolved oxygen fall below 5 mg/L in the next few hours?

    python ml/fetch_usgs.py --site 421401121480900          # real, calibrated monitor data (public domain)
    python ml/train_water_model.py --csv data/usgs/421401121480900.csv [--hours 3]

Why this task: classifying "is the water bad now" from the same readings only re-learns the threshold
rules. Warning BEFORE oxygen crashes is not circular (the label comes from future readings) and is
what the farm needs. So only hours when DO is still safe count: an alarm after the crash is no warning.

Split by time: earlier years train (tuned with time-series cross-validation), the most recent years
test, so no model sees the future. Logistic Regression, Random Forest and an RBF SVM are compared with
a one-feature baseline (current DO below a cut-off). Each alarm threshold, and the baseline cut-off, is
set on the last 20% of the training years and then used unchanged on the test years. pH and turbidity
are used only when the station records them for most hours. Writes ml/models/water_report.json.

Two public fish-pond datasets were checked first and rejected (docs/DATASETS.md): one repeats a monthly
oxygen value every hour, the other's oxygen sensor reads 0-45 mg/L.
"""
import argparse
import csv
import json
import math
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.base import clone
from sklearn.metrics import (average_precision_score, f1_score, precision_recall_curve, precision_score, recall_score,
                             roc_auc_score)
from sklearn.model_selection import GridSearchCV, TimeSeriesSplit
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

DO_LIMIT = 5.0  # mg/L: FISHUT's dissolved-oxygen warning limit
SVM_MAX_ROWS = 6000  # the SVM trains on an evenly spaced subsample beyond this (RBF cost grows ~n^2)
MODEL_DIR = Path(__file__).parent / "models"
H = timedelta(hours=1)


def read_csv(path: Path) -> dict[datetime, dict]:
    """time (UTC hour) -> {do, temp, ph, turbidity}; blanks become None. Format: fetch_usgs.py."""
    out = {}
    with path.open(newline="") as fh:
        for r in csv.DictReader(fh):
            t = datetime.fromisoformat(r["time"].replace("Z", "")).replace(tzinfo=None)
            out[t] = {k: float(r[k]) if r.get(k) else None for k in ("do", "temp", "ph", "turbidity")}
    return out


def feature_names(extra) -> list[str]:
    return ["do", "temp", *extra, "do_change_1h", "do_change_3h", "temp_change_3h", "hour_sin", "hour_cos"]


def make_samples(series: dict[datetime, dict], hours: int, extra=("ph", "turbidity")):
    """Feature rows for every hour with DO still >= DO_LIMIT and enough past and future readings.
    Label 1 if DO drops below DO_LIMIT at any of the next `hours` hours."""
    X, y, times = [], [], []
    for t, now in sorted(series.items()):
        if now["do"] < DO_LIMIT or any(now[k] is None for k in extra):
            continue
        past1, past3 = series.get(t - H), series.get(t - 3 * H)
        future = [series.get(t + k * H) for k in range(1, hours + 1)]
        if past1 is None or past3 is None or any(f is None for f in future):
            continue
        hour = 2 * math.pi * t.hour / 24
        X.append([now["do"], now["temp"], *[now[k] for k in extra], now["do"] - past1["do"], now["do"] - past3["do"],
                  now["temp"] - past3["temp"], math.sin(hour), math.cos(hour)])
        y.append(int(min(f["do"] for f in future) < DO_LIMIT))
        times.append(t)
    return np.array(X), np.array(y), times


def best_threshold(y_true, score) -> float:
    """Score threshold with the best F1 (the balance of missed crashes and false alarms)."""
    if not y_true.any():
        return 0.5
    p, r, t = precision_recall_curve(y_true, score)
    return float(t[np.argmax((2 * p * r / (p + r + 1e-12))[:-1])])


def scores(y_true, prob, pred) -> dict:
    return {"roc_auc": round(roc_auc_score(y_true, prob), 4), "average_precision": round(average_precision_score(y_true, prob), 4),
            "recall": round(recall_score(y_true, pred, zero_division=0), 4),
            "precision": round(precision_score(y_true, pred, zero_division=0), 4),
            "f1": round(f1_score(y_true, pred, zero_division=0), 4)}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--csv", type=Path, required=True, help="hourly CSV from fetch_usgs.py")
    ap.add_argument("--hours", type=int, default=3, help="how far ahead to warn")
    ap.add_argument("--test-from", help="first test date (default: start of the year holding the last 25%% of cases)")
    args = ap.parse_args()

    series = read_csv(args.csv)
    coverage = {k: np.mean([v[k] is not None for v in series.values()]) for k in ("ph", "turbidity")}
    extra = tuple(k for k, c in coverage.items() if c >= 0.9)
    X, y, times = make_samples(series, args.hours, extra)
    cut = (datetime.fromisoformat(args.test_from) if args.test_from
           else datetime(times[int(len(times) * 0.75)].year, 1, 1))
    tr = np.array([t < cut for t in times])
    # alarm thresholds are picked on the last 20% of the training years, never on the test years
    n_fit = int(tr.sum() * 0.8)
    fit, val = slice(0, n_fit), slice(n_fit, int(tr.sum()))
    print(f"{len(series)} hourly readings; features {feature_names(extra)}")
    print(f"{len(y)} cases ({y.mean():.2%} positive); train {tr.sum()} before {cut:%Y-%m-%d} "
          f"(threshold set on the last {tr.sum() - n_fit}, from {times[n_fit]:%Y-%m-%d}; {y[val].sum()} positive), "
          f"test {(~tr).sum()} ({y[~tr].sum()} positive)")

    # baseline: warn when current DO is below a cut-off (score = -DO), cut-off set the same way
    thr = best_threshold(y[val], -X[val, 0])
    results = {"baseline_do_cutoff": {"cutoff_mg_l": round(float(-thr), 2),
                                      **scores(y[~tr], -X[~tr, 0], -X[~tr, 0] >= thr)}}

    cv = TimeSeriesSplit(4)
    candidates = {
        "logistic_regression": (make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, class_weight="balanced")),
                                {"logisticregression__C": [0.01, 0.1, 1, 10]}),
        "random_forest": (RandomForestClassifier(n_estimators=300, class_weight="balanced_subsample", random_state=0, n_jobs=-1),
                          {"max_depth": [4, 8, None], "min_samples_leaf": [1, 5]}),
        "svm_rbf": (make_pipeline(StandardScaler(), CalibratedClassifierCV(SVC(class_weight="balanced"), ensemble=False)),
                    {"calibratedclassifiercv__estimator__C": [0.3, 1, 3]}),
    }
    for name, (est, grid) in candidates.items():
        # an RBF SVM costs ~n^2: it trains on every k-th row, which keeps time order and class balance
        step = math.ceil(tr.sum() / SVM_MAX_ROWS) if name == "svm_rbf" else 1
        search = GridSearchCV(est, grid, cv=cv, scoring="average_precision", n_jobs=-1).fit(X[tr][::step], y[tr][::step])
        early = clone(search.best_estimator_).fit(X[fit][::step], y[fit][::step])
        thr = best_threshold(y[val], early.predict_proba(X[val])[:, 1])
        prob = search.best_estimator_.predict_proba(X[~tr])[:, 1]  # refit on all training years
        results[name] = {"best_params": search.best_params_, "train_rows": int(len(y[tr][::step])),
                         "alarm_threshold": round(float(thr), 4), **scores(y[~tr], prob, prob >= thr)}
        if name == "random_forest":
            imp = search.best_estimator_.feature_importances_
            results[name]["feature_importance"] = {f: round(float(v), 4) for f, v in
                                                   sorted(zip(feature_names(extra), imp), key=lambda p: -p[1])}
    for name, r in results.items():
        print(f"{name:22s} AUC {r['roc_auc']:.3f}  AP {r['average_precision']:.3f}  recall {r['recall']:.2f}  "
              f"precision {r['precision']:.2f}  F1 {r['f1']:.2f}")

    report = {"data": args.csv.name, "source": "USGS Water Data API, continuous values (public domain)",
              "task": f"DO >= {DO_LIMIT} mg/L now; will it drop below within {args.hours} h?",
              "features": feature_names(extra), "readings": len(series), "cases": int(len(y)),
              "positive_rate": round(float(y.mean()), 4), "test_from": cut.date().isoformat(),
              "thresholds_set_on_cases_from": times[n_fit].date().isoformat(),
              "train_cases": int(tr.sum()), "test_cases": int((~tr).sum()),
              "test_positive_rate": round(float(y[~tr].mean()), 4), "models": results}
    MODEL_DIR.mkdir(exist_ok=True)
    (MODEL_DIR / "water_report.json").write_text(json.dumps(report, indent=2))
    print(f"saved {MODEL_DIR / 'water_report.json'}")


if __name__ == "__main__":
    main()
