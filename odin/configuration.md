# Configuration — Odin Threat Modeling Assessment

**Application:** `data-quality-scorecard`

**Framing context:** The app does **not run a web server it can configure at the HTTP layer**.
Locally, Streamlit's own (Tornado) server serves the app; in production under **Streamlit in
Snowflake (SiS)** the HTTP serving layer — methods, CORS, response headers, TLS — is **entirely
Snowflake/Snowsight-managed and not settable from app code**. There is **no `.streamlit/config.toml`**
tracked, so even Streamlit-level toggles are at defaults. Consequently, the HTTP-header / CORS /
method items below are **platform-delegated** (the application cannot implement or remediate them;
SSG/Heimdall must assess the deployed Snowflake endpoint). The **Build, Unintended-Disclosure, and
Dependency** items are genuinely application-relevant and connect to the CI/dependency gaps already
noted in the Architecture/SiS-migration assessments.

> **SiS production note:** because production is served by Snowflake, header/CORS/TLS posture is a
> Snowflake responsibility; dependency posture shifts from PyPI `requirements.lock` to the Snowflake
> **Anaconda channel via `environment.yml`** (now present in the repo). Both points recur below.

---

## Validate HTTP Request Header Requirements

**Question:** Accept only necessary HTTP methods; handle pre-flight OPTIONS appropriately.
**Status:** Applicable
**Comment:** Platform-delegated. The app exposes no custom HTTP endpoints and cannot configure method handling — it belongs to the serving layer (Streamlit locally, **Snowsight under SiS**). The requirement applies to the deployed system but is not remediable in app code. Follow-up: verify at the deployed endpoint (SSG/Heimdall) that only necessary methods are accepted and pre-flight OPTIONS is handled correctly.

**Question:** Strict whitelist for Access-Control-Allow-Origin (CORS); no "null" origins.
**Status:** Applicable
**Comment:** Platform-delegated. The app sets no CORS headers and cannot configure them — Streamlit ships CORS/XSRF protections on by default (no config.toml weakens them) and under SiS CORS is Snowflake-managed. The requirement applies to the deployed system but is not remediable in app code. Follow-up: verify the deployed endpoint enforces a strict ACAO with no "null" origins; and if a `.streamlit/config.toml` is ever added for local use, do not disable `enableCORS`/`enableXsrfProtection`.

**Question:** Authenticate HTTP headers added by trusted proxies/SSO (e.g. bearer tokens).
**Status:** Applicable
**Comment:** Platform-delegated. The app performs no header-based authentication and never trusts inbound headers for identity — auth is the Snowflake session (SSO locally / active session under SiS). Header-based identity at the edge is owned by the **Snowsight/Snowflake serving layer**, not app code. Follow-up: verify the deployed endpoint does not trust unauthenticated inbound identity headers.

---

## Build requirements

**Question:** App, config, and dependencies redeployable via automated scripts / documented runbook, or restorable from backups.
**Status:** Applicable
**Comment:** The source is in Git, and the SiS deploy mechanism is now documented: **`deploy/`** holds the Git-integration + least-privilege-role + `CREATE STREAMLIT` reference SQL (with a run-order README), and ARCHITECTURE.md/README describe the deployment. **Residual gap:** the deploy SQL is a **template that must be run** in Snowflake (objects not yet created), and the runbook hasn't been executed/tested end-to-end. Source-data backup is Snowflake (Time Travel/Fail-safe). Follow-up: run + validate the deploy, capturing any account-specific syntax differences.

**Question:** Secure, repeatable build/deploy via CI/CD, automated config management, deploy scripts.
**Status:** Applicable
**Comment:** CI runs build/test (`.github/workflows/tests.yml`: ruff + pytest on 3.11) plus report-only security scanning (`security.yml`), and **`environment.yml`** now makes the SiS dependency build reproducible. The `deploy/` SQL provides the deployment steps. **Residual gap:** the deployment is **declarative reference SQL, not yet automated/executed** (no GitHub-Actions-driven deploy), and is not onboarded to the enterprise pipeline. Follow-up: automate + verify the Git→Snowflake deployment in the org pipeline.

**Question:** Admins can verify integrity of security-relevant configurations (tamper detection).
**Status:** Applicable
**Comment:** Security-relevant config is env-driven locally (`.env`, untracked) and Snowflake-set under SiS (the Streamlit object's owner role + USAGE grants + warehouse). There is **no integrity/tamper-detection mechanism** today. Follow-up: treat the SiS deployment config (role/grants/Streamlit DDL) as reviewable, version-controlled config and verify it via Snowflake `SHOW`/`GET_DDL`; rely on Git history + branch protection for the app/config integrity.

**Question:** Harden server configurations per app-server/framework recommendations.
**Status:** Applicable
**Comment:** No explicit Streamlit hardening config exists (no config.toml; defaults in effect). Under SiS, server hardening is Snowflake's responsibility. Follow-up: confirm the SiS serving config is hardened by Snowflake; if any local config.toml is introduced, keep XSRF/CORS protections on and disable usage-stats/telemetry.

**Question:** Configure compiler flags for buffer-overflow protections, stack randomization, DEP; break build on unsafe pointers/format strings.
**Status:** Not Applicable
**Comment:** The application is pure Python with **no compilation/native build step**. There are no compiler flags to set (C-extension dependencies are prebuilt third-party wheels/conda packages). Memory-safety items are covered (and marked N/A) under the Input Validation theme.

---

## Unintended Security Disclosure Requirements

**Question:** Configure error messages to be user-actionable/customized and prevent unintended disclosure.
**Status:** Applicable
**Comment:** Partly in place (most messages are generic guidance), but `ui/step_02_data_product_review.py:184` interpolates the raw exception (`f"... {e}"`), and Streamlit's default shows tracebacks for uncaught exceptions (no config.toml disabling it). Same finding as the Error Handling theme. Follow-up: generic messages + server-side logging; disable Streamlit error-detail display in the SiS deployment.

**Question:** HTTP headers/responses do not expose detailed version information.
**Status:** Applicable
**Comment:** The app sets no version headers, but the serving layer (Streamlit/Tornado locally; Snowflake under SiS) controls response headers (e.g. `Server`). The app cannot remediate header-level version leakage directly. Note: dependency versions are visible in `requirements.lock` (a repo file, not a response header). Follow-up: verify the deployed SiS endpoint via SSG/Heimdall does not leak component versions.

**Question:** Disable debug modes in production.
**Status:** Applicable
**Comment:** No production hardening config is present (no config.toml). Streamlit dev features (`runOnSave`, developer console, error-detail display) are at defaults. Under SiS the deployment is not a dev session, but error-detail display should be explicitly disabled. Follow-up: ensure no debug/dev flags are enabled and `client.showErrorDetails` is off in production.

---

## Dependency requirements

**Question:** Sandbox/encapsulate third-party libraries, exposing only necessary functionality.
**Status:** Applicable
**Comment:** Limited and largely platform-provided: Python does not sandbox imported libraries, and the app imports pandas/numpy/plotly/streamlit/snowflake directly (some access is wrapped, e.g. the thin `snowflake_client`). True isolation comes from the **SiS sandbox** (the whole app runs inside Snowflake's managed compute). No app-level library sandboxing is feasible or implemented; low priority.

**Question:** Remove unnecessary features, documentation, sample applications, and default configurations.
**Status:** Applicable
**Comment:** The repo includes runtime-unnecessary artifacts that are present in the Git-deployed source: `notebooks/data_product_preview.ipynb` (a dev notebook that connects to Snowflake), `documents/`, `tests/`, `deploy/`. The SiS app entry point is `app.py`, and the Git integration stages the whole repo but serves nothing from a web root. **Control added:** `deploy/README.md` now documents the runtime-vs-dev-only file split (C2), confirming no runtime code imports the dev-only paths. Follow-up: keep the Snowflake-connecting notebook free of real account values; optionally trim dev artifacts from the deploy branch.

**Question:** Implement Subresource Integrity (SRI) for externally hosted (CDN) assets.
**Status:** Not Applicable
**Comment:** The app includes **no externally hosted JS/CSS** — Streamlit serves its own bundled assets, and the app's `unsafe_allow_html` usage is inline static CSS (no `<script src>`/CDN links). No external asset requires SRI. Follow-up: keep this invariant (do not introduce external `<script src>` includes via `unsafe_allow_html`).

**Question:** Maintain a comprehensive inventory catalog of all third-party libraries.
**Status:** Applicable
**Comment:** Inventory now exists for both runtimes: `requirements.txt` + pinned `requirements.lock` (local/CI) **and `environment.yml`** (SiS production, Anaconda channel). **Residual gap:** SBOM/inventory tooling (JFrog Xray) must be pointed at `environment.yml` for the production set — the PyPI lockfile alone misrepresents the SiS runtime. Follow-up: onboard `environment.yml` to the org SCA/SBOM tooling.

**Question:** Verify components are up to date, ideally with a dependency checker in the build.
**Status:** Applicable
**Comment:** **Substantially addressed.** CI now runs **SCA (pip-audit)** report-only (`security.yml`), and dependencies were **refreshed to clear known advisories** (incl. the previously-flagged `urllib3` 1.26→2.x); `pip-audit` reported **no known vulnerabilities** on `requirements.lock` as of the refresh (point-in-time; **JFrog Xray on the PR is authoritative**). **Residual gap:** the in-repo SCA scans the PyPI lockfile as a proxy — the **authoritative production scan must run via JFrog Xray against `environment.yml`** (Anaconda), and automated dependency-update alerting is still to add. Follow-up: JFrog Xray on `environment.yml` + update alerting.

**Question:** Source all third-party components from predefined, trusted, maintained repositories.
**Status:** Applicable
**Comment:** Satisfied: locally from default PyPI (no custom/insecure index configured); under SiS from Snowflake's curated **Anaconda channel**, now pinned in `environment.yml` (`channels: [snowflake]`). Follow-up: ensure no untrusted package index is ever introduced.

---

## HTTP Security Headers Requirements

**Question:** Implement secure headers (Cache-Control, CSP, HSTS, X-Content-Type-Options, X-Frame-Options, X-XSS-Protection).
**Status:** Applicable
**Comment:** **The application cannot set HTTP response headers** — they are controlled by Streamlit locally and **Snowflake/Snowsight under SiS**. So this is platform-delegated: the app team cannot implement these directly. Follow-up: verify the deployed SiS endpoint's headers against SSG/Heimdall; any gaps are a Snowflake-serving-layer matter, not an app code change. (XSS is additionally mitigated in-app via `html.escape`; clickjacking/CSP cannot be enforced from app code.)

**Question:** Remove headers: Expect-CT, Feature-Policy, Pragma, Public-Key-Pins.
**Status:** Applicable
**Comment:** The app emits none of these itself; their presence/absence is determined by the serving layer (Snowflake under SiS). Platform-delegated. Follow-up: confirm at the deployed endpoint via SSG/Heimdall.

**Question:** Comply with SSG HTTP header checks (Heimdall).
**Status:** Applicable
**Comment:** Compliance must be assessed against the **deployed (Snowflake-served) endpoint**, since the app cannot set headers. Follow-up: run the Heimdall/SSG header checks against the SiS app URL and route any failures to the Snowflake platform owners; document that header posture is inherited from Snowflake.

**Question:** Restrict unsafe headers on directive (Access-Control-Allow-Origin, Content-Security-Policy).
**Status:** Applicable
**Comment:** The app does not emit `Access-Control-Allow-Origin` or `Content-Security-Policy`; these are platform-controlled under SiS. Platform-delegated; verify the serving layer does not set an overly permissive ACAO/CSP. 

**Question:** Ensure OWASP "headers to remove" are not returned by the server.
**Status:** Applicable
**Comment:** The app returns no custom/technical-disclosure headers of its own; what the server returns is Snowflake-controlled under SiS. Follow-up: verify at the deployed endpoint that no information-disclosing headers are returned.

**Question:** Optional secure headers if used (Clear-Site-Data, COEP, COOP, CORP, Referrer-Policy, X-Permitted-Cross-Domain-Policies).
**Status:** Not Applicable
**Comment:** The application sets none of these optional headers (it cannot set headers), so the "if they are used" condition does not apply. Any such headers would be set by the Snowflake serving layer, not the app.
