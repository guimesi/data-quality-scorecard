"""Dataclasses shared by the report builder and its Streamlit wrapper.

``ReportContext`` carries every piece of run metadata the report shows
(header, About block, cover page) - it is built ONLY by the Streamlit
wrapper (from ``st.session_state``) or by a caller that already knows
the values. ``build_report`` itself never touches Streamlit. ``None``
fields render as an em dash; the builder never invents values.

``ReportModel`` is the ONE view model both editions render from: the
context plus one collected view per Data Product (see
:func:`ui.step_06.report.collect.build_model`).

``ReportArtifacts`` is the publisher-agnostic deliverable contract
(interactive HTML bytes + optional PDF bytes + print-ready HTML +
metadata + filenames) consumed today by the download buttons, the
report store (``/reports/<run_id>``) and the Airtable push, and by a
future ``publish_sharepoint()`` without changes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class ReportCaps:
    """Row caps embedded in (and stated by) both report editions.

    Interactive HTML:

    - ``worst_rows``: rows rendered statically in the Lowest-scoring rows
      table.
    - ``drill_rows``: max rows a drill-down table renders client-side.
    - ``row_store``: lowest-scoring rows embedded once per DP in the
      JSON island (must be >= ``worst_rows``).

    PDF edition (all drawn from the same store):

    - ``pdf_rows``: rows on each Lowest-scoring rows sheet.
    - ``pdf_sample_rows``: sample failing rows per DQR detail card.
    - ``pdf_run_log``: runs listed in the run log.
    - ``pdf_sheet_columns``: data columns per landscape values sheet
      (wider Data Products get several sheets).
    """
    worst_rows: int = 50
    drill_rows: int = 200
    row_store: int = 300
    pdf_rows: int = 25
    pdf_sample_rows: int = 5
    pdf_run_log: int = 6
    pdf_sheet_columns: int = 22


@dataclass(frozen=True)
class ReportContext:
    """Run metadata for the report (see the handoff, section 2)."""
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
class ReportModel:
    """The single view model both editions render from.

    ``dps`` holds one collected view per Data Product (plain dicts, see
    :func:`ui.step_06.report.collect.build_dp_view`), in the order the
    scorecards were given. ``data`` is the ``#report-data`` JSON island
    payload of the interactive edition (thresholds, caps, per-DP row
    stores) - the PDF edition reads its sample rows from the same
    stores, so both artefacts always describe the same records.
    """
    ctx: ReportContext
    dps: List[Dict[str, Any]]
    data: Dict[str, Any]

    @property
    def codes(self) -> List[str]:
        return [v["code"] for v in self.dps]


@dataclass(frozen=True)
class ReportArtifacts:
    """The finished deliverables of one run.

    - ``html``: the interactive edition (self-contained UTF-8 HTML).
    - ``pdf``: the complete PDF edition, or ``None`` when no headless
      Chromium converter was available (``metadata["pdf_error"]`` says
      why); ``pdf_html`` is always present and prints to the same PDF
      from any Chromium-based browser (Ctrl+P).
    - ``metadata``: everything a publisher needs to fill library
      columns (domain, DP codes, scores, statuses, project filter,
      config hashes, caps, page count).
    - ``filenames``: ``{"interactive": ..., "pdf": ..., "pdf_html": ...}``.
    """
    run_id: str
    domain_code: str
    generated_at: str
    html: bytes
    pdf: Optional[bytes]
    pdf_html: bytes
    metadata: Dict[str, Any] = field(default_factory=dict)
    filenames: Dict[str, str] = field(default_factory=dict)

    # -- compatibility with the previous single-artefact contract --------
    @property
    def filename(self) -> str:
        """The interactive edition's file name (previous contract)."""
        return self.filenames.get("interactive", "")

    @property
    def interactive_html(self) -> bytes:
        """Alias of ``html`` (name used in the publishing handoff)."""
        return self.html


# The previous name of the deliverable; kept so existing imports work.
ReportArtifact = ReportArtifacts
