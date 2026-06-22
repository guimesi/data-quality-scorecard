"""Custom DQR catalog, partitioned by system.

External callers should keep importing from :mod:`config.custom_dqr_catalog`,
which re-exports the names below. This package is the internal layout;
the per-system catalogs (``_ept_catalog``, ``_adr_catalog``,
``_acce_catalog``) hold the rule lists for each system, and ``_shared``
carries the dataclasses and option-builder helpers consumed by all of
them.
"""
