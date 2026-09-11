"""Embedded JavaScript + JSON-island serialisation for the report.

``safe_json_for_script`` makes the payload safe to inline inside a
``<script type="application/json">`` element: after ``json.dumps`` the
characters that could terminate the script element or open a tag
(``<``, ``>``, ``&``) are replaced with their ``\\uXXXX`` escapes, so a
hostile value like ``"</script><script>alert(1)"`` cannot break out of
the island. U+2028/U+2029 are escaped too (they are line terminators in
JavaScript source). The client reads the island with
``JSON.parse(el.textContent)`` and builds DOM nodes with
``createElement``/``textContent`` only - never ``innerHTML``.
"""
from __future__ import annotations

import json

from ui.step_06.report._js_source import REPORT_JS

__all__ = ["REPORT_JS", "safe_json_for_script", "split_js"]

_SCRIPT_SAFE_REPLACEMENTS = (
    ("&", "\\u0026"),   # first, so it doesn't re-escape the others
    ("<", "\\u003c"),
    (">", "\\u003e"),
    (" ", "\\u2028"),
    (" ", "\\u2029"),
)


def safe_json_for_script(obj: object) -> str:
    """Serialise ``obj`` for embedding inside a ``<script>`` element."""
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"),
                      allow_nan=False)
    for raw, escaped in _SCRIPT_SAFE_REPLACEMENTS:
        text = text.replace(raw, escaped)
    return text


def split_js(data_json: str) -> str:
    """The ``.js`` file of the split edition: the JSON payload plus the
    unchanged runtime.

    The runtime reads its data from the ``#report-data`` island, so the
    file first materialises that island from an embedded object literal
    (``data_json`` is the :func:`safe_json_for_script` output, which is
    also a valid JavaScript expression) and then runs ``REPORT_JS``
    verbatim - one runtime for both editions.
    """
    return (
        "(function(){var s=document.createElement('script');"
        "s.type='application/json';s.id='report-data';"
        f"s.textContent=JSON.stringify({data_json});"
        "document.body.appendChild(s);})();\n"
        + REPORT_JS
    )
