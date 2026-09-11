"""HTML -> PDF conversion for the PDF edition (headless Chromium).

The paginated HTML declares ``@page{size:A4}`` plus a named
``@page land{size:A4 landscape}`` for the Lowest-scoring rows sheets, so
one conversion yields a mixed-orientation document. Two interchangeable
converters, tried in this order:

1. **Playwright** (``pip install playwright && playwright install
   chromium``): ``page.pdf(print_background=True, prefer_css_page_size=True)``.
2. **A Chromium binary** (``SETTINGS.chromium_path`` /
   ``DQS_CHROMIUM_PATH``, or a well-known install path): ``--headless
   --print-to-pdf`` - Chrome for Testing, Chrome, Edge and the Playwright
   headless shell all work.

When neither is available :func:`html_to_pdf` raises
:class:`PdfConversionUnavailable`; the builder then ships ``pdf=None``
and the print-ready HTML (which prints to the same PDF with Ctrl+P from
any Chromium-based browser). Nothing here imports Streamlit.
"""
from __future__ import annotations

import glob
import logging
import os
import shutil
import subprocess  # nosec B404 - fixed argv, no shell
import tempfile
from pathlib import Path
from typing import Callable, List, Optional

from config.settings import SETTINGS

logger = logging.getLogger(__name__)

# Chromium binaries looked up when no explicit path is configured, in
# order. Globs are expanded (newest version last, so the last match wins).
_KNOWN_CHROMIUM_PATHS = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/usr/bin/microsoft-edge",
    "~/.cache/ms-playwright/chromium_headless_shell-*/chrome-linux/"
    "chrome-headless-shell",
    "~/.cache/ms-playwright/chromium-*/chrome-linux/chrome",
    "~/Library/Caches/ms-playwright/chromium_headless_shell-*/"
    "chrome-headless-shell-mac*/chrome-headless-shell",
    "~/Library/Caches/ms-playwright/chromium-*/chrome-mac*/Chromium.app/"
    "Contents/MacOS/Chromium",
)

_TIMEOUT_SECONDS = 120


class PdfConversionUnavailable(RuntimeError):
    """No headless Chromium converter could be used."""


def find_chromium() -> Optional[str]:
    """Path of a usable Chromium binary, or ``None``.

    ``SETTINGS.chromium_path`` wins; otherwise the well-known locations
    above are probed (``PATH`` lookups included).
    """
    explicit = (SETTINGS.chromium_path or "").strip()
    if explicit:
        return explicit if os.path.isfile(explicit) else None
    for candidate in _KNOWN_CHROMIUM_PATHS:
        expanded = os.path.expanduser(candidate)
        matches = sorted(glob.glob(expanded)) if "*" in expanded else (
            [expanded] if os.path.isfile(expanded) else [])
        if matches:
            return matches[-1]
    for name in ("google-chrome", "chromium", "chromium-browser",
                 "chrome-headless-shell", "microsoft-edge"):
        found = shutil.which(name)
        if found:
            return found
    return None


def _playwright_available() -> bool:
    try:
        import playwright.sync_api  # noqa: F401
    except ImportError:
        return False
    return True


def available_converters() -> List[str]:
    """Names of the converters that can run right now (``[]`` = none)."""
    out: List[str] = []
    if _playwright_available():
        out.append("playwright")
    if find_chromium():
        out.append("chromium")
    return out


def _convert_with_playwright(html: str) -> bytes:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                page = browser.new_page()
                page.set_content(html, wait_until="load")
                return page.pdf(print_background=True, prefer_css_page_size=True)
            finally:
                browser.close()
    except PlaywrightError as exc:  # browser not installed, launch failed
        raise PdfConversionUnavailable(f"Playwright: {exc}") from exc


def _convert_with_chromium(html: str, binary: str) -> bytes:
    with tempfile.TemporaryDirectory(prefix="dq_report_pdf_") as tmp:
        src = Path(tmp) / "report.html"
        out = Path(tmp) / "report.pdf"
        src.write_text(html, encoding="utf-8")
        argv = [
            binary, "--headless", "--disable-gpu", "--no-sandbox",
            "--no-pdf-header-footer", "--run-all-compositor-stages-before-draw",
            "--virtual-time-budget=5000",
            f"--print-to-pdf={out}", src.as_uri(),
        ]
        try:
            proc = subprocess.run(  # nosec B603 - fixed argv, no shell
                argv, capture_output=True, timeout=_TIMEOUT_SECONDS,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise PdfConversionUnavailable(f"Chromium: {exc}") from exc
        if proc.returncode != 0 or not out.exists():
            tail = proc.stderr.decode("utf-8", "replace")[-400:]
            raise PdfConversionUnavailable(
                f"Chromium exited with {proc.returncode}: {tail}")
        return out.read_bytes()


def html_to_pdf(html: str,
                converter: Optional[Callable[[str], bytes]] = None) -> bytes:
    """Render ``html`` (the PDF edition) to PDF bytes.

    ``converter`` overrides the detection (tests, custom deployments).
    Raises :class:`PdfConversionUnavailable` when nothing can convert.
    """
    if converter is not None:
        return converter(html)
    if _playwright_available():
        try:
            return _convert_with_playwright(html)
        except PdfConversionUnavailable as exc:
            logger.info("Playwright conversion unavailable (%s); trying a "
                        "Chromium binary", exc)
    binary = find_chromium()
    if binary:
        return _convert_with_chromium(html, binary)
    raise PdfConversionUnavailable(
        "No headless Chromium available: install Playwright "
        "(pip install playwright && playwright install chromium) or set "
        "DQS_CHROMIUM_PATH to a Chrome / Edge / Chromium binary."
    )
