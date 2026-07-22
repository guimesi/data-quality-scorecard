"""Saved projects with an audit changelog (phase 3).

UI-free service between the project UI (mode-selection browser + Step 6
save panel) and :mod:`src.persistence`. A *project* is a named, versioned
capture of the whole scoring configuration - domain, systems, CDEs,
Standard/Custom rule assignments with params, and every weight. Data is
NOT stored: opening a project rebuilds the data products fresh and applies
the saved configuration on top.

Versioning is append-only (each save is a new immutable version row via
``save_project_version``), so the version list *is* the audit changelog:
who saved, when, and a human-readable :func:`change_summary` of what
changed versus the previous version.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from src.models import CustomDQRAssignment, DataProductConfig, DQRAssignment
from src.persistence import (
    list_project_versions,
    log_event,
    save_project_version,
)

# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def serialize_config(cfg: DataProductConfig) -> Dict[str, Any]:
    return {
        "system_code": cfg.system_code,
        "cdes": list(cfg.cdes),
        "assignments": [
            {
                "cde_column": a.cde_column,
                "dimension": a.dimension,
                "weight": float(a.weight),
                "params": dict(a.params or {}),
            }
            for a in cfg.assignments
        ],
        "dqr_sources": list(cfg.dqr_sources),
        "source_weights": {k: float(v) for k, v in cfg.source_weights.items()},
        "custom_assignments": [
            {
                "rule_id": a.rule_id,
                "weight": float(a.weight),
                "params": dict(a.params or {}),
            }
            for a in cfg.custom_assignments
        ],
    }


def deserialize_config(data: Dict[str, Any]) -> DataProductConfig:
    return DataProductConfig(
        system_code=str(data.get("system_code", "")),
        cdes=list(data.get("cdes", [])),
        assignments=[
            DQRAssignment(
                cde_column=a["cde_column"],
                dimension=a["dimension"],
                weight=float(a.get("weight", 0.0)),
                params=dict(a.get("params") or {}),
            )
            for a in data.get("assignments", [])
        ],
        dqr_sources=list(data.get("dqr_sources", [])),
        source_weights={
            k: float(v) for k, v in (data.get("source_weights") or {}).items()
        },
        custom_assignments=[
            CustomDQRAssignment(
                rule_id=a["rule_id"],
                weight=float(a.get("weight", 0.0)),
                params=dict(a.get("params") or {}),
            )
            for a in data.get("custom_assignments", [])
        ],
    )


def serialize_project(domain_code: str,
                      configs: Dict[str, DataProductConfig]) -> Dict[str, Any]:
    return {
        "domain_code": domain_code,
        "systems": sorted(configs),
        "configs": {code: serialize_config(cfg) for code, cfg in configs.items()},
    }


def deserialize_project(
    payload: Dict[str, Any],
) -> Tuple[str, Dict[str, DataProductConfig]]:
    configs = {
        code: deserialize_config(data)
        for code, data in (payload.get("configs") or {}).items()
    }
    return str(payload.get("domain_code", "")), configs


# ---------------------------------------------------------------------------
# Change summary (the human-readable changelog line)
# ---------------------------------------------------------------------------


def _names(items: List[str], cap: int = 3) -> str:
    if len(items) > cap:
        return f"{len(items)}"
    return ", ".join(items)


def _config_changes(prev: Dict[str, Any], curr: Dict[str, Any]) -> List[str]:
    """Compact list of differences between two serialized configs."""
    parts: List[str] = []

    prev_cdes, curr_cdes = set(prev.get("cdes", [])), set(curr.get("cdes", []))
    if curr_cdes - prev_cdes:
        parts.append(f"+CDE {_names(sorted(curr_cdes - prev_cdes))}")
    if prev_cdes - curr_cdes:
        parts.append(f"-CDE {_names(sorted(prev_cdes - curr_cdes))}")

    def _std_map(cfg: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        return {
            f"{a['cde_column']}::{a['dimension']}": a
            for a in cfg.get("assignments", [])
        }

    def _custom_map(cfg: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        return {a["rule_id"]: a for a in cfg.get("custom_assignments", [])}

    for label, prev_map, curr_map in (
        ("rule", _std_map(prev), _std_map(curr)),
        ("custom rule", _custom_map(prev), _custom_map(curr)),
    ):
        added = sorted(set(curr_map) - set(prev_map))
        removed = sorted(set(prev_map) - set(curr_map))
        if added:
            parts.append(f"+{label} {_names(added)}")
        if removed:
            parts.append(f"-{label} {_names(removed)}")
        common = set(prev_map) & set(curr_map)
        reweighted = [
            k for k in common
            if round(float(prev_map[k].get("weight", 0.0)), 4)
            != round(float(curr_map[k].get("weight", 0.0)), 4)
        ]
        retuned = [
            k for k in common
            if (prev_map[k].get("params") or {}) != (curr_map[k].get("params") or {})
        ]
        if reweighted:
            parts.append(f"{len(reweighted)} {label} weight(s) changed")
        if retuned:
            parts.append(f"{len(retuned)} {label} param(s) changed")

    if (prev.get("source_weights") or {}) != (curr.get("source_weights") or {}) \
            or (prev.get("dqr_sources") or []) != (curr.get("dqr_sources") or []):
        parts.append("sources/source weights changed")
    return parts


def change_summary(prev_payload: Dict[str, Any],
                   curr_payload: Dict[str, Any]) -> str:
    """One human-readable line describing ``curr`` versus ``prev``."""
    parts: List[str] = []
    if prev_payload.get("domain_code") != curr_payload.get("domain_code"):
        parts.append(
            f"domain {prev_payload.get('domain_code')} → "
            f"{curr_payload.get('domain_code')}"
        )
    prev_cfgs = prev_payload.get("configs") or {}
    curr_cfgs = curr_payload.get("configs") or {}
    added = sorted(set(curr_cfgs) - set(prev_cfgs))
    removed = sorted(set(prev_cfgs) - set(curr_cfgs))
    if added:
        parts.append(f"+system {_names(added)}")
    if removed:
        parts.append(f"-system {_names(removed)}")
    for code in sorted(set(prev_cfgs) & set(curr_cfgs)):
        changes = _config_changes(prev_cfgs[code], curr_cfgs[code])
        if changes:
            parts.append(f"{code}: " + ", ".join(changes))
    return "; ".join(parts) if parts else "No configuration changes."


# ---------------------------------------------------------------------------
# Save / browse
# ---------------------------------------------------------------------------


def save_project(name: str, domain_code: str,
                 configs: Dict[str, DataProductConfig]) -> Optional[Dict[str, Any]]:
    """Persist a new version of project ``name`` and return the saved record
    (with its ``version`` and ``change_summary``), or ``None`` when the name
    is blank / there is nothing to save / persistence is down."""
    name = (name or "").strip()
    if not name or not configs:
        return None
    payload = serialize_project(domain_code, configs)
    previous = list_project_versions(name)
    summary = (
        change_summary(previous[-1].get("payload") or {}, payload)
        if previous else "Project created."
    )
    if not save_project_version(name, payload, summary):
        return None
    log_event("project_saved", {"project": name}, domain_code)
    versions = list_project_versions(name)
    return versions[-1] if versions else None


def list_projects() -> List[Dict[str, Any]]:
    """One row per project, newest-updated first: name, domain, version
    count, and who/when last saved it."""
    grouped: Dict[str, Dict[str, Any]] = {}
    for record in list_project_versions():
        name = str(record.get("project_name", ""))
        info = grouped.setdefault(name, {"name": name, "versions": 0})
        info["versions"] = max(info["versions"], int(record.get("version", 0)))
        info["updated_ts"] = record.get("ts", "")
        info["updated_by"] = record.get("username", "")
        info["domain_code"] = (record.get("payload") or {}).get("domain_code", "")
    return sorted(grouped.values(),
                  key=lambda i: str(i.get("updated_ts", "")), reverse=True)


def get_project(name: str,
                version: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """A specific version's record of project ``name`` (default: latest)."""
    versions = list_project_versions(name)
    if not versions:
        return None
    if version is None:
        return versions[-1]
    for record in versions:
        if int(record.get("version", 0)) == int(version):
            return record
    return None
