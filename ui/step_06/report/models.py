"""Dataclasses shared by the report builder and its Streamlit wrapper.

``ReportContext`` carries every piece of run metadata shown in the
report header - it is built ONLY by the Streamlit wrapper (from
``st.session_state``) or by a caller that already knows the values.
``build_report`` itself never touches Streamlit. ``None`` fields render
as an em dash; the builder never invents values.

``ReportArtifact`` is the publisher-agnostic deliverable contract
(``bytes`` + filename + metadata) consumed today by the download button
and the Airtable push, and by a future ``publish_report()`` (SharePoint
or other) without changes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class ReportCaps:
    """Row caps embedded in (and stated by) the report.

    - ``worst_rows``: rows rendered statically in the Worst rows table.
    - ``drill_rows``: max rows a drill-down table renders client-side.
    - ``row_store``: lowest-scoring rows embedded once per DP in the
      JSON island (must be >= ``worst_rows``).
    """
    worst_rows: int = 50
    drill_rows: int = 200
    row_store: int = 300


@dataclass(frozen=True)
class ReportContext:
    """Run metadata for the report header (see the handoff, section 2)."""
    domain_code: str = ""
    domain_name: str = ""
    dp_codes: List[str] = field(default_factory=list)
    generated_at: str = ""                 # UTC ISO-8601 ("...Z")
    generated_by: str = ""
    mode: Optional[str] = None             # "one_click" | "step_by_step"
    data_scope: Optional[str] = None       # "sample" | "full"
    sample_rows_cap: Optional[int] = None  # max rows per table when sampling
    project_filter: List[str] = field(default_factory=list)
    threshold_green: float = 80.0
    threshold_yellow: float = 60.0
    saved_project: Optional[str] = None
    run_id: Optional[str] = None
    drop_alert_pp: float = 5.0
    caps: ReportCaps = field(default_factory=ReportCaps)


@dataclass(frozen=True)
class ReportArtifact:
    """The finished report: UTF-8 HTML bytes + filename + metadata."""
    html: bytes
    filename: str
    metadata: Dict[str, Any] = field(default_factory=dict)
