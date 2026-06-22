"""Session state, partitioned by concern.

External callers should keep importing from :mod:`utils.session_state`,
which re-exports the names below. This package is the internal layout:

- :mod:`utils.session.state`: workflow state (STEPS, init, domain set/get).
- :mod:`utils.session.navigation`: step navigation (next / prev / restart,
  visibility predicates, scroll-to-top).
- :mod:`utils.session.sidebar`: sidebar rendering (CSS, brand, progress
  stepper, sample-mode toggle, project filter, footer).
"""
