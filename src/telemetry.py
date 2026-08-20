"""Adoption & audit metrics (phase 2).

UI-free aggregations over the persistence layer for the 📊 Adoption admin
page: who uses the app, how often scorecards are generated, what is
exported, and a unified audit trail. Everything is computed from the
records the app already persists (events, run snapshots, project
versions) - nothing here writes.

Authorization is intentionally NOT handled in-app: who may open the app
at all is governed by Databricks Apps permissions (see deploy/). This module
only measures and audits what authorized users did.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List

import pandas as pd

from src.persistence import list_events, list_project_versions, list_runs


def adoption_overview() -> Dict[str, Any]:
    """Headline counters for the metric tiles."""
    events = list_events()
    runs = list_runs(None)
    projects = list_project_versions()

    def _count(event_type: str) -> int:
        return sum(1 for e in events if e.get("event_type") == event_type)

    everything = events + runs + projects
    users = {r.get("username") for r in everything if r.get("username")}
    stamps = sorted(str(r.get("ts", "")) for r in everything if r.get("ts"))
    return {
        "unique_users": len(users),
        "app_opens": _count("app_open"),
        "scorecard_runs": len(runs),
        "exports": _count("export"),
        "projects_saved": _count("project_saved"),
        "projects_loaded": _count("project_loaded"),
        "last_activity": stamps[-1] if stamps else "",
    }


def runs_per_week() -> pd.DataFrame:
    """Scorecard runs per ISO week - the adoption trend chart."""
    runs = list_runs(None)
    if not runs:
        return pd.DataFrame(columns=["week", "runs"])
    ts = pd.to_datetime(
        [r.get("ts") for r in runs], utc=True, errors="coerce", format="ISO8601",
    )
    df = pd.DataFrame({"ts": ts}).dropna()
    if df.empty:
        return pd.DataFrame(columns=["week", "runs"])
    df["week"] = df["ts"].dt.strftime("%G-W%V")
    return df.groupby("week").size().reset_index(name="runs").sort_values("week")


def runs_by_system() -> pd.DataFrame:
    """Adoption per domain / Data Product: run counts + last run."""
    runs = list_runs(None)
    if not runs:
        return pd.DataFrame(columns=["domain", "system", "runs", "last_run"])
    df = pd.DataFrame([
        {
            "domain": r.get("domain_code", ""),
            "system": r.get("dp_code", ""),
            "ts": str(r.get("ts", "")),
        }
        for r in runs
    ])
    out = (
        df.groupby(["domain", "system"])
        .agg(runs=("ts", "size"), last_run=("ts", "max"))
        .reset_index()
        .sort_values("runs", ascending=False)
    )
    return out


def user_activity() -> pd.DataFrame:
    """Per-user rollup: events, runs, project saves, last seen."""
    rows: List[Dict[str, Any]] = []
    for kind, records in (
        ("events", list_events()),
        ("runs", list_runs(None)),
        ("project_saves", list_project_versions()),
    ):
        for r in records:
            rows.append({
                "user": r.get("username", "") or "unknown",
                "kind": kind,
                "ts": str(r.get("ts", "")),
            })
    if not rows:
        return pd.DataFrame(
            columns=["user", "events", "runs", "project_saves", "last_seen"]
        )
    df = pd.DataFrame(rows)
    pivot = (
        df.pivot_table(index="user", columns="kind", values="ts",
                       aggfunc="size", fill_value=0)
        .reindex(columns=["events", "runs", "project_saves"], fill_value=0)
        .astype(int)
    )
    pivot["last_seen"] = df.groupby("user")["ts"].max()
    return pivot.reset_index().sort_values("last_seen", ascending=False)


def _event_detail(event: Dict[str, Any]) -> str:
    payload = event.get("payload") or {}
    if not payload:
        return ""
    return json.dumps(payload, default=str, sort_keys=True)


def recent_activity(limit: int = 100) -> pd.DataFrame:
    """Unified audit trail (newest first): telemetry events, scorecard
    runs and project versions in one table."""
    rows: List[Dict[str, Any]] = []
    for e in list_events():
        rows.append({
            "ts": str(e.get("ts", "")),
            "user": e.get("username", ""),
            "action": e.get("event_type", ""),
            "domain": e.get("domain_code", ""),
            "detail": _event_detail(e),
        })
    for r in list_runs(None):
        payload = r.get("payload") or {}
        rows.append({
            "ts": str(r.get("ts", "")),
            "user": r.get("username", ""),
            "action": "scorecard_run",
            "domain": r.get("domain_code", ""),
            "detail": (
                f"{r.get('dp_code', '?')} "
                f"score={float(payload.get('overall_score', 0.0)):.1f}"
            ),
        })
    for v in list_project_versions():
        rows.append({
            "ts": str(v.get("ts", "")),
            "user": v.get("username", ""),
            "action": "project_version",
            "domain": (v.get("payload") or {}).get("domain_code", ""),
            "detail": (
                f"{v.get('project_name', '?')} v{v.get('version', '?')} - "
                f"{v.get('change_summary', '')}"
            ),
        })
    if not rows:
        return pd.DataFrame(columns=["ts", "user", "action", "domain", "detail"])
    df = pd.DataFrame(rows).sort_values("ts", ascending=False)
    return df.head(limit).reset_index(drop=True)
