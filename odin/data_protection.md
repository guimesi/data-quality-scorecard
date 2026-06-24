# Data Protection — Odin Threat Modeling Assessment

**Application:** `data-quality-scorecard`

**Framing context (drives the Applicable / Not Applicable calls below):**

The app was **developed and currently runs locally** (`streamlit run app.py`, localhost,
mock data by default; in snowflake mode it connects out via `snowflake.connector` +
`externalbrowser` SSO). It persists nothing to disk itself (exports are user-initiated
in-memory downloads) and holds data only in Streamlit `session_state`.

**Production target: Streamlit in Snowflake (SiS), deployed from this GitHub repo.** The
app object lives under *Projects → Streamlit* in the Snowflake account; Snowflake pulls
the code from GitHub via a Git integration. Under SiS the app runs inside Snowflake's
**sandboxed, warehouse-backed compute**; Snowflake provides **encryption at rest, in
transit, and in-platform memory by default**, retention/backup via **Time Travel /
Fail-safe**, platform edge protection, and **event tables** for logging. Authentication
is the viewer's Snowflake login; data access is the app's Snowflake role (owner's/caller's
rights).

> **SiS readiness (was a code/runtime mismatch — now remediated on `dev`):** the data layer
> (`src/snowflake_client.py`) now auto-selects the in-platform **Snowpark session** inside SiS
> (connector + `externalbrowser` remains the local-dev fallback), and the production deps are
> declared in **`environment.yml`** (Snowflake Anaconda channel). So the app now runs in SiS and
> the dependency set is declared. Because the GitHub repo is the deployment source, any secret
> committed here would flow straight into the deployed app — **secret scanning is now in CI**
> (report-only, `.github/workflows/security.yml`), and `.env` remains gitignored/untracked.
> Items below note where the SiS target changes the answer ("SiS production note").

---

## General Data Protection Security Requirements

**Question:** Section directive — "Mark all Applicable/Not Applicable"
**Status:** Applicable
**Comment:** Section directive; each item below is individually assessed.

**Question:** Follow company-defined data retention periods and set up a backup plan on high-value data.
**Status:** Applicable
**Comment:** The app itself stores no data and has no retention/backup logic — source data lives in Snowflake (`INSIGHTS_DB`/domain-pinned DBs defined in `config/domains.py`, resolved in `src/snowflake_client.py`), whose retention/backup is governed by the warehouse and corporate policy, not this repo. The relevant in-scope artifacts are the **CSV/JSON scorecard exports** (`ui/step_06/_export.py`), which contain warehouse-derived (potentially high-value) data and leave the controlled environment as user-managed files. Control/assumption: retention & backup are inherited from Snowflake + corporate policy; the app provides none. **SiS production note:** in production, retention/backup of source data is handled by Snowflake (Time Travel/Fail-safe) and exported scorecards stay within the Snowflake boundary rather than being downloaded to a local machine. Follow-up: document this inheritance so compliance tooling doesn't expect an app-side backup mechanism.

**Question:** Sensitive data should only be collected/retained with a justified business reason, and avoid exposing all object properties (excessive data exposure).
**Status:** Applicable
**Comment:** Directly relevant. The CSV export (`_build_rowscores_csv`, `ui/step_06/_export.py:165-200`) starts from `out = dp.df.copy()` — i.e. it emits **every column** of the joined data product plus per-rule scores and joined reference columns. In Snowflake mode this can surface all source attributes, not just those needed for scoring — a genuine excessive-data-exposure consideration. Business justification (building a quality scorecard) exists, but column minimization is not enforced. Follow-up/gap: consider limiting exported columns to CDEs + score columns. Relevant to data-classification review by SAST/compliance tooling.

---

## General Server-Side Data Protection requirements

**Question:** Section directive.
**Status:** Applicable
**Comment:** Directive; items assessed individually. Note the app is not a hosted multi-user webservice — it is a locally hosted Streamlit app — which shapes the answers below.

**Question:** Design the webservice to access the minimum number of systems (per MPI guidelines).
**Status:** Applicable
**Comment:** The app already minimizes external access: mock mode reaches **zero** external systems; snowflake mode reaches exactly **one** (Snowflake), reading only the configured `database.schema` tables (`src/snowflake_client.py:_resolve_location`). No other outbound integrations exist (grep confirms no `requests`/`urllib`/HTTP calls in source). Control in place: single, minimal backend dependency. Useful as positive evidence for MPI/minimal-access review.

**Question:** Avoid caching sensitive data in caches/RAM, or protect it; encrypt RESTRICTED data at-rest, in-transit, and in-memory.
**Status:** Applicable
**Comment:** **In-transit:** Snowflake connector uses TLS (control in place). **At-rest:** the app writes nothing at rest, but user-downloaded CSV/JSON are **plaintext, unencrypted**. **In-memory:** data is held as plain pandas DataFrames in `session_state` and a reference-dataset cache (`src/reference_data.py`) — **not encrypted in memory**. Gap (local runtime): if Snowflake data is classified RESTRICTED, the local app does not meet in-memory/at-rest encryption for that tier. **SiS production note:** under Streamlit in Snowflake the app runs inside Snowflake's sandbox, where data is **encrypted at rest, in transit, and in-platform memory by default**, and exports stay within the Snowflake/Snowsight boundary — so this requirement is largely **satisfied by the platform** in production. The residual gap is the in-memory plaintext exposure in the current *local* execution path; follow-up: confirm classification of `UC_GP_CSC`/Quality schemas and prefer the SiS path for RESTRICTED data.

**Question:** Binding client-provided data to models without filtering (Mass Assignment).
**Status:** Not Applicable
**Comment:** There is no auto-binding of request payloads to objects. Domain models (`DataProduct`, `DQRAssignment`, etc. in `src/models.py`) and the config JSON are constructed **field-by-field** from constrained Streamlit widgets (selections from fixed catalogs, numeric weights/params), not from a mapped HTTP request body. No ORM/auto-mapper exists, so the mass-assignment vector does not apply.

---

## General Data Protection requirements

**Question:** Section directive.
**Status:** Applicable
**Comment:** Directive; items assessed individually.

**Question:** Ensure all cached/temporary copies of sensitive data are protected or purged after use.
**Status:** Applicable
**Comment:** The app caches data products, scorecards, and reference datasets in `session_state`, plus a process-wide shared Snowflake connection (`get_shared_client`). Purge controls exist: `_clear_workflow_state_for_domain_switch` / `restart_app` clear workflow state and call `close_shared_client()` on restart and on any domain/mode switch (`close_shared_client` in `src/snowflake_client.py`). Gap: within an active session the cached data persists unencrypted in RAM until restart/exit. Control is partial (purge-on-restart, not continuous protection); acceptable for a local single-user model but should be stated honestly.

**Question:** Prevent sensitive data from being cached in local storage, memory, or server components.
**Status:** Applicable
**Comment:** Data is necessarily held in **memory** (`session_state`) to compute scores — this cannot be fully prevented in a pandas/Streamlit app. Mitigations: the app writes nothing to **disk/local storage** (no `open(...,'w')`/file writes in source), and mock mode involves no sensitive data at all. Declare as: in-memory caching is unavoidable and unencrypted; no local-storage persistence by the app. Consistent with the at-rest finding above.

**Question:** Securely store backups; test regular backups of important data.
**Status:** Not Applicable
**Comment:** The application creates and stores no backups; it has no persistence layer. Backup of the underlying high-value data is a Snowflake/platform responsibility. **SiS production note:** in production this is explicitly covered by Snowflake **Time Travel / Fail-safe** on the source tables — a platform control, not an app control.

**Question:** Minimize request parameters; sensitive data must not be in headers or query params.
**Status:** Not Applicable
**Comment:** The app exposes no custom HTTP API — Streamlit uses its own WebSocket transport and the developer does not construct request headers/cookies/query strings. Sensitive filter values (project IDs) reach Snowflake as **parameterized bind values** (`cursor.execute(sql, params)`, `src/data_product_builder.py:79-110`), never embedded in URLs or headers, so the header/query-param exposure vector does not apply.

**Question:** If WAF/DDoS not used, detect and alert on abnormal request patterns.
**Status:** Not Applicable
**Comment:** Locally the app is not internet-facing (localhost, single user). **SiS production note:** under Streamlit in Snowflake the app is reached only through authenticated Snowsight/Snowflake sessions, so edge protection (WAF/DDoS/anomaly detection) is **provided by the Snowflake platform**, not the app. Either way this is not an app-implemented control; delegated to platform/host.

---

## Client-side Data Protection requirements

**Question:** Section directive.
**Status:** Applicable
**Comment:** Directive; the "client" here is the browser tab rendering the Streamlit UI.

**Question:** Set anti-caching headers to prevent sensitive data being cached in browsers.
**Status:** Applicable
**Comment:** Warehouse data is rendered into the browser DOM (dashboard, tables, charts). The app does not (and via Streamlit largely cannot) set custom anti-cache HTTP headers, so it relies on framework defaults. Locally, risk is bounded by localhost/single-user. **SiS production note:** in Streamlit in Snowflake the UI is served and chrome-controlled by **Snowsight/Snowflake**, not the app, so cache-control behaviour is a platform responsibility. Gap/assumption: no app-controlled cache headers in either runtime; mitigated by the access being authenticated and platform-served.

**Question:** Clear authenticated data from client storage after session termination.
**Status:** Not Applicable
**Comment:** The app stores no authentication material in the browser. Snowflake auth is delegated to `externalbrowser` SSO (handled by the connector/IdP, not persisted by the app), and Streamlit `session_state` lives server-side in the Python process, not in browser storage. There is no app-managed authenticated client storage to clear.

**Question:** Ensure client-side storage does not contain sensitive data or PII.
**Status:** Applicable
**Comment:** The app does not deliberately write to browser `localStorage`, but rendered scorecard data and typed inputs (e.g. project filter IDs) exist transiently in the DOM/widget state during a session. No PII is intentionally collected; the user identity is a corporate email used only for Snowflake SSO, not stored client-side by the app. Control/assumption: no intentional sensitive client-side persistence; data is session-transient. Follow-up: verify no Streamlit component persists rendered data beyond the session.

---

## Data Storage and Privacy Requirements

**Question:** Section directive.
**Status:** Applicable
**Comment:** Directive; several items below are mobile-app-oriented and assessed accordingly for this desktop/browser app.

**Question:** Use system credential storage for sensitive data; do not expose it via the UI.
**Status:** Applicable
**Comment:** No password/secret is stored by the app — locally, `externalbrowser` SSO means credentials are handled by the IdP/browser (`src/snowflake_client.py` `connect()`). The `.env` holds only non-secret identifiers (account/user/warehouse/schema), is **gitignored and not tracked** (verified via `git ls-files`), and `.env.example` uses placeholders only. The UI never displays credentials. **SiS production note:** under Streamlit in Snowflake there is no `.env`/`externalbrowser`/dotenv at runtime — the app's identity is the **active Snowflake session** (owner's/caller's rights), so credential handling is delegated to the platform. Gap to flag: the **local `.env` contains a real corporate Snowflake account identifier and a corporate email address** (values intentionally not reproduced here) — fine while untracked, but because this GitHub repo is the SiS deployment source, an accidental commit would ship straight into production. Control added: **secret scanning (gitleaks) now runs in CI** (`.github/workflows/security.yml`, report-only). Follow-up: keep `.env` out of commits (consider a pre-commit gitleaks hook too) and onboard to the org's secret-scanning if required.

**Question:** Encrypt locally stored sensitive data using hardware-backed keys.
**Status:** Not Applicable
**Comment:** The app persists no sensitive data locally and has no local keystore (hardware-backed key encryption is a mobile-platform concept). The only local artifacts are user-initiated CSV/JSON downloads, which are plaintext and become the user's/OS's responsibility once saved. (Related gap — unencrypted exports — already captured under at-rest above.)

**Question:** Clear sensitive data from views when app is backgrounded; wipe local storage after failed auth attempts.
**Status:** Not Applicable
**Comment:** Mobile lifecycle concepts that don't map to a desktop browser Streamlit app: there is no app-background event and no app-level login/lockout flow (authentication is delegated to Snowflake SSO; the app has no password attempts to count or lock).

**Question:** Educate users about PII processing and enforce device security policies.
**Status:** Applicable
**Comment:** In snowflake mode the app processes potentially confidential corporate data and a corporate user identity. Enforcement of device security (MDM/disk encryption) is organizational, not in the app. Assumption: the app runs on a corporate-managed, policy-compliant device. Follow-up: add a data-classification/handling note to README/ARCHITECTURE so users understand what is processed; relevant to compliance documentation completeness.

**Question:** Avoid storing sensitive data locally; retrieve from remote endpoints and keep in memory only as needed.
**Status:** Applicable
**Comment:** This matches the app's actual design and is largely a **control in place**: data is fetched on demand from Snowflake, held only in `session_state`, and never written to disk by the app (no file-write calls in source); caches are cleared on restart/domain switch. **SiS production note:** the SiS target strengthens this — data never leaves the Snowflake boundary at all (no local download to a user device), satisfying "retrieve from remote, keep in memory only" by construction. Residual point is that in-memory copies are unencrypted in the *local* path (covered above; platform-encrypted under SiS).

**Question:** Prevent exposure of sensitive data via IPC, application logs, or backups.
**Status:** Applicable
**Comment:** No IPC mechanisms and no backups exist in the app. **Logging** is the relevant surface: the app uses `logging` with `logger.warning(..., exc_info=True)` in `src/snowflake_client.py` and `src/reference_data.py`, and ARCHITECTURE mandates no silent excepts. These log failure reasons/stack traces, not row-level data. Control: logs avoid dumping dataset contents. Follow-up/uncertainty: confirm that connector exception traces captured via `exc_info` cannot include bound filter values or schema details at a verbose log level; keep log level at WARNING+ in any shared environment.
