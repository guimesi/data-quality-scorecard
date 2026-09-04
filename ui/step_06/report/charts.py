"""Inline-SVG charts for the Data Quality Report.

No Plotly, no external assets: the gauge, the score trend and the
threshold distribution are plain SVG / CSS, matching the handoff's
reference markup pixel-for-pixel (same viewBoxes, radii and classes).
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

from ui.step_06.report.html import esc
from utils.helpers import score_bucket

# Gauge geometry (viewBox 0 0 140 84): half-circle centred at (70, 70),
# band radius 54, stroke 12; threshold ticks cross the band (r 44 -> 64).
_G_CX, _G_CY, _G_R = 70.0, 70.0, 54.0
_TICK_R1, _TICK_R2 = 44.0, 64.0

# Trend geometry (viewBox 0 0 560 150): plot x 36..548, y(100)=12,
# y(0)=122 (1.1 px per score point); date axis at y=142.
_T_X0, _T_X1 = 36.0, 548.0
_T_YTOP, _T_SCALE = 12.0, 1.1

# At most this many runs get a value + date label on the trend (always
# including the first and last): with dozens of persisted runs the labels
# would otherwise overlap into an unreadable smear.
_TREND_MAX_LABELS = 8


def _arc_point(fraction: float, radius: float) -> Tuple[float, float]:
    """Point on the gauge arc at ``fraction`` (0 = left end, 1 = right)."""
    angle = fraction * math.pi
    return (_G_CX - radius * math.cos(angle), _G_CY - radius * math.sin(angle))


def gauge_svg(score: float, green: float, yellow: float) -> str:
    """The overall-score half-circle gauge with threshold ticks."""
    frac = max(0.0, min(100.0, float(score))) / 100.0
    x0, y0 = _arc_point(0.0, _G_R)
    x1, y1 = _arc_point(1.0, _G_R)
    bucket = score_bucket(score, green, yellow)

    fill = ""
    if frac > 0:
        fx, fy = _arc_point(frac, _G_R)
        fill = (
            f'<g class="g-{bucket}"><path class="fill" '
            f'd="M{x0:.1f} {y0:.1f} A{_G_R:.0f} {_G_R:.0f} 0 0 1 '
            f'{fx:.1f} {fy:.1f}" fill="none" stroke-width="12" '
            'stroke-linecap="butt"/></g>'
        )
    ticks = []
    for threshold in (yellow, green):
        tf = max(0.0, min(100.0, float(threshold))) / 100.0
        ax, ay = _arc_point(tf, _TICK_R1)
        bx, by = _arc_point(tf, _TICK_R2)
        ticks.append(
            f'<line x1="{ax:.1f}" y1="{ay:.1f}" x2="{bx:.1f}" y2="{by:.1f}" '
            'stroke="#94a3b8" stroke-width="1.5"/>'
        )
    return (
        f'<svg class="gauge" viewBox="0 0 140 84" role="img" '
        f'aria-label="Overall score {score:.1f} of 100">'
        f'<g stroke="#e5e7eb"><path class="track" '
        f'd="M{x0:.1f} {y0:.1f} A{_G_R:.0f} {_G_R:.0f} 0 0 1 '
        f'{x1:.1f} {y1:.1f}" fill="none" stroke-width="12" '
        'stroke-linecap="butt"/></g>'
        + fill + "".join(ticks)
        + f'<text x="70" y="66" text-anchor="middle" class="g-num">{score:.1f}</text>'
        '<text x="70" y="80" text-anchor="middle" class="g-sub">/ 100</text>'
        '<text x="10" y="82" class="g-sub">0</text>'
        '<text x="130" y="82" text-anchor="end" class="g-sub">100</text></svg>'
    )


def _ty(value: float) -> float:
    """Trend y coordinate for a 0-100 score value."""
    return _T_YTOP + (100.0 - max(0.0, min(100.0, value))) * _T_SCALE


def _label_indices(n: int) -> List[int]:
    if n <= _TREND_MAX_LABELS:
        return list(range(n))
    step = (n - 1) / (_TREND_MAX_LABELS - 1)
    return sorted({round(i * step) for i in range(_TREND_MAX_LABELS)})


def trend_svg(runs: Sequence[Dict], green: float, yellow: float) -> str:
    """Score trend across persisted runs with threshold bands.

    ``runs`` is oldest-first; each item needs ``score`` (float), ``date``
    (label for the x axis) and ``changed`` (config changed vs previous -
    drawn as the ◆ marker).
    """
    n = len(runs)
    y100, yg, yy, y0 = _ty(100), _ty(green), _ty(yellow), _ty(0)
    width = _T_X1 - _T_X0
    if n == 1:
        xs = [(_T_X0 + _T_X1) / 2.0]
    else:
        xs = [_T_X0 + i * width / (n - 1) for i in range(n)]
    points = " ".join(
        f"{x:.1f},{_ty(float(r['score'])):.1f}" for x, r in zip(xs, runs)
    )
    labelled = set(_label_indices(n))
    marks: List[str] = []
    for i, (x, r) in enumerate(zip(xs, runs)):
        y = _ty(float(r["score"]))
        if r.get("changed"):
            marks.append(
                f'<rect x="{x - 6:.1f}" y="{y - 6:.1f}" width="12" height="12" '
                f'transform="rotate(45 {x:.1f} {y:.1f})" fill="#fff" '
                'stroke="#3b4d8f" stroke-width="2"/>'
            )
        else:
            marks.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="#fff" '
                'stroke="#3b4d8f" stroke-width="2"/>'
            )
        if i in labelled:
            # Clamp the labels inside the viewBox: a 100-score value label
            # would otherwise be clipped at the top, and the last run's
            # centred date label at the right edge.
            vy = max(y - 11.0, 10.0)
            vx = min(max(x, 50.0), 532.0)
            marks.append(
                f'<text x="{vx:.1f}" y="{vy:.1f}" text-anchor="middle" '
                f'class="t-val">{float(r["score"]):.1f}</text>'
                f'<text x="{vx:.1f}" y="142" text-anchor="middle" '
                f'class="t-ax">{esc(r["date"])}</text>'
            )
    return (
        f'<svg class="trend" viewBox="0 0 560 150" role="img" '
        f'aria-label="Score trend across {n} runs">'
        f'<rect x="36" y="{yy:.1f}" width="{width:.0f}" height="{y0 - yy:.1f}" '
        'fill="#dc2626" opacity=".08"/>'
        f'<rect x="36" y="{yg:.1f}" width="{width:.0f}" height="{yy - yg:.1f}" '
        'fill="#eab308" opacity=".08"/>'
        f'<rect x="36" y="{y100:.1f}" width="{width:.0f}" height="{yg - y100:.1f}" '
        'fill="#16a34a" opacity=".08"/>'
        f'<line x1="36" y1="{yg:.1f}" x2="548" y2="{yg:.1f}" stroke="#16a34a" '
        'stroke-dasharray="3 3"/>'
        f'<line x1="36" y1="{yy:.1f}" x2="548" y2="{yy:.1f}" stroke="#eab308" '
        'stroke-dasharray="3 3"/>'
        f'<text x="30" y="{yg + 4:.0f}" text-anchor="end" class="t-ax">{green:.0f}</text>'
        f'<text x="30" y="{yy + 4:.0f}" text-anchor="end" class="t-ax">{yellow:.0f}</text>'
        '<text x="30" y="16" text-anchor="end" class="t-ax">100</text>'
        '<text x="30" y="126" text-anchor="end" class="t-ax">0</text>'
        f'<polyline points="{points}" fill="none" stroke="#3b4d8f" stroke-width="2"/>'
        + "".join(marks) + "</svg>"
    )


def stacked_bar(green_pct: float, yellow_pct: float, red_pct: float,
                aria_label: Optional[str] = None) -> str:
    """The Green/Yellow/Red threshold-distribution stacked bar."""
    label = aria_label or (
        f"Threshold distribution: Green {green_pct:.1f}%, "
        f"Yellow {yellow_pct:.1f}%, Red {red_pct:.1f}%"
    )
    return (
        f'<div class="stack" role="img" aria-label="{esc(label)}">'
        f'<span class="seg f-green" style="width:{green_pct:.2f}%"></span>'
        f'<span class="seg f-yellow" style="width:{yellow_pct:.2f}%"></span>'
        f'<span class="seg f-red" style="width:{red_pct:.2f}%"></span></div>'
    )


def score_bar(score: float, green: float, yellow: float) -> str:
    """A small horizontal score bar coloured by threshold bucket."""
    bucket = score_bucket(score, green, yellow)
    width = max(0.0, min(100.0, float(score)))
    return (
        '<span class="bar" aria-hidden="true">'
        f'<span class="bar-fill f-{bucket}" style="width:{width:.1f}%"></span>'
        "</span>"
    )
