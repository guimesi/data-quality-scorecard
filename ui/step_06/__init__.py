"""Step 6 (Scorecard Dashboard), partitioned by concern.

External callers should keep importing from :mod:`ui.step_06_dashboard`,
which re-exports the helpers below. This package is the internal layout:

- :mod:`ui.step_06._shared`:        CSS, ``_status_class``, system icons / accents.
- :mod:`ui.step_06._export`:        CSV / JSON download builders.
- :mod:`ui.step_06._charts`:        Plotly gauge + threshold-bar.
- :mod:`ui.step_06._breakdown`:     DP-card header, source-breakdown card,
                                    Custom Rules table.
- :mod:`ui.step_06._dp_dashboard`:  Per-DP card (gauge + tab row) and the
                                    cross-DP overview tiles.
"""
