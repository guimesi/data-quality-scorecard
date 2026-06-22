"""Custom DQR engine, partitioned by rule family.

External callers should keep importing from :mod:`src.custom_dqr_engine`,
which re-exports the names below. This package is the internal layout;
the per-family modules (``_ept_rules``, ``_adr_rules``, ``_acce_rules``)
hold the rule implementations and constants for each system, ``_shared``
holds primitives consumed by all of them, ``_validators`` exposes the
reusable completeness / referential-integrity validators, and
``_dispatcher`` wraps the catalog-driven evaluation loop.
"""
