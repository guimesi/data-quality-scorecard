"""Send persisted runs (DQS_RUNS) to the Airtable detailed-results table.

Backfill / repair companion of the "Send to Airtable" button and the
scheduled job, which only push each Data Product's *latest* run.

**Nothing is written unless ``--send`` is given**::

    python scripts/push_runs_to_airtable.py                        # check only
    python scripts/push_runs_to_airtable.py --send                 # latest run of every DP
    python scripts/push_runs_to_airtable.py --send --systems ADR   # latest ADR run
    python scripts/push_runs_to_airtable.py --send --all           # every persisted run

Without ``--send`` the script reads the linked tables (and the base schema,
when the token has the ``schema.bases:read`` scope) and prints a short
summary: how many rows would be written, how many got each link, which
link values stay blank and which columns are missing / computed.
``--verbose`` adds the full schema report and one sample row per type.

Records are upserted on "Result ID", so re-sending is safe. Environment:
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
    parser.add_argument("--send", action="store_true",
                        help="actually write to Airtable (default: check "
                             "the table schema and the link resolution, "
                             "print the rows, write nothing)")
    parser.add_argument("--dry-run", action="store_true",
                        help="the default; kept so older commands still work")
    parser.add_argument("--verbose", action="store_true",
                        help="also print the schema report and sample rows")
    args = parser.parse_args(argv)
    dry_run = args.dry_run or not args.send

    # Same as app.py: behind a TLS-inspecting corporate proxy the certifi CAs
    # reject api.airtable.com; truststore validates against the OS store.
    try:
        import truststore
        truststore.inject_into_ssl()
    except ImportError:  # pragma: no cover - truststore not installed
        pass

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
    report = {"mode": "DRY RUN - nothing written" if dry_run else "SEND"}
    schema = None
    if dry_run:
        try:
            schema = airtable_results.inspect_schema()
            report["columns_missing"] = schema["missing"]
            report["columns_computed"] = schema["computed"]
        except AirtablePushError as exc:
            report["schema"] = f"not checked: {str(exc)[:120]}"
    try:
        summary = airtable_results.push_runs(runs, dry_run=dry_run)
    except AirtablePushError as exc:
        if dry_run:
            print(json.dumps(report, indent=2, default=str))
        print(f"Airtable push failed: {exc}", file=sys.stderr)
        return 1
    report.update({
        "runs": summary.run_ids,
        "rows": len(summary.rows),
        "links_filled": {
            column: sum(1 for row in summary.rows if column in row)
            for column in ("Data Product", "DQR", "CDE")
        },
        "links_blank": summary.unresolved,
    })
    if not dry_run:
        report["records_written"] = len(summary.record_ids)
    if args.verbose:
        by_type: dict = {}
        for row in summary.rows:
            by_type.setdefault(row.get("Result Type"), row)
        report["sample_rows"] = list(by_type.values())
        if schema is not None:
            report["schema"] = schema
    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
