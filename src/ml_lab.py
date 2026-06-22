# pyright: reportArgumentType=false, reportOperatorIssue=false
# pyright: reportCallIssue=false, reportReturnType=false
# pyright: reportAttributeAccessIssue=false
# scikit-learn is a soft dependency (numpy fallbacks ship), so missing
# imports are expected when running pyright in an env without it.
# pyright: reportMissingImports=false
"""
Experimental ML helpers for the Data Quality Scorecard (ML Lab - beta).

Read-only consumers of the existing scorecard artifacts. None of the
functions in this module mutate session state, DQR assignments, weights,
or any score that the main flow produces, they only OBSERVE what the
rules-based pipeline computed and surface complementary insights.

scikit-learn is a **soft** dependency. When it is installed (default via
``requirements.txt``), the algorithms can optionally swap in their sklearn
counterparts (IsolationForest, KMeans, PCA, LogisticRegression). When it
is missing, the pure-numpy implementations defined here run instead -
identical interface, slightly less sophisticated but still useful.

What lives here:

Core unsupervised analytics (read-only on the current run):

* :func:`build_rule_flag_matrix` - re-derives the per-row pass/fail
  matrix using the same evaluators the dashboard uses (no semantic drift).
* :func:`compute_row_anomalies` - rank-percentile blend of robust z-score
  on row_score, rare-failure rarity, and an optional IsolationForest score.
* :func:`compute_rule_impact` - exact leave-one-out impact per rule.
* :func:`compute_cde_profile_clusters` - k-means + PCA-2D projection
  (numpy or sklearn).
* :func:`simulate_weight_perturbation` - Dirichlet Monte-Carlo on weights.
* :func:`compare_data_products` - robust-z (MAD) across Data Products.

Run history + drift (track scorecards over time):

* :func:`snapshot_scorecard` - capture a JSON-serialisable snapshot of a
  ScorecardResult that survives across reruns (kept in session state).
* :func:`load_snapshot_from_json` / :func:`load_snapshot_from_csv` -
  import snapshots from files the user previously exported in Step 6.
* :func:`compute_drift` - PSI on row-score histograms + per-rule / per-CDE
  / per-dimension delta tables between two snapshots of the same DP.

Supervised + advanced:

* :func:`train_risk_classifier` - logistic regression (sklearn or numpy)
  on per-rule fail flags to predict RED-row status. Surfaces which rules
  are most DISCRIMINATIVE of RED (vs. merely heavily weighted).
* :func:`recommend_dqrs_for_cde` - neighbor-based DQR recommendation:
  cosine similarity on profile embeddings + dtype/null/distinct heuristics.
* :func:`explain_row_score` - SHAP-like waterfall: per-CDE deficit
  decomposition of ``100 - row_score``.
"""
from __future__ import annotations

import io
import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# =============================================================================
# Optional scikit-learn detection
# =============================================================================

def _sklearn_available() -> bool:
    """Return True iff scikit-learn can be imported.

    Imported lazily inside callers so module load stays fast. Result is
    cheap to recompute - Python's import cache short-circuits subsequent
    calls.
    """
    try:
        import sklearn  # noqa: F401
        return True
    except Exception:  # pragma: no cover - defensive
        return False


def sklearn_status() -> Dict[str, Any]:
    """UI-friendly status of the optional sklearn integration.

    Returned dict carries ``{"available": bool, "version": str | None}``.
    Used by Step 7 to render a soft "sklearn detected - turbo mode
    available" badge.
    """
    if _sklearn_available():
        try:
            import sklearn
            return {"available": True, "version": getattr(sklearn, "__version__", "?")}
        except Exception:  # pragma: no cover
            return {"available": True, "version": "?"}
    return {"available": False, "version": None}


# =============================================================================
# Shared helpers
# =============================================================================

def _rule_id(a) -> str:
    return getattr(a, "rule_id")  # works on both DQRAssignment + CustomDQRAssignment


def _robust_standardize(X: np.ndarray) -> np.ndarray:
    """Median / MAD scaling. Constant columns are passed through as zeros."""
    if X.size == 0:
        return X
    med = np.median(X, axis=0)
    mad = np.median(np.abs(X - med), axis=0)
    mad = np.where(mad > 0, mad, 1.0)
    return (X - med) / (1.4826 * mad)


def _simple_kmeans(
    X: np.ndarray, k: int, max_iter: int = 200, seed: int = 42,
) -> Tuple[np.ndarray, np.ndarray]:
    """Deterministic k-means++ on a small point set. Pure numpy."""
    rng = np.random.default_rng(seed)
    n = X.shape[0]
    if n <= k:
        labels = np.arange(n) % max(k, 1)
        return labels.astype(int), X.copy()
    centers_idx: List[int] = [int(rng.integers(0, n))]
    for _ in range(k - 1):
        dist = np.min(
            np.linalg.norm(X[:, None, :] - X[centers_idx, :], axis=2), axis=1,
        )
        denom = float((dist ** 2).sum())
        if denom <= 0:
            centers_idx.append(int(rng.integers(0, n)))
            continue
        probs = (dist ** 2) / denom
        centers_idx.append(int(rng.choice(n, p=probs)))
    centers = X[centers_idx].copy()
    # Seed ``labels`` so a degenerate ``max_iter=0`` call (or an empty X)
    # returns valid arrays instead of raising UnboundLocalError. The
    # loop overwrites this on the first iteration in the normal case.
    labels = np.zeros(X.shape[0], dtype=int)
    for _ in range(max_iter):
        d = np.linalg.norm(X[:, None, :] - centers, axis=2)
        labels = np.argmin(d, axis=1)
        new_centers = np.array([
            X[labels == i].mean(axis=0) if (labels == i).any() else centers[i]
            for i in range(k)
        ])
        if np.allclose(new_centers, centers, atol=1e-8):
            break
        centers = new_centers
    return labels.astype(int), centers


def _pca_2d(X: np.ndarray) -> np.ndarray:
    """Project rows of X onto the top-2 principal components. Pure numpy SVD."""
    if X.shape[0] < 2 or X.shape[1] == 0:
        return np.zeros((X.shape[0], 2))
    Xc = X - X.mean(axis=0)
    try:
        _, _, Vt = np.linalg.svd(Xc, full_matrices=False)
    except np.linalg.LinAlgError:  # pragma: no cover - extremely rare
        return np.zeros((X.shape[0], 2))
    k = min(2, Vt.shape[0])
    proj = Xc @ Vt[:k].T
    if proj.shape[1] < 2:
        proj = np.hstack([proj, np.zeros((proj.shape[0], 2 - proj.shape[1]))])
    return proj


# =============================================================================
# Pass/fail matrix (re-uses existing evaluators)
# =============================================================================

def build_rule_flag_matrix(dp, config) -> Tuple[pd.DataFrame, Dict[str, Dict[str, Any]]]:
    """Per-row pass/fail flags + per-rule metadata.

    Returns ``(flags, rule_meta)`` where:

    * ``flags`` is a DataFrame aligned to ``dp.df.index`` with one Boolean
      column per *successfully evaluated* rule. ``True`` = the row passed.
    * ``rule_meta`` maps ``rule_id`` → ``{source, label, weight}`` for
      pretty display in the UI.

    Rules that could not be evaluated (incompatible config, missing
    reference dataset, etc.) are silently omitted, they're already
    surfaced as "Not evaluated" / "Not computed" on the dashboard.
    """
    # Imported lazily - keeps this module loadable from unit tests that
    # don't pull in pandas/Snowflake helpers transitively via the engines.
    from src.custom_dqr_engine import evaluate_custom_rules
    from src.dqr_engine import evaluate_all_safe

    parts: List[pd.DataFrame] = []
    rule_meta: Dict[str, Dict[str, Any]] = {}

    if config.assignments:
        std_flags, _ = evaluate_all_safe(dp.df, config.assignments, dp.profiles)
        for a in config.assignments:
            if a.rule_id in std_flags.columns:
                rule_meta[a.rule_id] = {
                    "source": "Standard",
                    "label": f"{a.cde_column} · {a.dimension}",
                    "weight": float(a.weight),
                }
        if std_flags.shape[1] > 0:
            parts.append(std_flags.astype(bool))

    if config.custom_assignments:
        cust_flags, _ = evaluate_custom_rules(
            dp.df, config.custom_assignments, dp.system_code,
        )
        try:
            from config.custom_dqr_catalog import get_available_custom_dqr_rules
            catalog = {r.id: r for r in get_available_custom_dqr_rules(dp.system_code)}
        except Exception:  # pragma: no cover - defensive
            catalog = {}
        for a in config.custom_assignments:
            if a.rule_id in cust_flags.columns:
                rule = catalog.get(a.rule_id)
                rule_meta[a.rule_id] = {
                    "source": "Custom",
                    "label": rule.name if rule is not None else a.rule_id,
                    "weight": float(a.weight),
                }
        if cust_flags.shape[1] > 0:
            parts.append(cust_flags.astype(bool))

    if not parts:
        return pd.DataFrame(index=dp.df.index), rule_meta
    flags = pd.concat(parts, axis=1)
    return flags, rule_meta


# =============================================================================
# (1) Row anomaly detection
# =============================================================================

def compute_row_anomalies(
    dp,
    config,
    result,
    top_n: int = 50,
    rarity_weight: float = 0.7,
    use_sklearn: bool = False,
    flags: Optional[pd.DataFrame] = None,
    rule_meta: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Detect rows whose failure pattern is rare/anomalous.

    Two or three complementary signals are combined into a single
    rank-percentile anomaly score:

    * **Robust z on row_score**: MAD-based standardization of the row
      score (resilient to skewed distributions).
    * **Rare-failure score**: ``Σ -log(fail_rate_i)`` summed over the
      rules the row failed. Failing a rule that 95% of rows pass is far
      more suspicious than failing a rule everyone fails.
    * **(Optional) IsolationForest score**: when ``use_sklearn=True`` and
      scikit-learn is importable, an ``IsolationForest`` is fit on the
      per-row pass/fail matrix and its anomaly score is blended into the
      composite at a 0.30 weight.

    The composite anomaly score is the rank-percentile blend of all
    active signals, so ordering is robust to outliers.
    """
    # ``flags`` / ``rule_meta`` may be supplied by the caller (the ML Lab
    # render() computes the matrix once and passes it to every tab) to avoid
    # rebuilding it per tab; they travel together, so recompute both if either
    # is absent (e.g. called directly without the cache).
    if flags is None or rule_meta is None:
        flags, rule_meta = build_rule_flag_matrix(dp, config)
    if flags.empty:
        return {
            "table": pd.DataFrame(),
            "rule_fail_rate_pct": pd.Series(dtype=float),
            "rule_meta": rule_meta,
            "method": "rare-failure pattern + robust z",
            "n_rows_total": int(dp.row_count),
            "n_rules_evaluated": 0,
            "rarity_weight": float(rarity_weight),
        }

    fails = (~flags).astype(int)
    rule_fail_rate = fails.mean(axis=0)  # 0..1 per rule

    eps = 1e-3
    rarity_weights = -np.log(rule_fail_rate.clip(lower=eps))
    row_rarity = fails.dot(rarity_weights)  # higher = rarer combined failures

    row_scores = result.row_scores
    if len(row_scores) == 0 or not row_scores.index.equals(flags.index):
        # Defensive reindex (dashboard always aligns these, but the lab
        # may be reached via a different code path).
        row_scores = row_scores.reindex(flags.index).fillna(
            float(row_scores.mean()) if len(row_scores) else 0.0
        )

    med = float(np.median(row_scores)) if len(row_scores) else 0.0
    mad = float(np.median(np.abs(row_scores - med))) if len(row_scores) else 0.0
    # ``mad <= 0`` is False for NaN, so we have to check both explicitly;
    # otherwise a NaN MAD silently propagates through robust_z into the
    # output frame.
    if not np.isfinite(mad) or mad <= 0:
        mad = 1.0
    if not np.isfinite(med):
        med = 0.0
    robust_z = (med - row_scores) / (1.4826 * mad)  # >0 = below median (worse)
    robust_z = robust_z.replace([np.inf, -np.inf], np.nan).fillna(0.0)

    rarity_rank = row_rarity.rank(pct=True, method="average").fillna(0.0)
    score_rank = (100 - row_scores).rank(pct=True, method="average").fillna(0.0)
    alpha = max(0.0, min(1.0, float(rarity_weight)))

    sklearn_used = False
    iso_rank: Optional[pd.Series] = None
    if use_sklearn and _sklearn_available():
        try:
            from sklearn.ensemble import IsolationForest
            # IsolationForest on the pass/fail matrix. Failures are encoded
            # as 1 so rare failure patterns sit far from the cloud of
            # all-passing rows.
            iso = IsolationForest(
                n_estimators=120, contamination="auto",
                random_state=42, n_jobs=1,
            )
            X = fails.to_numpy(dtype=float)
            iso.fit(X)
            # decision_function: higher = more normal. Invert so higher = anomalous.
            raw = -iso.decision_function(X)
            iso_rank = pd.Series(raw, index=flags.index).rank(
                pct=True, method="average"
            ).fillna(0.0)
            sklearn_used = True
        except Exception:  # pragma: no cover - sklearn install issue
            iso_rank = None

    if iso_rank is not None:
        # Re-balance: existing pair sums to (alpha + 1-alpha) = 1; we drop
        # 0.30 of mass onto the isolation-forest signal.
        iso_w = 0.30
        anomaly_score = (
            (1.0 - iso_w) * (alpha * rarity_rank + (1.0 - alpha) * score_rank)
            + iso_w * iso_rank
        )
    else:
        anomaly_score = alpha * rarity_rank + (1.0 - alpha) * score_rank

    # Per-row top rare failures (up to 3), ranked by rarity weight.
    rule_rarity_lookup = rarity_weights.to_dict()

    fail_cols = list(fails.columns)
    fail_np = fails.to_numpy(dtype=bool)
    rarity_arr = np.array([rule_rarity_lookup[c] for c in fail_cols])

    def _label(rid: str) -> str:
        meta = rule_meta.get(rid, {})
        src = meta.get("source", "")
        return f"{src[:3].upper()} · {meta.get('label', rid)}" if src else meta.get("label", rid)

    top_rare: List[str] = []
    for i in range(fail_np.shape[0]):
        row = fail_np[i]
        if not row.any():
            top_rare.append("-")
            continue
        # Indices of failed rules, sorted by descending rarity weight.
        idxs = np.where(row)[0]
        idxs = idxs[np.argsort(-rarity_arr[idxs])][:3]
        top_rare.append(" | ".join(_label(fail_cols[j]) for j in idxs))

    out_data = {
        "row_score": row_scores.round(2),
        "robust_z": robust_z.round(2),
        "rarity_score": row_rarity.round(2),
        "anomaly_score": anomaly_score.round(3),
        "n_rules_failed": fails.sum(axis=1).astype(int),
        "top_rare_failures": top_rare,
    }
    if iso_rank is not None:
        out_data["iso_forest_score"] = iso_rank.round(3)
    out = pd.DataFrame(out_data)
    out = out.sort_values("anomaly_score", ascending=False).head(int(top_n))

    # Per-rule fail-rate table (sorted by rarity) for the right-hand panel.
    rule_fail_rate_pct = (rule_fail_rate * 100.0).round(2)
    rule_fail_rate_pct.name = "fail_rate_pct"

    method = "rare-failure pattern + robust z"
    if sklearn_used:
        method += " + IsolationForest"

    return {
        "table": out,
        "rule_fail_rate_pct": rule_fail_rate_pct.sort_values(),
        "rule_meta": rule_meta,
        "method": method,
        "n_rows_total": int(dp.row_count),
        "n_rules_evaluated": int(flags.shape[1]),
        "rarity_weight": float(alpha),
        "sklearn_used": bool(sklearn_used),
    }


# =============================================================================
# (2) Rule impact - exact leave-one-out
# =============================================================================

def compute_rule_impact(config, result) -> pd.DataFrame:
    """Per-rule leave-one-out impact within each source.

    Because each source's sub-score is a linear combination of rule
    pass-rates by their normalized weights, removing rule *i* and
    renormalizing the remaining weights gives the EXACT new sub-score, no simulation needed.

    Returns one tidy DataFrame containing both Standard and Custom rules:

    * ``baseline_source_score`` - current sub-score for that source.
    * ``loo_source_score`` - sub-score after removing this single rule.
    * ``delta_vs_baseline`` - ``loo - baseline``. Negative = the rule is
      LIFTING the score (failing it would hurt). Positive = the rule is
      DRAGGING the score (its low pass-rate is pulling the source down).
    * ``criticality`` - ``|delta|`` - magnitude of the rule's influence.
    * ``potential_uplift_pct`` - how many points the source sub-score
      would gain if this rule were 100% passing (``w_i * (1 - pr_i) * 100``).
    """
    rows: List[Dict[str, Any]] = []

    def _section(assignments, pass_rates_pct, source_label, label_fn):
        # Restrict to *evaluated* rules so the baseline this function
        # computes matches the dashboard's source sub-score exactly.
        # Non-evaluated rules (incompatible config / missing reference data
        # / runtime error) are excluded here for the same reason
        # ``compute_scorecard`` excludes them when normalizing weights.
        assignments = [a for a in assignments if _rule_id(a) in pass_rates_pct]
        n = len(assignments)
        if n == 0:
            return
        w = np.array([a.weight for a in assignments], dtype=float)
        total_w = float(w.sum())
        norm = (w / total_w) if total_w > 0 else np.ones(n) / max(n, 1)
        pr = np.array(
            [pass_rates_pct.get(_rule_id(a), 0.0) / 100.0 for a in assignments],
            dtype=float,
        )
        baseline = float((norm * pr).sum() * 100.0)

        for i, a in enumerate(assignments):
            mask = np.ones(n, dtype=bool)
            mask[i] = False
            if not mask.any():
                loo = 0.0
            else:
                w_loo = w[mask]
                total_loo = float(w_loo.sum())
                if total_loo > 0:
                    norm_loo = w_loo / total_loo
                else:
                    norm_loo = np.ones(mask.sum()) / max(mask.sum(), 1)
                loo = float((norm_loo * pr[mask]).sum() * 100.0)

            current_pr = float(pr[i] * 100.0)
            potential_uplift = float(norm[i] * (1.0 - pr[i]) * 100.0)
            rows.append({
                "source": source_label,
                "rule_id": _rule_id(a),
                "label": label_fn(a),
                "weight_pct": round(float(a.weight), 2),
                "pass_rate_pct": round(current_pr, 2),
                "baseline_source_score": round(baseline, 2),
                "loo_source_score": round(loo, 2),
                "delta_vs_baseline": round(loo - baseline, 2),
                "criticality": round(abs(loo - baseline), 2),
                "potential_uplift_pct": round(potential_uplift, 2),
            })

    _section(
        config.assignments,
        result.rule_pass_rates,
        "Standard",
        lambda a: f"{a.cde_column} · {a.dimension}",
    )
    _section(
        config.custom_assignments,
        result.custom_rule_pass_rates,
        "Custom",
        lambda a: a.rule_id,
    )

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(
        ["source", "criticality"], ascending=[True, False],
    )


# =============================================================================
# (3) CDE profile clustering
# =============================================================================

def compute_cde_profile_clusters(
    dp,
    config,
    result,
    n_clusters: int = 3,
    seed: int = 42,
    use_sklearn: bool = False,
) -> Dict[str, Any]:
    """Cluster the selected CDEs by their profile + score signature.

    Features per CDE:

    * ``null_pct``
    * ``distinct_ratio`` (distinct / total rows, %)
    * ``duplicate_ratio`` (duplicates / non-null rows, %)
    * ``cde_score`` (mean pass-rate of the rules tied to this CDE)
    * One-hot of ``column_type_group``

    Features are robust-standardized (median / MAD), clustered via a tiny
    deterministic k-means, and projected to 2D via SVD-PCA. The 2D
    coordinates are what the Streamlit scatter uses.
    """
    cdes = [c for c in (config.cdes or []) if c in dp.profiles]
    if not cdes:
        return {
            "table": pd.DataFrame(),
            "n_clusters": 0,
            "feature_columns": [],
            "explained_variance": (0.0, 0.0),
        }

    rows = []
    for c in cdes:
        p = dp.profiles[c]
        total = max(int(p.total_rows), 1)
        non_null = max(total - int(p.null_count), 1)
        rows.append({
            "cde": c,
            "type": p.column_type_group,
            "null_pct": float(p.null_pct),
            "distinct_ratio_pct": float(p.distinct_count) / total * 100.0,
            "duplicate_ratio_pct": float(p.duplicate_count) / non_null * 100.0,
            "cde_score": float(result.cde_scores.get(c, 0.0)),
        })
    df = pd.DataFrame(rows)

    numeric_cols = ["null_pct", "distinct_ratio_pct", "duplicate_ratio_pct", "cde_score"]
    type_dummies = pd.get_dummies(df["type"], prefix="t").astype(float)
    feat = pd.concat([df[numeric_cols], type_dummies], axis=1)
    X = feat.to_numpy(dtype=float)

    Xs = _robust_standardize(X)

    n = Xs.shape[0]
    k = max(1, min(int(n_clusters), n))

    sklearn_used = False
    # Bind to safe defaults so a partial sklearn-try failure can't leave
    # these unset before the numpy fall-through assigns them.
    labels: np.ndarray = np.zeros(n, dtype=int)
    proj: np.ndarray = np.zeros((n, 2))
    ev: List[float] = [0.0, 0.0]
    if use_sklearn and _sklearn_available() and n > 1:
        try:
            from sklearn.cluster import KMeans
            from sklearn.decomposition import PCA
            model = KMeans(n_clusters=k, n_init=10, random_state=int(seed))
            labels = model.fit_predict(Xs).astype(int)
            pca = PCA(n_components=min(2, Xs.shape[1]))
            proj_part = pca.fit_transform(Xs)
            if proj_part.shape[1] < 2:
                proj_part = np.hstack([
                    proj_part,
                    np.zeros((proj_part.shape[0], 2 - proj_part.shape[1])),
                ])
            proj = proj_part
            ev_list = list(pca.explained_variance_ratio_)
            while len(ev_list) < 2:
                ev_list.append(0.0)
            ev = [float(ev_list[0]), float(ev_list[1])]
            sklearn_used = True
        except Exception:  # pragma: no cover - sklearn install issue
            sklearn_used = False
            labels = np.zeros(0, dtype=int)  # placeholder; fall through
    if not sklearn_used:
        if n > 1:
            labels, _centers = _simple_kmeans(Xs, k, seed=seed)
        else:
            labels = np.zeros(n, dtype=int)
        proj = _pca_2d(Xs)
        if n > 1:
            Xc = Xs - Xs.mean(axis=0)
            total_var = float((Xc ** 2).sum()) or 1.0
            try:
                _, S, _ = np.linalg.svd(Xc, full_matrices=False)
                var = (S ** 2)
                ev_arr = (var[: min(2, len(var))] / total_var).tolist()
                while len(ev_arr) < 2:
                    ev_arr.append(0.0)
                ev = [float(ev_arr[0]), float(ev_arr[1])]
            except np.linalg.LinAlgError:  # pragma: no cover - defensive
                ev = [0.0, 0.0]
        else:
            ev = [0.0, 0.0]

    out = df.copy()
    out["cluster"] = labels.astype(int)
    out["pc1"] = proj[:, 0]
    out["pc2"] = proj[:, 1]
    return {
        "table": out.round(3),
        "n_clusters": int(k),
        "feature_columns": numeric_cols + list(type_dummies.columns),
        # Clamp to [0, 1]: the ratios are mathematically bounded there, but
        # float error (or a degenerate single-row frame) can nudge them just
        # outside, which would render as e.g. "100.0001%" / a negative %.
        "explained_variance": (
            float(np.clip(ev[0], 0.0, 1.0)),
            float(np.clip(ev[1], 0.0, 1.0)),
        ),
        "sklearn_used": bool(sklearn_used),
    }


# =============================================================================
# (4) Weight perturbation Monte-Carlo
# =============================================================================

def simulate_weight_perturbation(
    config,
    result,
    n_simulations: int = 300,
    jitter: float = 0.25,
    seed: int = 42,
) -> Dict[str, Any]:
    """Monte-Carlo perturbation of the Standard-source rule weights.

    Each sample draws weights from a Dirichlet anchored at the current
    normalized weights. The sub-score is the linear combination of the
    sampled weights and the current pass-rates.

    Output is the histogram-ready array of resulting scores + summary stats
    (mean / std / p05 / p95 / min / max) and the baseline (= current
    Standard sub-score).

    ``seed`` defaults to a FIXED value (42) so the Monte-Carlo is reproducible
    across reruns - the histogram is stable instead of re-randomizing on every
    widget interaction. This is intentional and deliberately not exposed as a
    UI control; pass a different ``seed`` to vary the draw.
    """
    assignments = list(config.assignments or [])
    if not assignments or not result.rule_pass_rates:
        return {
            "scores": np.array([], dtype=float),
            "baseline": None,
            "summary": {},
            "n_simulations": 0,
            "jitter": float(jitter),
        }

    rng = np.random.default_rng(seed)
    w = np.array([a.weight for a in assignments], dtype=float)
    if w.sum() <= 0:
        w = np.ones_like(w)
    w_norm = w / w.sum()
    pr = np.array(
        [result.rule_pass_rates.get(a.rule_id, 0.0) / 100.0 for a in assignments],
        dtype=float,
    )
    baseline = float((w_norm * pr).sum() * 100.0)

    # Map UI jitter (0..1) to Dirichlet concentration. Higher concentration
    # = tighter cluster around current weights (less jitter).
    j = max(0.01, min(1.0, float(jitter)))
    concentration = max(2.0, (1.0 - j) * 80.0 + 2.0)
    alpha = w_norm * concentration + 1e-3
    samples = rng.dirichlet(alpha, size=int(n_simulations))
    # NumPy 2.0.x emits spurious divide/overflow/invalid FPE warnings from the
    # ``@`` matmul path here even though every input is a finite probability in
    # [0, 1] and the result is correct. Use ``.dot`` under errstate so the
    # warning log stays clean (verified: scores are finite and identical).
    with np.errstate(divide="ignore", over="ignore", invalid="ignore"):
        scores = samples.dot(pr) * 100.0

    return {
        "scores": scores,
        "baseline": baseline,
        "summary": {
            "mean": float(scores.mean()),
            "std": float(scores.std()),
            "p05": float(np.percentile(scores, 5)),
            "p95": float(np.percentile(scores, 95)),
            "min": float(scores.min()),
            "max": float(scores.max()),
        },
        "n_simulations": int(n_simulations),
        "jitter": float(j),
    }


# =============================================================================
# (5) Cross-Data-Product comparison
# =============================================================================

def compare_data_products(scorecards: Dict[str, Any]) -> pd.DataFrame:
    """Robust-z (MAD) anomaly detection across Data Products.

    With few DPs (n ≈ 3 typical) z-scores are noisy; |z| > 1.5 is used as
    a soft "Anomalous" cutoff. The status column is advisory - a single
    low-scoring DP doesn't automatically mean its quality is bad, it may
    just have stricter rules or thornier data.
    """
    if not scorecards:
        return pd.DataFrame()
    rows = []
    for code, r in scorecards.items():
        total = max(int(r.total_rows), 1)
        rows.append({
            "data_product": code,
            "overall_score": round(float(r.overall_score), 2),
            "rows_green_pct": round(r.rows_green / total * 100.0, 2),
            "rows_yellow_pct": round(r.rows_yellow / total * 100.0, 2),
            "rows_red_pct": round(r.rows_red / total * 100.0, 2),
            "total_rows": int(r.total_rows),
            "n_rules_std": len(r.rule_pass_rates),
            "n_rules_cust": len(r.custom_rule_pass_rates),
        })
    df = pd.DataFrame(rows)
    if len(df) >= 2:
        s = df["overall_score"].to_numpy(dtype=float)
        med = float(np.median(s))
        mad = float(np.median(np.abs(s - med)))
        # ``or 1.0`` was OK for ``mad == 0`` but ``NaN or 1.0`` is still NaN.
        # Guard explicitly so NaN scores don't leak into the dashboard.
        if not np.isfinite(mad) or mad <= 0:
            mad = 1.0
        if not np.isfinite(med):
            med = 0.0
        z = ((s - med) / (1.4826 * mad))
        df["robust_z"] = pd.Series(z).replace(
            [np.inf, -np.inf], np.nan
        ).fillna(0.0).round(2).to_numpy()
        df["status"] = np.where(
            np.abs(df["robust_z"]) > 1.5, "Anomalous", "In-line",
        )
    else:
        df["robust_z"] = 0.0
        df["status"] = "Single DP"
    return df.sort_values("overall_score").reset_index(drop=True)


# =============================================================================
# (6) Run history - snapshot, import, export
# =============================================================================

_HIST_HIST_BINS = 20  # bins used when capturing row_score histograms


def _row_score_summary(row_scores: pd.Series) -> Optional[Dict[str, Any]]:
    """Compact summary of a per-row score distribution.

    Captures enough information to recompute PSI later without storing
    every row, the lab tracks snapshots over time and a full row_scores
    array would blow up session state on large data products.
    """
    if row_scores is None or len(row_scores) == 0:
        return None
    arr = np.asarray(row_scores, dtype=float)
    counts, bin_edges = np.histogram(arr, bins=_HIST_HIST_BINS, range=(0.0, 100.0))
    return {
        "bin_edges": [float(x) for x in bin_edges.tolist()],
        "counts": [int(x) for x in counts.tolist()],
        "mean": float(np.mean(arr)),
        "std": float(np.std(arr)),
        "p05": float(np.percentile(arr, 5)),
        "p25": float(np.percentile(arr, 25)),
        "p50": float(np.percentile(arr, 50)),
        "p75": float(np.percentile(arr, 75)),
        "p95": float(np.percentile(arr, 95)),
        "n": int(len(arr)),
    }


def snapshot_scorecard(
    dp_code: str,
    dp: Any,
    result: Any,
    label: Optional[str] = None,
) -> Dict[str, Any]:
    """Capture a JSON-serialisable snapshot of one DP's current scorecard.

    The dict is small enough to keep dozens of historical snapshots in
    ``st.session_state`` without bloating memory. ``label`` is whatever
    free-form string the user wants ("baseline", "after-fix-A1", ...);
    defaults to the timestamp.
    """
    ts = datetime.now().isoformat(timespec="seconds")
    return {
        "id": f"snap_{ts}_{dp_code}",
        "label": label or ts,
        "timestamp": ts,
        "source": "session",
        "dp_code": dp_code,
        "dp_name": getattr(dp, "name", dp_code),
        "overall_score": float(result.overall_score),
        "threshold_green": float(result.threshold_green),
        "threshold_yellow": float(result.threshold_yellow),
        "total_rows": int(result.total_rows),
        "rows_green": int(result.rows_green),
        "rows_yellow": int(result.rows_yellow),
        "rows_red": int(result.rows_red),
        "standard_score": (
            float(result.standard_score) if result.standard_score is not None else None
        ),
        "custom_score": (
            float(result.custom_score) if result.custom_score is not None else None
        ),
        "rule_pass_rates": {k: float(v) for k, v in result.rule_pass_rates.items()},
        "custom_rule_pass_rates": {
            k: float(v) for k, v in result.custom_rule_pass_rates.items()
        },
        "cde_scores": {k: float(v) for k, v in result.cde_scores.items()},
        "dimension_scores": {k: float(v) for k, v in result.dimension_scores.items()},
        "row_score_hist": _row_score_summary(result.row_scores),
    }


def load_snapshot_from_json(file_bytes: bytes, source: str = "upload-json") -> Dict[str, Any]:
    """Parse a JSON file previously exported by Step 6 into a snapshot.

    The Step 6 export schema is:
        ``{exported_at, system_code, data_product_name, row_count, ...,
           summary: {overall_score, rows_green, rows_yellow, rows_red,
                     cde_scores, dimension_scores, ...},
           assignments: [{cde_column, dimension, weight_pct, pass_rate_pct, ...}]}``

    The mapped snapshot mirrors :func:`snapshot_scorecard`'s schema -
    apart from ``row_score_hist`` (which the JSON export does not carry).
    Drift on row-score distributions therefore requires session snapshots
    or CSV uploads; the per-rule / per-CDE drift still works either way.
    """
    payload = json.loads(file_bytes.decode("utf-8"))
    summary = payload.get("summary", {}) or {}
    ts = payload.get("exported_at") or datetime.now().isoformat(timespec="seconds")
    dp_code = payload.get("system_code", "?")
    rule_pass_rates: Dict[str, float] = {}
    for a in payload.get("assignments", []) or []:
        rid = f"{a.get('cde_column')}::{a.get('dimension')}"
        rule_pass_rates[rid] = float(a.get("pass_rate_pct", 0.0))
    rows_green = int(summary.get("rows_green", 0))
    rows_yellow = int(summary.get("rows_yellow", 0))
    rows_red = int(summary.get("rows_red", 0))
    return {
        "id": f"snap_{ts}_{dp_code}_json",
        "label": f"{dp_code} · {ts}",
        "timestamp": ts,
        "source": source,
        "dp_code": dp_code,
        "dp_name": payload.get("data_product_name", dp_code),
        "overall_score": float(summary.get("overall_score", 0.0)),
        "threshold_green": float((payload.get("thresholds") or {}).get("green", 80)),
        "threshold_yellow": float((payload.get("thresholds") or {}).get("yellow", 60)),
        "total_rows": int(payload.get("row_count", rows_green + rows_yellow + rows_red)),
        "rows_green": rows_green,
        "rows_yellow": rows_yellow,
        "rows_red": rows_red,
        "standard_score": None,
        "custom_score": None,
        "rule_pass_rates": rule_pass_rates,
        "custom_rule_pass_rates": {},
        "cde_scores": {k: float(v) for k, v in (summary.get("cde_scores") or {}).items()},
        "dimension_scores": {k: float(v) for k, v in (summary.get("dimension_scores") or {}).items()},
        "row_score_hist": None,  # not present in JSON exports
    }


def load_snapshot_from_csv(
    file_bytes: bytes,
    dp_code: str = "?",
    label: Optional[str] = None,
) -> Dict[str, Any]:
    """Parse a CSV exported by Step 6 (rows + row_scores + per-rule cols)
    into a snapshot.

    The Step 6 CSV has ``_row_score`` + ``_status`` columns followed by one
    column per evaluated rule (``STD · CDE · Dim (w=X%)`` /
    ``CUSTOM · id · name (w=X%)``). We reconstruct:

    * The row-score histogram (full fidelity, since this file *does*
      carry the per-row scores).
    * Per-rule pass rates by averaging the rule columns (100/0).

    The threshold values used to bucket rows aren't in the CSV, so we
    fall back to the project defaults (80 / 60).
    """
    df = pd.read_csv(io.BytesIO(file_bytes))
    ts = datetime.now().isoformat(timespec="seconds")
    if "_row_score" not in df.columns:
        raise ValueError(
            "CSV is missing the '_row_score' column - this loader expects "
            "a file exported from Step 6 (Dashboard ▸ CSV)."
        )
    row_scores = pd.to_numeric(df["_row_score"], errors="coerce").dropna()
    rule_cols = [c for c in df.columns if c.startswith(("STD · ", "CUSTOM · "))]
    rule_pass_rates: Dict[str, float] = {}
    custom_rule_pass_rates: Dict[str, float] = {}
    for c in rule_cols:
        try:
            mean_pct = float(pd.to_numeric(df[c], errors="coerce").dropna().mean())
        except Exception:
            continue
        # Recover a stable rule-id from the header.
        parts = c.split(" · ")
        if c.startswith("STD · ") and len(parts) >= 3:
            cde, dim_part = parts[1], parts[2].split(" (w=")[0]
            rid = f"{cde}::{dim_part}"
            rule_pass_rates[rid] = mean_pct
        elif c.startswith("CUSTOM · ") and len(parts) >= 2:
            rid = parts[1]
            custom_rule_pass_rates[rid] = mean_pct
    rows_green = int(((row_scores >= 80).sum()))
    rows_red = int((row_scores < 60).sum())
    rows_yellow = int(len(row_scores) - rows_green - rows_red)
    return {
        "id": f"snap_{ts}_{dp_code}_csv",
        "label": label or f"{dp_code} · {ts} (csv)",
        "timestamp": ts,
        "source": "upload-csv",
        "dp_code": dp_code,
        "dp_name": dp_code,
        "overall_score": float(row_scores.mean()) if len(row_scores) else 0.0,
        "threshold_green": 80.0,
        "threshold_yellow": 60.0,
        "total_rows": int(len(row_scores)),
        "rows_green": rows_green,
        "rows_yellow": rows_yellow,
        "rows_red": rows_red,
        "standard_score": None,
        "custom_score": None,
        "rule_pass_rates": rule_pass_rates,
        "custom_rule_pass_rates": custom_rule_pass_rates,
        "cde_scores": {},
        "dimension_scores": {},
        "row_score_hist": _row_score_summary(row_scores),
    }


def _psi_from_histograms(
    counts_a: List[int],
    counts_b: List[int],
    eps: float = 1e-4,
) -> float:
    """Population Stability Index between two histograms.

    PSI = Σ (pB − pA) · ln(pB / pA), clipped to avoid log(0). Conventional
    interpretation:

    * < 0.1 → negligible drift
    * 0.1 – 0.25 → moderate drift, worth a look
    * > 0.25 → significant drift, investigate
    """
    a = np.array(counts_a, dtype=float)
    b = np.array(counts_b, dtype=float)
    if a.sum() == 0 or b.sum() == 0:
        return 0.0
    pa = a / a.sum()
    pb = b / b.sum()
    pa = np.clip(pa, eps, None)
    pb = np.clip(pb, eps, None)
    return float(((pb - pa) * np.log(pb / pa)).sum())


def _ks_from_histograms(counts_a: List[int], counts_b: List[int]) -> float:
    """KS-style statistic on histograms, the L∞ distance between the
    cumulative distributions. Crude but cheap when only histograms are
    retained.
    """
    a = np.array(counts_a, dtype=float)
    b = np.array(counts_b, dtype=float)
    if a.sum() == 0 or b.sum() == 0:
        return 0.0
    ca = np.cumsum(a / a.sum())
    cb = np.cumsum(b / b.sum())
    return float(np.max(np.abs(ca - cb)))


def compute_drift(
    snap_a: Dict[str, Any],
    snap_b: Dict[str, Any],
    rule_delta_threshold: float = 5.0,
) -> Dict[str, Any]:
    """Quantify drift between two snapshots of (typically) the same DP.

    Output:

    * ``overall_score_delta`` - B − A
    * ``psi`` / ``ks`` - distribution drift on row scores (or ``None`` if
      either snapshot lacks the histogram)
    * ``rule_table`` - per-rule pass-rate Δ + ``flagged`` boolean
    * ``cde_table`` - per-CDE score Δ
    * ``dimension_table`` - per-dimension score Δ
    """
    psi = None
    ks = None
    histA = snap_a.get("row_score_hist")
    histB = snap_b.get("row_score_hist")
    if histA and histB:
        # Both snapshots must share the same bin edges (they do - we use a
        # fixed 0..100 range), so the histograms are directly comparable.
        psi = _psi_from_histograms(histA["counts"], histB["counts"])
        ks = _ks_from_histograms(histA["counts"], histB["counts"])

    def _table(map_a: Dict[str, float], map_b: Dict[str, float], key_label: str,
               flag_threshold: float) -> pd.DataFrame:
        keys = sorted(set(map_a.keys()) | set(map_b.keys()))
        if not keys:
            return pd.DataFrame(
                columns=[key_label, "score_a", "score_b", "delta", "flagged"]
            )
        rows = []
        for k in keys:
            a = float(map_a.get(k)) if k in map_a else np.nan
            b = float(map_b.get(k)) if k in map_b else np.nan
            delta = (b - a) if (not np.isnan(a) and not np.isnan(b)) else np.nan
            flagged = (not np.isnan(delta)) and (abs(delta) >= flag_threshold)
            # NB: keep these as numeric NaN (not Python None) so the
            # resulting DataFrame columns stay float64 and ``.abs()`` in
            # sort_values' key= works elementwise. Mixing None + float
            # promotes the column to object dtype and breaks the sort
            # with ``TypeError: bad operand type for abs(): 'NoneType'``.
            rows.append({
                key_label: k,
                "score_a": round(a, 2) if not np.isnan(a) else np.nan,
                "score_b": round(b, 2) if not np.isnan(b) else np.nan,
                "delta": round(delta, 2) if not np.isnan(delta) else np.nan,
                "flagged": bool(flagged),
            })
        df = pd.DataFrame(rows)
        # Defence in depth: coerce delta to numeric before sorting so a
        # downstream change to the dict shape can't reintroduce the bug.
        return df.sort_values(
            "delta",
            key=lambda s: pd.to_numeric(s, errors="coerce").abs(),
            ascending=False, na_position="last",
        )

    rule_table = _table(
        {**snap_a.get("rule_pass_rates", {}), **snap_a.get("custom_rule_pass_rates", {})},
        {**snap_b.get("rule_pass_rates", {}), **snap_b.get("custom_rule_pass_rates", {})},
        "rule_id", rule_delta_threshold,
    )
    cde_table = _table(
        snap_a.get("cde_scores", {}) or {},
        snap_b.get("cde_scores", {}) or {},
        "cde", rule_delta_threshold,
    )
    dim_table = _table(
        snap_a.get("dimension_scores", {}) or {},
        snap_b.get("dimension_scores", {}) or {},
        "dimension", rule_delta_threshold,
    )

    return {
        "snapshot_a_id": snap_a.get("id"),
        "snapshot_b_id": snap_b.get("id"),
        "overall_score_delta": round(
            float(snap_b.get("overall_score", 0.0))
            - float(snap_a.get("overall_score", 0.0)),
            2,
        ),
        "psi": psi,
        "ks": ks,
        "rule_table": rule_table,
        "cde_table": cde_table,
        "dimension_table": dim_table,
        "rule_delta_threshold": float(rule_delta_threshold),
    }


# =============================================================================
# (7) Supervised risk classifier (RED row probability)
# =============================================================================

def _logreg_numpy(
    X: np.ndarray,
    y: np.ndarray,
    lr: float = 0.1,
    n_iter: int = 300,
    l2: float = 0.01,
) -> Tuple[np.ndarray, float]:
    """Tiny pure-numpy logistic regression with L2.

    Used as a fallback when scikit-learn is unavailable. Coefficients are
    interpreted exactly as sklearn's: positive → feature value increases
    the probability of the positive class (RED row).
    """
    n, d = X.shape
    w = np.zeros(d, dtype=float)
    b = 0.0
    y_f = y.astype(float)
    for _ in range(n_iter):
        z = np.clip(X @ w + b, -50, 50)
        p = 1.0 / (1.0 + np.exp(-z))
        gw = (X.T @ (p - y_f)) / max(n, 1) + l2 * w
        gb = float((p - y_f).mean())
        w -= lr * gw
        b -= lr * gb
    return w, float(b)


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -50, 50)))


def train_risk_classifier(
    dp,
    config,
    result,
    use_sklearn: bool = False,
    flags: Optional[pd.DataFrame] = None,
    rule_meta: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Train a logistic regression that predicts RED-row status.

    Features: per-row pass/fail flags (1 = the rule FAILED for this row).
    Target: ``row_score < threshold_yellow`` (RED).

    The model's value is **discrimination**: its coefficients tell you
    which rule FAILURES best segregate the RED rows, which can differ
    sharply from the rule's configured weight. A small-weight rule with a
    huge coefficient is a high-signal rule that is currently
    *underweighted*; a high-weight rule with a coefficient near zero
    barely informs RED status (its failures coincide with everyone else's).

    Output:
    * ``coef_table`` - DataFrame ``[rule_id, label, weight_pct, coefficient,
      odds_ratio]`` sorted by |coefficient|.
    * ``intercept`` - float
    * ``accuracy``, ``base_rate`` - sanity metrics
    * ``predictions`` - Series ``risk_probability`` per row (0..1)
    * ``confusion`` - dict ``{tn, fp, fn, tp}``
    * ``sklearn_used`` - bool
    """
    if flags is None or rule_meta is None:
        flags, rule_meta = build_rule_flag_matrix(dp, config)
    if flags.empty or len(result.row_scores) == 0:
        return {
            "coef_table": pd.DataFrame(),
            "intercept": 0.0,
            "accuracy": 0.0,
            "base_rate": 0.0,
            "predictions": pd.Series(dtype=float),
            "confusion": {"tn": 0, "fp": 0, "fn": 0, "tp": 0},
            "sklearn_used": False,
            "n_rules": 0,
            "threshold_yellow": float(result.threshold_yellow),
        }

    fails = (~flags).astype(int)
    X = fails.to_numpy(dtype=float)
    y = (result.row_scores < result.threshold_yellow).astype(int).to_numpy()
    base_rate = float(y.mean()) if len(y) else 0.0

    coef: np.ndarray
    intercept: float
    sklearn_used = False
    if use_sklearn and _sklearn_available() and len(np.unique(y)) > 1:
        try:
            from sklearn.linear_model import LogisticRegression
            clf = LogisticRegression(
                penalty="l2", C=1.0, solver="lbfgs", max_iter=500,
            )
            clf.fit(X, y)
            coef = clf.coef_[0]
            intercept = float(clf.intercept_[0])
            sklearn_used = True
        except Exception:  # pragma: no cover - sklearn install issue
            coef, intercept = _logreg_numpy(X, y)
    elif len(np.unique(y)) > 1:
        coef, intercept = _logreg_numpy(X, y)
    else:
        # Degenerate target, no RED rows at all (or all RED). The model
        # is uninformative; emit zeros so the UI still has something to
        # render.
        coef = np.zeros(X.shape[1])
        intercept = float(np.log((base_rate + 1e-3) / (1 - base_rate + 1e-3)))

    probs = _sigmoid(X @ coef + intercept)
    preds = (probs >= 0.5).astype(int)
    tp = int(((preds == 1) & (y == 1)).sum())
    tn = int(((preds == 0) & (y == 0)).sum())
    fp = int(((preds == 1) & (y == 0)).sum())
    fn = int(((preds == 0) & (y == 1)).sum())
    accuracy = float((preds == y).mean()) if len(y) else 0.0

    feat_cols = list(fails.columns)
    weight_lookup = {rid: m.get("weight", 0.0) for rid, m in rule_meta.items()}
    label_lookup = {rid: m.get("label", rid) for rid, m in rule_meta.items()}
    source_lookup = {rid: m.get("source", "") for rid, m in rule_meta.items()}
    coef_table = pd.DataFrame({
        "rule_id": feat_cols,
        "source": [source_lookup.get(rid, "") for rid in feat_cols],
        "label": [label_lookup.get(rid, rid) for rid in feat_cols],
        "weight_pct": [float(weight_lookup.get(rid, 0.0)) for rid in feat_cols],
        "coefficient": [float(c) for c in coef],
        "odds_ratio": [float(np.exp(np.clip(c, -50, 50))) for c in coef],
    })
    coef_table["abs_coef"] = coef_table["coefficient"].abs()
    coef_table = coef_table.sort_values("abs_coef", ascending=False).drop(columns=["abs_coef"])

    predictions = pd.Series(probs, index=flags.index, name="risk_probability")

    return {
        "coef_table": coef_table,
        "intercept": float(intercept),
        "accuracy": float(accuracy),
        "base_rate": base_rate,
        "predictions": predictions.round(4),
        "confusion": {"tn": tn, "fp": fp, "fn": fn, "tp": tp},
        "sklearn_used": bool(sklearn_used),
        "n_rules": int(X.shape[1]),
        "threshold_yellow": float(result.threshold_yellow),
    }


# =============================================================================
# (8) DQR recommendations by profile similarity + heuristics
# =============================================================================

def _profile_feature_vector(profile) -> Tuple[np.ndarray, List[str]]:
    """Convert a ColumnProfile to a numeric feature vector for similarity.

    Features: null_pct (0..100), distinct_ratio (0..100), duplicate_ratio
    (0..100), plus a 9-bucket one-hot of column_type_group.
    """
    total = max(int(profile.total_rows), 1)
    non_null = max(total - int(profile.null_count), 1)
    null_pct = float(profile.null_pct)
    distinct_ratio = float(profile.distinct_count) / total * 100.0
    duplicate_ratio = float(profile.duplicate_count) / non_null * 100.0
    type_buckets = [
        "numeric", "integer", "float", "datetime", "date",
        "string", "categorical", "id", "boolean",
    ]
    onehot = [1.0 if profile.column_type_group == t else 0.0 for t in type_buckets]
    return (
        np.array([null_pct, distinct_ratio, duplicate_ratio] + onehot, dtype=float),
        ["null_pct", "distinct_ratio_pct", "duplicate_ratio_pct"] + [f"t_{t}" for t in type_buckets],
    )


def _heuristic_dimensions(profile) -> List[Tuple[str, str]]:
    """Profile-based heuristic DQR suggestions.

    Returns a list of ``(dimension, reason)`` pairs. Reasons are short,
    user-facing strings that the UI can render verbatim. Complements (but
    does not replace) :func:`config.dqr_catalog.suggest_dimensions_for`.
    """
    out: List[Tuple[str, str]] = []
    if profile.null_pct > 10.0:
        out.append((
            "Completeness",
            f"null_pct={profile.null_pct:.1f}% > 10%",
        ))
    name_low = (profile.name or "").lower()
    is_id_like = (
        profile.column_type_group == "id"
        or name_low.endswith("_id")
        or name_low == "id"
        or "planview" in name_low
    )
    total = max(int(profile.total_rows), 1)
    distinct_ratio = float(profile.distinct_count) / total
    if is_id_like and profile.duplicate_count > 0:
        out.append((
            "Uniqueness",
            f"ID-like column with {profile.duplicate_count} duplicates",
        ))
    if (
        profile.column_type_group in ("string", "categorical")
        and 0 < profile.distinct_count <= 30
    ):
        out.append((
            "Conformity",
            f"low-cardinality string ({profile.distinct_count} distinct) - "
            "consider an allowed-values list",
        ))
    if profile.column_type_group in ("numeric", "integer", "float") and (
        profile.min_value is not None and profile.max_value is not None
    ):
        out.append((
            "Accuracy",
            f"numeric with finite range [{profile.min_value}, {profile.max_value}]",
        ))
    if profile.column_type_group in ("datetime", "date"):
        out.append(("Timeliness", "date/datetime column - set max_lag_days SLA"))
        out.append(("Currency", "date/datetime column - set max_age_days freshness"))
    if profile.column_type_group in ("float", "numeric") and distinct_ratio > 0.5:
        out.append(("Precision", "float with high distinctness - verify expected decimals"))
    return out


def recommend_dqrs_for_cde(
    dp,
    config,
    other_scope: Optional[Dict[str, Any]] = None,
    top_neighbors: int = 3,
) -> pd.DataFrame:
    """For each CDE in ``config.cdes``, recommend DQRs to add.

    Two complementary signals:

    * **Profile-similarity**: cosine on the standardized profile vector.
      Neighbours come from ``other_scope`` (defaults to all other DPs in
      session state, when available) or from the same DP's non-CDE
      columns as a fallback. The DQRs already assigned to similar
      columns become candidate recommendations.
    * **Heuristics**: see :func:`_heuristic_dimensions`. Always emitted,
      independent of neighbors.

    Recommendations already covered by the current config are dropped so
    the table only shows ACTIONABLE additions.
    """
    if not config.cdes:
        return pd.DataFrame()
    existing_dims_by_cde: Dict[str, set] = {}
    for a in config.assignments:
        existing_dims_by_cde.setdefault(a.cde_column, set()).add(a.dimension)

    # Build neighbor pool. ``other_scope`` is expected to look like
    # ``{dp_code: (DataProduct, DataProductConfig)}`` so we can read both
    # profiles + DQR assignments from peer DPs.
    neighbor_vectors: List[Tuple[str, str, np.ndarray, List[str]]] = []
    if other_scope:
        for code, (other_dp, other_cfg) in other_scope.items():
            for col, prof in other_dp.profiles.items():
                if other_dp is dp and col in (config.cdes or []):
                    continue  # don't recommend a CDE to itself
                vec, _ = _profile_feature_vector(prof)
                dims_assigned = sorted({
                    a.dimension for a in other_cfg.assignments
                    if a.cde_column == col
                })
                if dims_assigned:
                    neighbor_vectors.append((code, col, vec, dims_assigned))
    if not neighbor_vectors:
        # Fallback: use the current DP's non-CDE columns as the neighbor pool.
        non_cde_cols = [c for c in dp.profiles.keys() if c not in (config.cdes or [])]
        for col in non_cde_cols:
            vec, _ = _profile_feature_vector(dp.profiles[col])
            # No DQRs are assigned outside of CDEs by construction, so we
            # can't borrow DQRs, but we can still use these as "similar
            # profiles" for context. We'll just skip them in the neighbor
            # loop since they wouldn't contribute recommendations.
            _ = vec
        # If nothing else, heuristics alone will populate the table.

    # Standardise neighbor matrix robustly (so cosine isn't dominated by
    # the large-magnitude null/distinct dimensions).
    if neighbor_vectors:
        M = np.vstack([v for _, _, v, _ in neighbor_vectors])
        med = np.median(M, axis=0)
        mad = np.median(np.abs(M - med), axis=0)
        mad = np.where(mad > 0, mad, 1.0)
    else:
        med = mad = None

    def _standardize(v: np.ndarray) -> np.ndarray:
        if med is None:
            return v
        return (v - med) / (1.4826 * mad)

    rows = []
    for cde in (config.cdes or []):
        profile = dp.profiles.get(cde)
        if profile is None:
            continue
        existing = existing_dims_by_cde.get(cde, set())

        # 1. Heuristic dimensions
        heuristics = [
            (dim, reason)
            for dim, reason in _heuristic_dimensions(profile)
            if dim not in existing
        ]

        # 2. Neighbor recommendations
        neighbor_recs: List[Tuple[str, str, float]] = []  # (dim, neighbor_label, sim)
        if neighbor_vectors:
            v = _standardize(_profile_feature_vector(profile)[0])
            v_norm = np.linalg.norm(v) or 1.0
            similarities: List[Tuple[float, str, str, List[str]]] = []
            for code, col, n_vec, dims in neighbor_vectors:
                nv = _standardize(n_vec)
                nv_norm = np.linalg.norm(nv) or 1.0
                sim = float((v @ nv) / (v_norm * nv_norm))
                similarities.append((sim, code, col, dims))
            similarities.sort(key=lambda t: -t[0])
            top = similarities[: int(top_neighbors)]
            for sim, code, col, dims in top:
                for d in dims:
                    if d not in existing:
                        neighbor_recs.append((d, f"{code}.{col}", sim))

        # De-duplicate neighbor recs: keep best similarity per (dim).
        best_by_dim: Dict[str, Tuple[str, float]] = {}
        for d, lbl, s in neighbor_recs:
            if d not in best_by_dim or s > best_by_dim[d][1]:
                best_by_dim[d] = (lbl, s)

        # Emit rows
        for dim, reason in heuristics:
            rows.append({
                "cde": cde,
                "recommendation": dim,
                "source": "heuristic",
                "reason": reason,
                "similar_to": "",
                "similarity": None,
            })
        for dim, (lbl, sim) in best_by_dim.items():
            rows.append({
                "cde": cde,
                "recommendation": dim,
                "source": "neighbor",
                "reason": f"similar columns assign this DQR ({lbl})",
                "similar_to": lbl,
                "similarity": round(sim, 3),
            })

    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    # Drop duplicates per (cde, recommendation), preferring "neighbor" with
    # higher similarity over "heuristic" so the table doesn't double-list
    # the same dimension for the same CDE.
    df["_rank"] = df["source"].map({"neighbor": 0, "heuristic": 1}).fillna(2)
    df = df.sort_values(
        ["cde", "recommendation", "_rank", "similarity"],
        ascending=[True, True, True, False],
        na_position="last",
    ).drop_duplicates(subset=["cde", "recommendation"], keep="first").drop(columns=["_rank"])
    return df.reset_index(drop=True)


# =============================================================================
# (9) SHAP-like per-row score explainability
# =============================================================================

def explain_row_score(
    dp,
    config,
    result,
    row_index: Any,
    flags: Optional[pd.DataFrame] = None,
    rule_meta: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Decompose ``100 - row_score`` into per-CDE contributions.

    For each rule the row failed, the contribution is
    ``normalized_weight_i * 100`` (within its source). Aggregating those
    contributions by ``cde_column`` (Standard) or by ``required_columns``
    (Custom) gives a deficit per CDE that sums to ``100 - row_score`` for
    a single-source DP, and to the same value scaled by source-weights
    when both Standard and Custom are active.

    Returned dict:

    * ``row_score``, the row's actual score.
    * ``status`` - "GREEN" / "YELLOW" / "RED".
    * ``per_cde`` - DataFrame ``[cde, deficit, share_pct]`` sorted descending.
    * ``per_rule`` - DataFrame ``[rule_id, source, label, weight_pct,
      passed, contribution]`` sorted by contribution.
    * ``waterfall_x`` / ``waterfall_y`` - arrays for a Plotly waterfall
      chart that starts at 100 and ends at the row's score.
    """
    if flags is None or rule_meta is None:
        flags, rule_meta = build_rule_flag_matrix(dp, config)
    if flags.empty or row_index not in flags.index:
        return {
            "row_score": 0.0,
            "status": "RED",
            "per_cde": pd.DataFrame(),
            "per_rule": pd.DataFrame(),
            "waterfall_x": [],
            "waterfall_y": [],
            "waterfall_measure": [],
        }

    row_pass = flags.loc[row_index]
    score = float(result.row_scores.loc[row_index]) if row_index in result.row_scores.index else 0.0
    status = (
        "GREEN" if score >= result.threshold_green
        else "YELLOW" if score >= result.threshold_yellow
        else "RED"
    )

    # ---- Normalized per-rule weights (matches scorecard math) ----
    std_assigns = [a for a in config.assignments if a.rule_id in flags.columns]
    cust_assigns = [a for a in config.custom_assignments if a.rule_id in flags.columns]
    std_w = np.array([a.weight for a in std_assigns], dtype=float)
    cust_w = np.array([a.weight for a in cust_assigns], dtype=float)
    std_norm = (std_w / std_w.sum()) if std_w.sum() > 0 else (
        np.ones(len(std_w)) / max(len(std_w), 1)
    )
    cust_norm = (cust_w / cust_w.sum()) if cust_w.sum() > 0 else (
        np.ones(len(cust_w)) / max(len(cust_w), 1)
    )

    # Source-level weighting (matches compute_scorecard).
    sources = result.source_weights or {"standard": 100.0}
    src_total = sum(sources.values()) or 1.0
    w_std = float(sources.get("standard", 0.0)) / src_total
    w_cust = float(sources.get("custom", 0.0)) / src_total

    # CDE rollup map for Custom rules.
    custom_rule_cdes: Dict[str, List[str]] = {}
    if cust_assigns:
        # Import outside the try so a catalog-load failure can't leave
        # ``effective_required_columns`` unbound when the loop below
        # reaches the rule-found branch.
        from config.custom_dqr_catalog import (
            effective_required_columns,
            get_available_custom_dqr_rules,
        )
        try:
            catalog = {r.id: r for r in get_available_custom_dqr_rules(dp.system_code)}
        except Exception:  # pragma: no cover
            catalog = {}
        for a in cust_assigns:
            rule = catalog.get(a.rule_id)
            if rule is None:
                custom_rule_cdes[a.rule_id] = []
                continue
            req = effective_required_columns(rule, getattr(a, "params", None) or {})
            custom_rule_cdes[a.rule_id] = list(req.values())

    # Per-rule contributions (already accounting for source weights).
    rule_rows: List[Dict[str, Any]] = []
    cde_deficit: Dict[str, float] = {cde: 0.0 for cde in (config.cdes or [])}

    for i, a in enumerate(std_assigns):
        passed = bool(row_pass[a.rule_id])
        contrib = 0.0 if passed else float(std_norm[i] * 100.0 * w_std)
        rule_rows.append({
            "rule_id": a.rule_id,
            "source": "Standard",
            "label": f"{a.cde_column} · {a.dimension}",
            "weight_pct": round(float(a.weight), 2),
            "passed": passed,
            "contribution_to_deficit": round(contrib, 2),
        })
        if not passed:
            cde_deficit[a.cde_column] = cde_deficit.get(a.cde_column, 0.0) + contrib

    for i, a in enumerate(cust_assigns):
        passed = bool(row_pass[a.rule_id])
        contrib = 0.0 if passed else float(cust_norm[i] * 100.0 * w_cust)
        rid = a.rule_id
        label = rule_meta.get(rid, {}).get("label", rid)
        rule_rows.append({
            "rule_id": rid,
            "source": "Custom",
            "label": label,
            "weight_pct": round(float(a.weight), 2),
            "passed": passed,
            "contribution_to_deficit": round(contrib, 2),
        })
        if not passed:
            cdes_for_rule = custom_rule_cdes.get(rid, [])
            if cdes_for_rule:
                share = contrib / len(cdes_for_rule)
                for cde in cdes_for_rule:
                    cde_deficit[cde] = cde_deficit.get(cde, 0.0) + share
            else:
                cde_deficit["(unattributed)"] = (
                    cde_deficit.get("(unattributed)", 0.0) + contrib
                )

    per_rule = pd.DataFrame(rule_rows).sort_values(
        "contribution_to_deficit", ascending=False,
    )
    total_deficit = float(sum(cde_deficit.values())) or 1e-9
    per_cde = pd.DataFrame([
        {
            "cde": cde,
            "deficit": round(d, 2),
            "share_pct": round(d / total_deficit * 100.0, 2),
        }
        for cde, d in sorted(cde_deficit.items(), key=lambda t: -t[1])
        if d > 0  # only show CDEs that actually pulled the score down
    ])

    # ---- Waterfall: 100 → −deficit_cde_1 → ... → row_score ----
    wf_x: List[str] = ["Perfect score"]
    wf_y: List[float] = [100.0]
    wf_measure: List[str] = ["absolute"]
    for _, r in per_cde.iterrows():
        wf_x.append(r["cde"])
        wf_y.append(-float(r["deficit"]))
        wf_measure.append("relative")
    wf_x.append("Row score")
    wf_y.append(float(score))
    wf_measure.append("total")

    return {
        "row_score": float(round(score, 2)),
        "status": status,
        "per_cde": per_cde,
        "per_rule": per_rule,
        "waterfall_x": wf_x,
        "waterfall_y": wf_y,
        "waterfall_measure": wf_measure,
    }
