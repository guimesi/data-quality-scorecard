# Error Handling and Logging — Odin Threat Modeling Assessment

**Application:** `data-quality-scorecard`

**Framing context:** The app uses Python's stdlib `logging` (`logging.getLogger(__name__)`
in each module) with the ARCHITECTURE-mandated "no silent except" rule
(`logger.warning(..., exc_info=True)`). It configures **no handlers/formatter/basicConfig**,
so it relies on default logging (stderr, local time) — there is **no app-managed log store**.
It implements **no authentication or access-control decisions of its own** (delegated to
Snowflake SSO + RBAC), so those security events are recorded at the **Snowflake tier**
(Login History / Access History / Query History), not by the app.

Concrete points established in review:
- One user-facing error interpolates the raw exception: `st.error(f"❌ Failed to build data
  products: {e}")` (`ui/step_02_data_product_review.py:184`). Most other `st.error` calls are
  generic navigation guidance.
- **No `.streamlit/config.toml` is tracked**, so Streamlit's default behaviour (rendering
  exception tracebacks in the browser for *uncaught* exceptions) is not disabled.
- No `st.exception` (full-traceback widget) is used.
- Timestamps use local-time `datetime.now()` (e.g. `exported_at`, snapshot ids); **no UTC**.
- Logged values are predominantly catalog-constrained identifiers (system code, rule id),
  not free-text — low log-injection risk.

> **SiS production note:** under Streamlit in Snowflake the platform provides the
> security-relevant logging/monitoring this app lacks locally — **Login History** (auth),
> **Access History / Query History** (data access, RBAC-protected, UTC), and **event tables**
> for app telemetry. Several gaps below become "enable/rely on the platform facility" in
> production rather than app code. Also set Streamlit error-detail display off in the SiS app.

---

## Log Processing Requirements

**Question:** Log all access control decisions, including failed ones, with relevant metadata.
**Status:** Applicable
**Comment:** The app makes **no in-app access-control decisions** (authorization is delegated to Snowflake RBAC), so it logs none. The applicable control is at the Snowflake tier: **Access History / Query History** record what the user's role accessed (including denials), with per-user attribution. Follow-up: ensure Snowflake account-level auditing is enabled for the production app; the app should not (and does not) duplicate or fabricate access logs.

**Question:** Log all authentication decisions without storing sensitive session identifiers or passwords, with relevant metadata.
**Status:** Applicable
**Comment:** Authentication is delegated to Snowflake SSO (`externalbrowser` locally; the Snowflake session under SiS); the app implements no login flow and **stores no session identifiers or passwords** (good). Authentication decisions are recorded in **Snowflake Login History**, not the app. Follow-up: rely on/confirm Snowflake login auditing in production.

---

## Log Content Requirements

**Question:** Log security-relevant events (authentication attempts, access-control failures, deserialization failures, input-validation failures).
**Status:** Applicable
**Comment:** Partial. The app logs **operational/processing failures** via `logger.warning(..., exc_info=True)` — data-product build failures (`src/one_click.py:237`), scorecard computation failures (`ui/step_06_dashboard.py:123`), custom-rule errors → `CustomRuleNotEvaluated` (`src/custom_dqr/_dispatcher.py:66`), reference-load failures (`src/reference_data.py:73`). Auth/access-control events are at the Snowflake tier (above). **Gaps:** input-validation failures (incompatible DQRs) and the former upload/deserialization failures are surfaced to the **user** (`st.warning`/`st.error`) but **not security-logged centrally**. Follow-up: route validation/deserialization failures to the SiS event table.

**Question:** Ensure each log event includes information for detailed timeline investigation.
**Status:** Applicable
**Comment:** Partial. Log events carry the module logger name (`__name__`), level, a message with identifiers (system code, rule id), and an `exc_info` stack trace. **Gaps:** no user/session correlation id, and timestamps are **local time, not UTC** (no formatter configured). Follow-up: under SiS, emit structured events (with timestamp/user) to an event table; standardize on UTC.

**Question:** Do not log credentials/payment/sensitive data; store session tokens hashed; comply with privacy policy.
**Status:** Applicable
**Comment:** The app logs **no credentials** (none are stored — SSO) and handles **no payment data**. Logged values are mostly identifiers and rule ids. Follow-up/uncertainty: (a) the connector exception traces captured via `exc_info` and the `st.error(f"...{e}")` path could surface bound filter values or data fragments — verify and keep log level at WARNING+; (b) confirm no data values are emitted to logs in any verbose path. Relevant to data-classification/privacy review.

---

## Error Handling Requirements

**Question:** Show generic messages for unexpected/security-sensitive errors, with unique IDs for support.
**Status:** Applicable
**Comment:** Partial. Most user-facing messages are generic guidance (e.g. "Go back to step 1"). **Gaps:** `ui/step_02_data_product_review.py:184` interpolates the raw exception (`f"... {e}"`), and there are **no unique error/correlation IDs** for support. Follow-up: replace raw-exception interpolation with a generic message + a logged correlation id.

**Question:** Ensure APIs log each failure/unexpected event and store logs centrally (Datadog/Kibana).
**Status:** Applicable
**Comment:** The app is not an API service, but it does log failures — to the **local console only** (no central aggregation today). **SiS equivalent:** Snowflake **event tables / Query History** provide central storage. Follow-up: enable event-table logging for the SiS app (the central-store gap is closeable on the platform, not via Datadog/Kibana).

**Question:** API error messages disclose minimal information and do not confirm/deny data existence.
**Status:** Applicable
**Comment:** There is no per-record lookup API and no anonymous/enumeration surface (access is single-user/SSO-gated), so the "confirm/deny existence" vector is minimal. The applicable part is **minimal disclosure in user-facing errors** — the `{e}` interpolation (above) is the one place that over-discloses. Follow-up: same fix as the generic-message item.

**Question:** Define secure responses to system failures and avoid security misconfigurations.
**Status:** Applicable
**Comment:** The app degrades gracefully for *expected* failures (failed DP build → error message; failed scorecard → logged and excluded; missing rule dependency → "Not evaluated"). **Gap:** for *uncaught* exceptions, Streamlit's default renders a **traceback in the browser**, and **no `.streamlit/config.toml`** disables it. Follow-up: set `client.showErrorDetails = false` (or equivalent) for the production/SiS deployment.

**Question:** Use exception handling across the codebase; define a "last resort" error handler.
**Status:** Applicable
**Comment:** Broad exception handling is in place and is an explicit project rule ("Silent except is forbidden" — every `except` logs or has a tight reason). `app.py` has a fallback for unknown steps (`st.error("Unknown step: ...")`). **Gap:** there is **no explicit global last-resort handler** — uncaught exceptions fall through to Streamlit (which shows a traceback). Follow-up: add a top-level guard in `app.main()` that renders a generic message + logs detail, complementing the config change above.

**Question:** Prevent exposure of detailed error information to end users.
**Status:** Applicable
**Comment:** **Concrete gap.** Two exposure paths: (1) `st.error(f"... {e}")` shows the exception message; (2) Streamlit's default traceback display for uncaught exceptions (no config.toml disabling it). Mitigation today: most expected errors are caught and shown as generic guidance. Follow-up (production-relevant): disable Streamlit error-detail display in SiS and replace raw-exception interpolation with generic text + server-side logging. Relevant to SAST/compliance review.

---

## Log Protection Requirements

**Question:** Ensure all events are protected from injection when viewed in log-viewing software.
**Status:** Applicable
**Comment:** Low risk: logged values are predominantly catalog-constrained identifiers (system codes, rule ids), not free-text. **Gap:** there is **no explicit encoding/escaping of logged values**, so a value containing newlines/control chars (e.g. inside an exception message) could distort a log viewer. Follow-up: sanitize/encode any free-text before logging if such fields are ever logged.

**Question:** Prevent log injection by encoding user-supplied data.
**Status:** Applicable
**Comment:** User-supplied free-text (project IDs) is generally **not** logged (the app logs system codes/rule ids), and `logging` parameterization (`logger.warning("... %s", value)`) does not evaluate input — so the practical risk is low. There is no explicit log-encoding layer, however. Follow-up: encode/strip control characters from any user-derived value before it is logged.

**Question:** Protect security logs from unauthorized access and modification.
**Status:** Applicable
**Comment:** Locally, logs go to the console with no app-level protection. **SiS equivalent:** Snowflake **event tables / Query History / Login History** are stored in Snowflake and protected by RBAC and are tamper-resistant at the platform level. Follow-up: rely on Snowflake-secured logging in production; restrict who can read those objects.

**Question:** Synchronize time sources to the correct time/time zone, preferably UTC.
**Status:** Applicable
**Comment:** **Gap:** the app uses **local-time** `datetime.now()` for application timestamps (`exported_at`, snapshot ids) and default (local-time) logging timestamps — not UTC. (Note: `src/dqr_engine.py` parses *data* datetimes with `utc=True`, but that is data handling, not logging.) Follow-up: stamp application/log timestamps in **UTC**. Under SiS, the platform logs (Query/Login History) are already UTC; app-generated timestamps should match.

---

## Monitoring Alerts Requirements

**Question:** Ensure any external API service components operate in environments with performance monitoring and alerts.
**Status:** Not Applicable
**Comment:** The app exposes **no external API service component**. Under SiS, performance monitoring of the underlying compute (warehouse usage, query performance/history) is provided by the **Snowflake platform**; there is no app-level external API to monitor. If a service component were ever added, this would become Applicable.
