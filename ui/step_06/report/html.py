"""HTML primitives for the Data Quality Report.

``esc`` is the single escaping gate every dynamic string goes through -
text nodes AND attribute values (``title``, ``data-*``, ``aria-label``).
``document`` assembles the final self-contained page: inline CSS, body,
the JSON payload island and the inline script - no external references.
``document_split`` is the three-file variant (HTML + ``.css`` + ``.js``
side by side) for hosts that strip inline ``<style>``/``<script>``
from ``.html`` files but serve separate assets untouched (SharePoint).
"""
from __future__ import annotations

import html as _html


def esc(value: object) -> str:
    """HTML-escape ``value`` for use in text nodes and attribute values.

    ``quote=True`` escapes both quote characters so the result is safe
    inside double- and single-quoted attributes alike.
    """
    return _html.escape(str(value), quote=True)


def fmt_int(n: object) -> str:
    """Thousands-separated integer (``12480`` -> ``12,480``)."""
    return f"{int(n):,}"


def fmt_cell_number(v: object) -> str:
    """Render a numeric cell value the way the embedded JS renders the
    same value from the JSON store (``String(v)``), so the static worst
    rows and the lazy drill-down tables read identically: integral floats
    lose the trailing ``.0``, everything else keeps full precision."""
    if isinstance(v, float):
        if v.is_integer():
            return str(int(v))
        return repr(v)
    return str(v)


def document(*, title: str, css: str, body: str, data_json: str,
             js: str) -> str:
    """The complete standalone HTML document.

    ``data_json`` must already be ``</script>``-breakout safe (see
    :func:`ui.step_06.report.interactivity.safe_json_for_script`).
    """
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{esc(title)}</title>\n"
        f"<style>\n{css}</style></head>\n"
        "<body>\n"
        f"{body}\n"
        f'<script type="application/json" id="report-data">{data_json}</script>\n'
        f"<script>\n{js}</script>\n"
        "</body></html>"
    )


def document_split(*, title: str, body: str, css_href: str,
                   js_href: str) -> str:
    """The HTML of the split edition: same body, but the stylesheet and
    the script are referenced by *relative* file name instead of being
    inlined, so the three files only need to sit in the same folder.

    The script tag stays at the end of ``<body>`` (like the inline one)
    so the DOM exists when it runs; the ``.js`` file carries the JSON
    payload itself (see :func:`ui.step_06.report.interactivity.split_js`).
    """
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{esc(title)}</title>\n"
        f'<link rel="stylesheet" href="{esc(css_href)}"></head>\n'
        "<body>\n"
        f"{body}\n"
        f'<script src="{esc(js_href)}"></script>\n'
        "</body></html>"
    )
