## General Data Protection Security Requirements

**Section directive — "Mark all Applicable/Not Applicable"**
Status: Applicable
Comment: Section directive; each item below is individually assessed.

**Follow company-defined data retention periods and set up a backup plan on high-value data.**
Status: Applicable
Comment: The app stores no data; retention/backup of Snowflake source data is inherited from the platform and corporate policy. In-scope CSV/JSON exports leave as user-managed files; document this inheritance.

**Sensitive data should only be collected/retained with a justified business reason, and avoid exposing all object properties (excessive data exposure).**
Status: Applicable
Comment: The CSV export copies the full data product (every column plus scores), so column minimization is not enforced — a genuine excessive-data-exposure gap. Follow-up: limit exports to CDEs plus score columns.

## General Server-Side Data Protection requirements

**Section directive.**
Status: Applicable
Comment: Directive; items assessed individually. The app is a locally hosted Streamlit app, not a hosted multi-user webservice, which shapes the answers below.

**Design the webservice to access the minimum number of systems (per MPI guidelines).**
Status: Applicable
Comment: Mock mode reaches zero external systems; snowflake mode reaches exactly one (Snowflake), reading only configured tables. No other outbound integrations exist — positive evidence for minimal-access review.

**Avoid caching sensitive data in caches/RAM, or protect it; encrypt RESTRICTED data at-rest, in-transit, and in-memory.**
Status: Applicable
Comment: In-transit uses TLS, but exports and in-memory pandas DataFrames are plaintext/unencrypted locally — a gap if data is RESTRICTED. Under SiS the platform encrypts at rest, in transit, and in memory; follow-up: confirm classification and prefer the SiS path.

**Binding client-provided data to models without filtering (Mass Assignment).**
Status: Not Applicable
Comment: No auto-binding of request payloads. Domain models and config JSON are built field-by-field from constrained Streamlit widgets, with no ORM/auto-mapper, so the mass-assignment vector does not apply.

## General Data Protection requirements

**Section directive.**
Status: Applicable
Comment: Directive; items assessed individually.

**Ensure all cached/temporary copies of sensitive data are protected or purged after use.**
Status: Applicable
Comment: Data products, scorecards, and reference datasets are cached in session_state; purge controls clear state and close the shared client on restart and domain/mode switch. Gap: cached data persists unencrypted in RAM until restart.

**Prevent sensitive data from being cached in local storage, memory, or server components.**
Status: Applicable
Comment: In-memory caching is unavoidable and unencrypted to compute scores, but the app writes nothing to disk and mock mode involves no sensitive data. No local-storage persistence by the app.

**Securely store backups; test regular backups of important data.**
Status: Not Applicable
Comment: The app creates and stores no backups and has no persistence layer. Backup of underlying data is a Snowflake responsibility, covered in production by Time Travel / Fail-safe.

**Minimize request parameters; sensitive data must not be in headers or query params.**
Status: Not Applicable
Comment: The app exposes no custom HTTP API; Streamlit uses its own WebSocket transport. Sensitive filter values reach Snowflake as parameterized bind values, never in URLs or headers, so this vector does not apply.

**If WAF/DDoS not used, detect and alert on abnormal request patterns.**
Status: Not Applicable
Comment: Locally the app is not internet-facing. Under SiS, edge protection (WAF/DDoS/anomaly detection) is provided by the Snowflake platform. Either way this is delegated to platform/host, not an app control.

## Client-side Data Protection requirements

**Section directive.**
Status: Applicable
Comment: Directive; the "client" here is the browser tab rendering the Streamlit UI.

**Set anti-caching headers to prevent sensitive data being cached in browsers.**
Status: Applicable
Comment: Warehouse data is rendered into the browser DOM and the app cannot set custom anti-cache headers, relying on framework defaults. Under SiS, cache-control is a Snowsight/Snowflake responsibility; mitigated by authenticated, platform-served access.

**Clear authenticated data from client storage after session termination.**
Status: Not Applicable
Comment: The app stores no auth material in the browser. Snowflake auth is delegated to externalbrowser SSO, and session_state lives server-side in the Python process, so there is no app-managed authenticated client storage to clear.

**Ensure client-side storage does not contain sensitive data or PII.**
Status: Applicable
Comment: The app does not write to browser localStorage, but rendered data and typed inputs exist transiently in the DOM during a session. No PII is intentionally collected. Follow-up: verify no component persists rendered data beyond the session.

## Data Storage and Privacy Requirements

**Section directive.**
Status: Applicable
Comment: Directive; several items below are mobile-app-oriented and assessed accordingly for this desktop/browser app.

**Use system credential storage for sensitive data; do not expose it via the UI.**
Status: Applicable
Comment: No secret is stored; externalbrowser SSO delegates credentials to the IdP, and the gitignored, untracked .env holds only non-secret identifiers. The UI never displays credentials. Gap: keep .env out of commits since the repo is the SiS deploy source; secret scanning now runs in CI.

**Encrypt locally stored sensitive data using hardware-backed keys.**
Status: Not Applicable
Comment: The app persists no sensitive data locally and has no keystore (a mobile concept). The only local artifacts are user-initiated CSV/JSON downloads, which are plaintext and become the user's responsibility once saved.

**Clear sensitive data from views when app is backgrounded; wipe local storage after failed auth attempts.**
Status: Not Applicable
Comment: Mobile lifecycle concepts that do not map to a desktop browser Streamlit app: there is no app-background event and no app-level login/lockout flow, since authentication is delegated to Snowflake SSO.

**Educate users about PII processing and enforce device security policies.**
Status: Applicable
Comment: In snowflake mode the app processes confidential corporate data and a corporate identity; device security enforcement is organizational. Follow-up: add a data-classification/handling note to README/ARCHITECTURE for compliance completeness.

**Avoid storing sensitive data locally; retrieve from remote endpoints and keep in memory only as needed.**
Status: Applicable
Comment: Matches the design and is largely a control in place: data is fetched on demand from Snowflake, held only in session_state, and never written to disk; caches clear on restart/domain switch. Residual point: in-memory copies are unencrypted in the local path.

**Prevent exposure of sensitive data via IPC, application logs, or backups.**
Status: Applicable
Comment: No IPC or backups exist. Logging is the relevant surface: the app logs failure reasons/stack traces, not row-level data. Follow-up: confirm exception traces cannot include bound filter values and keep log level at WARNING+ in shared environments.
