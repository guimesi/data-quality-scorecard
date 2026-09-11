"""Generate both Data Quality Report editions from mock data.

Runs the One-click pipeline for a domain in ``DATA_SOURCE=mock`` mode,
records a couple of runs in a throw-away persistence store (so the
History / drift sections have content), then writes:

- ``<out>/dq_scorecard_report.html``   interactive edition
- ``<out>/dq_scorecard_pdf.html``      print-ready PDF edition (HTML)
- ``<out>/dq_scorecard_report.pdf``    PDF (when a headless Chromium is
                                       available - see report/convert.py)
- ``<out>/metadata.json``

Usage::

    python scripts/build_sample_report.py [--domain cost_estimate]
        [--systems ACCE,ADR] [--out /tmp/dq_report] [--no-pdf]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("DATA_SOURCE", "mock")
os.environ.setdefault("DQS_PERSISTENCE", "local")
os.environ.setdefault("DQS_STORE_DIR", tempfile.mkdtemp(prefix="dq_sample_store_"))
os.environ.setdefault("DQS_REPORT_STORE", "off")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain", default="cost_estimate")
    parser.add_argument("--systems", default="ACCE,ADR")
    parser.add_argument("--out", default=str(ROOT / "output" / "dq_report"))
    parser.add_argument("--no-pdf", action="store_true")
    parser.add_argument("--project-filter", default="PV-10422,PV-10587")
    args = parser.parse_args()

    from config.domains import get_domain
    from src.ml_lab import snapshot_scorecard
    from src.one_click import run_one_click
    from src.persistence import current_username, save_run
    from src.run_history import record_run_if_new
    from ui.step_06.report import ReportContext, build_report, split_zip

    systems = [s.strip() for s in args.systems.split(",") if s.strip()]
    result = run_one_click(args.domain, systems)
    if result.skipped:
        print("skipped:", result.skipped)

    # Seed history: an older, better run with a different config hash so the
    # drop alert, the trend and the "what changed" drift all render.
    for code, product in result.products.items():
        prev = snapshot_scorecard(code, product.data_product, product.scorecard)
        prev["overall_score"] = min(100.0, float(product.scorecard.overall_score) + 12.0)
        for key in ("rule_pass_rates", "custom_rule_pass_rates"):
            prev[key] = {k: min(100.0, v + 9.0) for k, v in prev[key].items()}
        save_run(code, args.domain, prev, config_hash="previouscfg")
        record_run_if_new(code, product.data_product, product.scorecard,
                          product.config, args.domain)

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    ctx = ReportContext(
        domain_code=args.domain,
        domain_name=get_domain(args.domain).name,
        dp_codes=result.scored_systems,
        generated_at=now.isoformat(timespec="seconds").replace("+00:00", "Z"),
        generated_by=current_username(),
        mode="one_click",
        data_scope="sample",
        sample_rows_cap=50000,
        project_filter=[p for p in args.project_filter.split(",") if p],
        run_id=f"run_{now.strftime('%Y%m%d_%H%M%S')}_demo",
    )
    artifacts = build_report(ctx, result.scorecards, result.data_products,
                             result.configs, want_pdf=not args.no_pdf)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "dq_scorecard_report.html").write_bytes(artifacts.html)
    (out / "dq_scorecard_pdf.html").write_bytes(artifacts.pdf_html)
    if artifacts.pdf:
        (out / "dq_scorecard_report.pdf").write_bytes(artifacts.pdf)
    split_dir = out / "split"
    split_dir.mkdir(exist_ok=True)
    for kind in ("html", "css", "js"):
        (split_dir / artifacts.filenames[f"split_{kind}"]).write_bytes(
            artifacts.split[kind])
    (out / artifacts.filenames["split_zip"]).write_bytes(split_zip(artifacts))
    (out / "metadata.json").write_text(
        json.dumps(artifacts.metadata, indent=2, default=str), encoding="utf-8")
    print(f"interactive: {len(artifacts.html):,} bytes")
    print(f"split:       {', '.join(artifacts.filenames[f'split_{k}'] for k in ('html', 'css', 'js'))} "
          f"-> {split_dir}")
    print(f"pdf html:    {len(artifacts.pdf_html):,} bytes "
          f"({artifacts.metadata['pdf_pages']} pages)")
    print(f"pdf:         {len(artifacts.pdf or b''):,} bytes"
          + (f" - {artifacts.metadata['pdf_error']}" if not artifacts.pdf else ""))
    print(f"written to   {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
