## Log Processing Requirements

**Log all access control decisions, including failed ones, with relevant metadata.**
Status: Applicable
Comment: The app makes no in-app access-control decisions (delegated to Snowflake RBAC), so it logs none; rely on Snowflake Access History / Query History. Follow-up: ensure account-level auditing is enabled in production.

**Log all authentication decisions without storing sensitive session identifiers or passwords, with relevant metadata.**
Status: Applicable
Comment: Authentication is delegated to Snowflake SSO; the app implements no login flow and stores no session identifiers or passwords. Auth decisions are recorded in Snowflake Login History. Follow-up: confirm Snowflake login auditing in production.

## Log Content Requirements

**Log security-relevant events (authentication attempts, access-control failures, deserialization failures, input-validation failures).**
Status: Applicable
Comment: Partial. The app logs operational/processing failures via `logger.warning(..., exc_info=True)`. Gap: input-validation and deserialization failures are surfaced to the user but not security-logged centrally. Follow-up: route them to the event table.

**Ensure each log event includes information for detailed timeline investigation.**
Status: Applicable
Comment: Partial. Events carry logger name, level, an identifier-bearing message, and an `exc_info` stack trace. Gaps: no user/session correlation id and timestamps are local time, not UTC. Follow-up: emit structured events with timestamp/user; standardize on UTC.

**Do not log credentials/payment/sensitive data; store session tokens hashed; comply with privacy policy.**
Status: Applicable
Comment: The app logs no credentials (SSO) and no payment data; logged values are mostly identifiers. Uncertainty: `exc_info` traces and the `st.error(f"...{e}")` path could surface bound filter values or data fragments. Follow-up: verify and keep log level at WARNING+.

## Error Handling Requirements

**Show generic messages for unexpected/security-sensitive errors, with unique IDs for support.**
Status: Applicable
Comment: Partial. Most user-facing messages are generic guidance. Gaps: one `st.error` interpolates the raw exception (`f"... {e}"`), and there are no unique error/correlation IDs. Follow-up: replace raw-exception interpolation with a generic message plus a logged correlation id.

**Ensure APIs log each failure/unexpected event and store logs centrally (Datadog/Kibana).**
Status: Applicable
Comment: Not an API service, but it logs failures to the local console only, with no central aggregation. Follow-up: enable Snowflake event-table / Query History logging for the SiS app to close the central-store gap.

**API error messages disclose minimal information and do not confirm/deny data existence.**
Status: Applicable
Comment: No per-record lookup API and no anonymous/enumeration surface (single-user, SSO-gated), so the confirm/deny vector is minimal. The `{e}` interpolation is the one place that over-discloses. Follow-up: same fix as the generic-message item.

**Define secure responses to system failures and avoid security misconfigurations.**
Status: Applicable
Comment: Degrades gracefully for expected failures. Gap: for uncaught exceptions, Streamlit's default renders a traceback in the browser and no `.streamlit/config.toml` disables it. Follow-up: set `client.showErrorDetails = false` for the production/SiS deployment.

**Use exception handling across the codebase; define a "last resort" error handler.**
Status: Applicable
Comment: Broad exception handling is in place as an explicit project rule (no silent except). Gap: no explicit global last-resort handler — uncaught exceptions fall through to Streamlit's traceback. Follow-up: add a top-level guard in `app.main()` that renders a generic message and logs detail.

**Prevent exposure of detailed error information to end users.**
Status: Applicable
Comment: Concrete gap via two paths: `st.error(f"... {e}")` shows the exception message, and Streamlit's default traceback display for uncaught exceptions (no config.toml disabling it). Follow-up: disable Streamlit error-detail display in SiS and replace raw-exception interpolation with generic text plus server-side logging.

## Log Protection Requirements

**Ensure all events are protected from injection when viewed in log-viewing software.**
Status: Applicable
Comment: Low risk: logged values are predominantly catalog-constrained identifiers, not free-text. Gap: no explicit encoding/escaping of logged values, so newlines/control chars in an exception message could distort a viewer. Follow-up: sanitize free-text before logging.

**Prevent log injection by encoding user-supplied data.**
Status: Applicable
Comment: User-supplied free-text is generally not logged and `logging` parameterization does not evaluate input, so practical risk is low. There is no explicit log-encoding layer. Follow-up: encode/strip control characters from any user-derived value before logging.

**Protect security logs from unauthorized access and modification.**
Status: Applicable
Comment: Locally, logs go to the console with no app-level protection. Snowflake event tables / Query History / Login History are RBAC-protected and tamper-resistant at the platform level. Follow-up: rely on Snowflake-secured logging and restrict who can read those objects.

**Synchronize time sources to the correct time/time zone, preferably UTC.**
Status: Applicable
Comment: Gap: the app uses local-time `datetime.now()` for application timestamps and default local-time logging timestamps — not UTC. Follow-up: stamp application/log timestamps in UTC to match the platform logs.

## Monitoring Alerts Requirements

**Ensure any external API service components operate in environments with performance monitoring and alerts.**
Status: Not Applicable
Comment: The app exposes no external API service component; under SiS the Snowflake platform provides compute/query performance monitoring. If a service component were ever added, this would become Applicable.
