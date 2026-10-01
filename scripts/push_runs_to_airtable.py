"""Send persisted runs (DQS_RUNS) to the Airtable detailed-results table.

Backfill / repair companion of the "Send to Airtable" button and the
scheduled job, which only push each Data Product's *latest* run::

    python scripts/push_runs_to_airtable.py                 # latest run of every DP
    python scripts/push_runs_to_airtable.py --systems ADR   # latest ADR run
    python scripts/push_runs_to_airtable.py --all           # every persisted run
    python scripts/push_runs_to_airtable.py --dry-run       # check, write nothing

``--dry-run`` reads the base schema (when the token has the
``schema.bases:read`` scope) and the linked tables, then prints which
columns are missing / computed, where each link column points, which link
values would stay blank and a sample of the rows - without writing.

Records are upserted on "Result ID", so re-running is safe. Environment:
the same variables the app uses (``DQS_PERSISTENCE``, ``DATABRICKS_*``,
``AIRTABLE_*``); a ``.env`` at the project root is loaded when present.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Upsert persisted run results into the Airtable "
                    "detailed-results table.")
    parser.add_argument("--systems", default="",
                        help="comma-separated system codes (default: every "
                             "system with a persisted run)")
    parser.add_argument("--all", action="store_true",
                        help="send every persisted run, not just the latest "
                             "per system")
    parser.add_argument("--dry-run", action="store_true",
                        help="check the table schema and the link "
                             "resolution, print the rows, write nothing")
    args = parser.parse_args(argv)

    from src import airtable_results
    from src.airtable_push import AirtablePushError
    from src.persistence import list_runs

    wanted = {s.strip() for s in args.systems.split(",") if s.strip()}
    runs = [r for r in list_runs()
            if (r.get("payload") or {}).get("id")
            and (not wanted or r.get("dp_code") in wanted)]
    if not args.all:
        # list_runs is oldest-first: the last record per DP wins.
        runs = list({r.get("dp_code"): r for r in runs}.values())
    report = {}
    if args.dry_run:
        try:
            report["schema"] = airtable_results.inspect_schema()
        except AirtablePushError as exc:
            report["schema"] = f"not checked: {exc}"
    try:
        summary = airtable_results.push_runs(runs, dry_run=args.dry_run)
    except AirtablePushError as exc:
        if report:
            print(json.dumps(report, indent=2, default=str))
        print(f"Airtable push failed: {exc}", file=sys.stderr)
        return 1
    report.update({"runs": summary.run_ids,
                   "unresolved_links": summary.unresolved})
    if args.dry_run:
        by_type: dict = {}
        for row in summary.rows:
            by_type.setdefault(row.get("Result Type"), row)
        report["rows_to_write"] = len(summary.rows)
        report["sample_rows"] = list(by_type.values())
    else:
        report["records"] = len(summary.record_ids)
    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
