# SiS Migration & Remediation Changes — `data-quality-scorecard`

**Context:** Production target is **Streamlit in Snowflake (SiS), deployed from this GitHub
repo** (app object under *Projects → Streamlit*; code pulled via a Snowflake Git
integration). This document lists the changes to make the project consistent with the SiS
production runtime and to pass Erebor / SAST / JFrog / pipeline checks.

> **Status (as of the reconciliation):** the **P0 code/config work has landed on the `dev`
> branch** — the data layer auto-selects the Snowpark session (connector kept as the local
> fallback), `environment.yml` declares the production deps, dotenv is optional, deps were
> refreshed, and report-only OSS SAST/SCA/secret scanning runs in CI. **What remains** is
> running the `deploy/` SQL in Snowflake, GitHub branch protection, enterprise scanning
> onboarding (Erebor/JFrog/Nexus/Heimdall), data classification, and account-specific
> verification. See the **Quick checklist** at the end for per-item status. The original
> sections below describe each change in full.

Priority legend: **P0** = blocks the app from working / deploying in SiS, or is a security
must-fix. **P1** = required for compliance/consistency before production sign-off. **P2** =
recommended hardening / hygiene.

> Note: items marked *(verify against current Snowflake docs)* depend on SiS feature
> details that should be confirmed against the live Snowflake documentation for the target
> account, since SiS capabilities evolve.

---

## 1. Snowflake connectivity — replace the local connector with the in-platform session

**P0 — the app cannot connect to Snowflake once deployed to SiS as written.**

- **`src/snowflake_client.py`** — Replace `snowflake.connector.connect(...)` +
  `externalbrowser` (`connect()`, lines ~72-92) with the SiS pattern using
  **`snowflake.snowpark.context.get_active_session()`**. The app already has an
  authenticated, warehouse-backed session inside SiS — there is no account/user/
  authenticator/browser step.
  - Rework `fetch_table()` / `fetch_query()` to run through the Snowpark session
    (e.g. `session.sql(query).to_pandas()`), preserving the existing **parameterized**
    `WHERE ... IN (%s, ...)` behaviour so the project-filter stays injection-safe
    *(verify Snowpark `session.sql` parameter-binding syntax)*.
  - `get_shared_client()` / `close_shared_client()` (lines ~188-221): in SiS the session
    is platform-managed and long-lived; the "single auth round-trip" rationale no longer
    applies. Decide whether to keep a thin shim returning the active session or remove the
    shared-client lifecycle entirely. Make sure
    `_clear_workflow_state_for_domain_switch` no longer closes a session it doesn't own.
  - `_resolve_location()` (lines ~36-63): confirm the active session's current
    database/schema, or the domain's pinned `snowflake_database`/`snowflake_schema`, still
    resolve correctly without `SETTINGS.sf_database/schema` from `.env`.
- **Keep the local path optional (recommended):** make the data layer select between
  Snowpark (SiS) and the legacy connector (local dev) so local development still works.
  Without this, local `DATA_SOURCE=snowflake` dev stops functioning.

## 2. Dependencies — declare SiS deps via `environment.yml` (Anaconda channel)

**P0 for the build to be correct; P1 for JFrog/SCA consistency.**

- **Add `environment.yml`** at repo root declaring the packages SiS must load from the
  **Snowflake Anaconda channel** (the production dependency source). Pin the **Python
  version** SiS will run *(verify supported versions for the target account)*.
  - Likely needed: `pandas`, `numpy`, `plotly`, `scikit-learn`, `snowflake-snowpark-python`.
  - `streamlit` itself is provided/managed by SiS — confirm whether it should be listed
    *(verify against current Snowflake docs)*.
- **Drop production reliance on PyPI-only packages:** `snowflake-connector-python` and
  `python-dotenv` are **local-only** and should not be production deps. They may remain in
  `requirements.txt`/`requirements.lock` for **local dev/CI only**, but that must be
  clearly labeled so JFrog/SCA does not treat them as the production set.
- **Document the split explicitly** (e.g. a header comment in `requirements.txt` and a
  README note): `requirements*.txt` = local dev/CI; `environment.yml` = SiS production.
  This is the key fix for "JFrog/SCA scanning the wrong dependency set".
- **Review pinned versions for advisories** regardless of channel. ✅ DONE: deps were
  refreshed (e.g. `urllib3` 1.26→2.x, streamlit→≥1.54, pyarrow/requests/pyjwt/tornado/pillow);
  `pip-audit` now reports no known vulnerabilities on `requirements.lock`.

## 3. Configuration & secrets — remove `.env`/dotenv from the runtime path

**P0 for correctness; P1 for secret hygiene.**

- **`config/settings.py`** — `load_dotenv(...)` + `os.getenv("SNOWFLAKE_*")` will not work
  in SiS (no `.env`, no dotenv). Remove the SF connection settings from the runtime config
  for the SiS path. Non-connection settings still needed (`THRESHOLD_GREEN`,
  `THRESHOLD_YELLOW`, `MAX_ROWS_PER_TABLE`, `DATA_SOURCE`) need a SiS-compatible source —
  hardcoded defaults, a config table, or Streamlit-provided config *(verify SiS config
  options)*.
- **`.env` hygiene (P0 security):** the local `.env` holds a **real corporate Snowflake
  account identifier and corporate email** (values intentionally not reproduced here). It is
  gitignored and untracked today — keep it that way. Because the GitHub repo is now the
  deployment source, **a committed secret ships
  to production**. Confirm `.env` is never staged; consider `git secrets`/pre-commit guard.
- **Account/warehouse/role are set at app creation in SiS**, not in code — remove the
  expectation that they come from env.

## 4. Access control — dedicated least-privilege role + grant model

**P0 security.**

- **Create a dedicated, least-privilege, READ-ONLY Snowflake role** for the SiS app,
  scoped to exactly the required schemas (`UC_GP_CSC` for Cost Estimate, the Quality
  schema). Do **not** run the app under a broad personal/admin role. The app only issues
  `SELECT` (no writes/DDL), so the role should grant only `USAGE` + `SELECT` on the needed
  objects and `USAGE` on the warehouse.
- **Decide the app's rights model** (owner's-rights vs caller's-rights) and document it.
  Under owner's-rights, every viewer sees data through that single role.
- **Define who is granted `USAGE` on the Streamlit object** (the audience). If different
  viewers must see different data, owner's-rights cannot express that — evaluate
  caller's-rights, separate app instances, or **row-access policies** on the source tables.
- **Choose/assign the warehouse** the SiS app runs on (currently `.env` names
  `TRUSTED_WH`); set it at app creation, sized for the workload.

## 5. Deployment artifacts & process — Git → Snowflake

**P0 to deploy; P1 to secure the path.**

- **Add the SiS deployment definition** (the Streamlit object DDL / `CREATE STREAMLIT`
  pointing at the Git repository stage, the API/Git integration, and the `main_file`
  entry = `app.py`) *(verify exact objects required for the target account)*. None exist
  in the repo today.
- **Secure the Git integration:** the GitHub PAT / secret used by Snowflake's Git
  integration lives in **Snowflake** (a SECRET object), not in the repo. Confirm storage
  and least-privilege on it.
- **Branch protection on the deploy branch (P0 security):** because an unreviewed commit
  flows straight to production, enforce **mandatory PR review, status checks, and restricted
  push** on whatever branch SiS deploys from; require ticket references for traceability.

## 6. Documentation — align with the SiS reality

**P1 (consistency; Erebor compares docs vs runtime).**

- **`ARCHITECTURE.md`** ✅ DONE: previously said *"runs on the user's machine / No deploy
  step"*; now describes the SiS runtime, sandboxed compute, `get_active_session()` data
  access, `environment.yml` deps, the Git→Snowflake deploy step, and the role/grant model.
  (Data classification statement still TODO.)
- **`README.md`** — update the run/deploy instructions to cover SiS deployment, and label
  the local `streamlit run` flow as **development-only**.
- **Add a data-classification statement** (what data the app reads in production, its
  sensitivity tier) — referenced by multiple Odin items and currently absent.

## 7. CI/CD & scanning — add the missing security stages

**P1 (Erebor/SAST/JFrog).**

- Add **SCA/dependency-vulnerability scanning** (e.g. JFrog Xray) pointed at the **correct
  production dependency set** (`environment.yml`), not just `requirements.lock`.
- Add **secret scanning** (detect-secrets / gitleaks) to **pre-commit and CI** — especially
  important now that the repo is the deployment source.
- Add **SAST** to the pipeline.
- Add a **deploy-verification step** for the Git→Snowflake integration; update the CI note
  that claims there is no deploy step.
- **`environment.yml` validation** in CI (lint/parse) so a broken deploy manifest is caught
  before it reaches Snowflake.

## 8. Logging & monitoring — use platform facilities

**P1/P2.**

- Enable **Snowflake event-table logging/telemetry** for the SiS app for centralized
  analysis/alerting *(verify setup for the target account)*.
- Rely on Snowflake **Access History / Query History** for auditing what the app's role
  queried (centralized auditing that local execution lacked).
- Keep app log level at WARNING+ and confirm `exc_info` traces never surface bound filter
  values / schema details.

## 9. Output / export behavior in SiS

**P2 (verify).**

- The CSV/JSON **download** flow (`ui/step_06/_export.py`, Streamlit `download_button`)
  should still work in SiS, delivering files to the viewer's browser — **verify behavior**
  in the SiS sandbox. The existing **CSV-injection sanitization** (`_sanitize_csv_cell`)
  and **`html.escape` on rendered values** remain valid and should be kept.
- Re-confirm the **excessive-data-exposure** point: the CSV still exports *all* data-product
  columns; consider limiting to CDEs + score columns before production.

## 10. Tooling config alignment

**P2.**

- **`pyproject.toml` / ruff `target-version = "py39"`** and **CI `python-version: 3.11`**
  should be reconciled with the **Python version SiS actually runs** (set in
  `environment.yml`) so lint/test match production.

---

## Quick checklist

Status legend: `[x]` done · `[~]` partial · `[ ]` not started. Reflects the **`dev`** branch as of
the reconciliation. (`[x]` = code/config landed on `dev`; running the deploy in Snowflake and the
GitHub/enterprise items remain.)

- [x] P0 Replace connector/externalbrowser with `get_active_session()` (`src/snowflake_client.py`) — dual backend; connector kept as local fallback
- [x] P0 Add `environment.yml` (Anaconda deps + Python version)
- [x] P0 Remove dotenv/SF env from runtime (`config/settings.py`); SiS-compatible config — dotenv optional; thresholds/limits use built-in defaults
- [~] P0 Dedicated least-privilege read-only role; grants/audience; warehouse — **reference SQL written** (`deploy/01_least_privilege_role.sql`); **not yet run**; audience/warehouse to finalize
- [~] P0 SiS deployment definition (CREATE STREAMLIT + Git integration) — **reference SQL written** (`deploy/02_sis_deploy.sql`); **not yet executed**
- [ ] P0 Branch protection + mandatory PR review on the deploy branch — **GitHub setting, not applied**
- [x] P0 Confirm `.env` never committed; secret-scan guard — `.env` untracked; gitleaks in CI (report-only)
- [~] P1 Label PyPI deps dev/CI-only; point JFrog/SCA at `environment.yml` — labelled done; pip-audit on lock in CI; **JFrog Xray on `environment.yml` not wired**
- [~] P1 Update ARCHITECTURE/README; add data classification — **docs updated**; **data classification still undeclared**
- [~] P1 Add SCA + secret scanning + SAST + deploy verification to CI — **report-only OSS SAST/SCA/secret added** (`security.yml`); **enterprise Erebor/JFrog/Nexus + deploy verification + DAST/Heimdall pending**
- [x] P1 Review pinned deps for advisories — refreshed (streamlit, urllib3→2.x, etc.); pip-audit clean
- [ ] P2 Enable event-table logging; rely on Access/Query History — **not configured**
- [ ] P2 Verify export/download behavior in SiS; consider column minimization on CSV — **pending post-deploy smoke test**
- [x] P2 Reconcile Python version across `environment.yml` / ruff / CI — all on 3.11 (ruff `py311`, CI 3.11, `environment.yml` `python=3.11`)

### Still-open follow-ups (carry into `odin.md`)
- Run the `deploy/` SQL in Snowflake (create role + app objects); finalize audience/warehouse.
- Apply **branch protection** on the deploy branch.
- Onboard to **enterprise scanning**: Erebor (SAST), JFrog Xray / Nexus (SCA on `environment.yml`), Heimdall (DAST against the deployed endpoint) + verify HTTP security headers there.
- Declare **data classification** for the schemas the app reads.
- Confirm **plotly/scikit-learn versions** in the Snowflake Anaconda channel; post-deploy **smoke test** of the Snowpark data path.
- Replace raw-exception UI messages (`st.error(f"...{e}")`) with generic text (warehouse runtime can't disable `showErrorDetails`).
- Enable Snowflake **event-table logging**; confirm session/idle-timeout policy.
