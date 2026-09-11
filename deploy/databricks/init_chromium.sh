#!/bin/bash
# Cluster init script: headless Chromium for the PDF edition of the Data
# Quality Report (scheduled Job). Classic job clusters run init scripts
# as root, so the system libraries Chromium needs can be installed too.
#
# Attach it to the job cluster as a workspace-file init script, e.g.
#   /Workspace/Users/<you>/dq-scorecard/deploy/databricks/init_chromium.sh
# (see job_dq_report.json). Without it the job still runs: the report
# store receives the print-ready HTML instead of the PDF.
set -euo pipefail

export PLAYWRIGHT_BROWSERS_PATH=/usr/local/share/ms-playwright
/databricks/python/bin/pip install -q "playwright>=1.45,<2.0"
/databricks/python/bin/python -m playwright install --with-deps chromium
chmod -R a+rX "$PLAYWRIGHT_BROWSERS_PATH"
# Make the location visible to the job's Python (ui/step_06/report/convert.py
# checks the Playwright package first, then this path).
echo "export PLAYWRIGHT_BROWSERS_PATH=$PLAYWRIGHT_BROWSERS_PATH" >> /etc/environment
