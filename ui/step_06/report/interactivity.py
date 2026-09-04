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

__all__ = ["REPORT_JS", "safe_json_for_script"]

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
