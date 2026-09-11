"""Run the scorecard + Data Quality Report headlessly (no Streamlit).

The command-line face of :mod:`src.scheduled_report` - what a Databricks
Job runs on a schedule (through ``deploy/databricks/scheduled_report_job.py``)
and what you can run locally against mock data::

    DATA_SOURCE=mock python scripts/run_scheduled_report.py --domain cost_estimate
    python scripts/run_scheduled_report.py --domain cost_estimate --systems ACCE,ADR \\
        --project-filter PV-10422 --no-pdf --no-airtable

Prints a JSON summary (run id, scores, where the report was stored, the
hosted paths, Airtable record ids) and exits 0 when the run is usable
(at least one system scored and the report stored - or storage off),
1 otherwise, so the Job shows as failed when something needs a look.

Environment: the same variables the app uses (``DATA_SOURCE``,
``DATABRICKS_*``, ``DQS_PERSISTENCE``, ``DQS_REPORT_STORE`` /
``DQS_REPORT_WORKSPACE_DIR``, ``AIRTABLE_*``); a ``.env`` at the project
root is loaded when present.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _split(value: Optional[str]) -> Optional[List[str]]:
    if value is None or not value.strip():
        return None
    return [v.strip() for v in value.split(",") if v.strip()]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Score a domain and publish its Data Quality Report "
                    "without the Streamlit UI.")
    parser.add_argument("--domain", required=True,
                        help="domain code, e.g. cost_estimate")
    parser.add_argument("--systems", default="",
                        help="comma-separated system codes (default: every "
                             "system of the domain)")
    parser.add_argument("--project-filter", default="",
                        help="comma-separated PLANVIEW ids to filter on")
    parser.add_argument("--no-pdf", action="store_true",
                        help="skip the Chromium PDF conversion")
    airtable = parser.add_mutually_exclusive_group()
    airtable.add_argument("--airtable", dest="airtable", action="store_true",
                          default=None, help="push scores to Airtable")
    airtable.add_argument("--no-airtable", dest="airtable", action="store_false",
                          help="never push to Airtable")
    parser.add_argument("--no-history", action="store_true",
                        help="do not record the run in the run history")
    parser.add_argument("--generated-by", default=None,
                        help="identity written on the report (default: the "
                             "Databricks user / OS login)")
    parser.add_argument("--quiet", action="store_true",
                        help="only print the JSON summary")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        from dotenv import load_dotenv  # type: ignore

        load_dotenv(ROOT / ".env")
    except Exception:  # nosec B110 - optional convenience
        pass

    from src.scheduled_report import run_scheduled_report

    outcome = run_scheduled_report(
        args.domain,
        _split(args.systems),
        planview_filter=_split(args.project_filter),
        want_pdf=not args.no_pdf,
        push_airtable=args.airtable,
        generated_by=args.generated_by,
        record_history=not args.no_history,
    )
    print(outcome.to_json())
    return 0 if outcome.ok else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
