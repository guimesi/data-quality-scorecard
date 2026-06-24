## Validate HTTP Request Header Requirements

**Accept only necessary HTTP methods; handle pre-flight OPTIONS appropriately.**
Status: Applicable
Comment: Platform-delegated — the app exposes no custom HTTP endpoints and cannot configure method handling. Follow-up: verify at the deployed endpoint that only necessary methods are accepted and OPTIONS is handled.

**Strict whitelist for Access-Control-Allow-Origin (CORS); no "null" origins.**
Status: Applicable
Comment: Platform-delegated — the app sets no CORS headers; Streamlit's defaults are on and CORS is Snowflake-managed. Follow-up: verify the endpoint enforces a strict ACAO with no "null" origins.

**Authenticate HTTP headers added by trusted proxies/SSO (e.g. bearer tokens).**
Status: Applicable
Comment: Platform-delegated — the app performs no header-based auth and never trusts inbound headers for identity (auth is the Snowflake session). Follow-up: verify the endpoint does not trust unauthenticated inbound identity headers.

## Build requirements

**App, config, and dependencies redeployable via automated scripts / documented runbook, or restorable from backups.**
Status: Applicable
Comment: Source is in Git and the SiS deploy is documented in `deploy/` (Git-integration + role + CREATE STREAMLIT SQL). Gap: the SQL is a template not yet run/tested end-to-end. Follow-up: run and validate the deploy.

**Secure, repeatable build/deploy via CI/CD, automated config management, deploy scripts.**
Status: Applicable
Comment: CI runs build/test plus report-only scanning, and `environment.yml` makes the SiS build reproducible. Gap: deployment is reference SQL, not yet automated/executed. Follow-up: automate and verify the Git→Snowflake deployment.

**Admins can verify integrity of security-relevant configurations (tamper detection).**
Status: Applicable
Comment: Security-relevant config is env-driven locally and Snowflake-set under SiS, with no integrity/tamper-detection mechanism today. Follow-up: treat SiS deployment config as version-controlled, verify via `SHOW`/`GET_DDL`, and rely on Git history plus branch protection.

**Harden server configurations per app-server/framework recommendations.**
Status: Applicable
Comment: No explicit Streamlit hardening config exists (defaults in effect); server hardening is Snowflake's responsibility. Follow-up: confirm SiS serving is hardened; keep XSRF/CORS on and telemetry off if a local config is added.

**Configure compiler flags for buffer-overflow protections, stack randomization, DEP; break build on unsafe pointers/format strings.**
Status: Not Applicable
Comment: The app is pure Python with no compilation/native build step, so there are no compiler flags to set (C-extension deps are prebuilt wheels/conda packages).

## Unintended Security Disclosure Requirements

**Configure error messages to be user-actionable/customized and prevent unintended disclosure.**
Status: Applicable
Comment: Mostly generic messages, but `ui/step_02_data_product_review.py` interpolates the raw exception and Streamlit shows tracebacks by default. Follow-up: use generic messages plus server-side logging and disable error-detail display in SiS.

**HTTP headers/responses do not expose detailed version information.**
Status: Applicable
Comment: The app sets no version headers, but the serving layer controls response headers and the app cannot remediate header-level version leakage. Follow-up: verify the deployed SiS endpoint does not leak component versions.

**Disable debug modes in production.**
Status: Applicable
Comment: No production hardening config is present; Streamlit dev features are at defaults. Follow-up: ensure no debug/dev flags are enabled and `client.showErrorDetails` is off in production.

## Dependency requirements

**Sandbox/encapsulate third-party libraries, exposing only necessary functionality.**
Status: Applicable
Comment: Python does not sandbox imports and the app imports pandas/numpy/plotly/streamlit/snowflake directly; true isolation comes from the SiS sandbox. No app-level library sandboxing is feasible; low priority.

**Remove unnecessary features, documentation, sample applications, and default configurations.**
Status: Applicable
Comment: The Git-deployed source includes runtime-unnecessary artifacts (dev notebook, `documents/`, `tests/`, `deploy/`); `deploy/README.md` documents the runtime-vs-dev-only split and confirms no runtime code imports dev-only paths. Follow-up: keep the notebook free of real account values and optionally trim dev artifacts.

**Implement Subresource Integrity (SRI) for externally hosted (CDN) assets.**
Status: Not Applicable
Comment: The app includes no externally hosted JS/CSS — Streamlit serves bundled assets and `unsafe_allow_html` is inline static CSS. Follow-up: keep this invariant by not introducing external `<script src>` includes.

**Maintain a comprehensive inventory catalog of all third-party libraries.**
Status: Applicable
Comment: Inventory exists for both runtimes: `requirements.txt`/`requirements.lock` (local/CI) and `environment.yml` (SiS). Gap: SBOM tooling (JFrog Xray) must point at `environment.yml`. Follow-up: onboard `environment.yml` to org SCA/SBOM tooling.

**Verify components are up to date, ideally with a dependency checker in the build.**
Status: Applicable
Comment: Substantially addressed: CI runs pip-audit report-only and deps were refreshed to clear advisories (point-in-time; JFrog Xray on the PR is authoritative). Gap: authoritative production scan must run via Xray against `environment.yml`, plus update alerting.

**Source all third-party components from predefined, trusted, maintained repositories.**
Status: Applicable
Comment: Satisfied — locally from default PyPI (no custom index) and under SiS from Snowflake's curated Anaconda channel, pinned in `environment.yml`. Follow-up: ensure no untrusted package index is ever introduced.

## HTTP Security Headers Requirements

**Implement secure headers (Cache-Control, CSP, HSTS, X-Content-Type-Options, X-Frame-Options, X-XSS-Protection).**
Status: Applicable
Comment: The app cannot set HTTP response headers — they are platform-controlled — so this is platform-delegated. Follow-up: verify the deployed endpoint's headers against SSG/Heimdall. (XSS is additionally mitigated in-app via `html.escape`.)

**Remove headers: Expect-CT, Feature-Policy, Pragma, Public-Key-Pins.**
Status: Applicable
Comment: The app emits none of these; their presence is determined by the serving layer. Platform-delegated. Follow-up: confirm at the deployed endpoint via SSG/Heimdall.

**Comply with SSG HTTP header checks (Heimdall).**
Status: Applicable
Comment: Compliance must be assessed against the deployed endpoint since the app cannot set headers. Follow-up: run Heimdall/SSG checks against the SiS URL and route failures to Snowflake platform owners.

**Restrict unsafe headers on directive (Access-Control-Allow-Origin, Content-Security-Policy).**
Status: Applicable
Comment: The app emits no ACAO or CSP; these are platform-controlled under SiS. Platform-delegated; verify the serving layer does not set an overly permissive ACAO/CSP.

**Ensure OWASP "headers to remove" are not returned by the server.**
Status: Applicable
Comment: The app returns no custom/technical-disclosure headers; what the server returns is Snowflake-controlled. Follow-up: verify at the deployed endpoint that no information-disclosing headers are returned.

**Optional secure headers if used (Clear-Site-Data, COEP, COOP, CORP, Referrer-Policy, X-Permitted-Cross-Domain-Policies).**
Status: Not Applicable
Comment: The app sets none of these optional headers and cannot set headers, so the "if used" condition does not apply; any such headers would be set by the Snowflake serving layer.
