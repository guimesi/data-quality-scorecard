# Architecture, Design and Threat Modeling — Odin Threat Modeling Assessment

**Application:** `data-quality-scorecard`

**Framing context:**

**Current code/runtime:** local, single-user Streamlit app. No authentication of its own
(locally delegated to Snowflake `externalbrowser` SSO); no in-app authorization (delegated
to Snowflake RBAC); single-process monolith with one external dependency (Snowflake over TLS);
mock data by default. Verified during review: data-derived strings interpolated into HTML are
wrapped in `html.escape(...)`; TLS validation is never disabled (no `insecure_mode`/`verify=False`);
no `pickle`/`yaml.load`/`eval` anywhere.

**Production target: Streamlit in Snowflake (SiS), deployed from this GitHub repo** (app object
under *Projects → Streamlit*; code pulled via a Snowflake Git integration). Under SiS the app runs
in Snowflake's **sandboxed compute**, authenticated by the viewer's **Snowflake login**, executing
with the app's **owner's/caller's-rights role**, accessible to **any user granted USAGE on the
Streamlit object** (i.e. potentially multi-user), with deps from the **Snowflake Anaconda channel**
and logging via **event tables**.

> **SiS READINESS (was: critical mismatch — now largely remediated on `dev`):** the app was
> originally built for the *local* runtime only; the SiS-prep work has since landed on the `dev`
> branch. Current state:
> - **Data layer (DONE):** `src/snowflake_client.py` now auto-selects the in-platform **Snowpark
>   session** (`get_active_session()`) inside SiS and falls back to `snowflake.connector` +
>   `externalbrowser` for local dev; SQL stays parameterized (qmark `?` for Snowpark, `%s` for the
>   connector). `config/settings.py` imports `python-dotenv` defensively (no `.env` in SiS).
> - **Dependencies (DONE):** `environment.yml` (Snowflake Anaconda channel, `python=3.11`) now
>   declares the production deps; `requirements*.txt` are labelled local/CI-only.
> - **Deployment artifacts (DONE):** `deploy/` contains the Git-integration + least-privilege-role +
>   `CREATE STREAMLIT` reference SQL; ARCHITECTURE.md/README updated to describe the SiS deploy.
> - **Remaining gaps (still open):** the deploy SQL must be **run** in Snowflake (objects not yet
>   created); **B2 branch protection** on the deploy branch is not set; **enterprise scanning**
>   (Erebor SAST / JFrog Xray / Nexus) is not yet wired (only report-only OSS scanners in CI —
>   see `.github/workflows/security.yml`); the production (Anaconda) dep set must be scanned via
>   JFrog Xray (PyPI tools can't resolve it); **data classification** is undeclared; and
>   account-specific items (plotly/scikit-learn Anaconda versions, post-deploy smoke test) need
>   confirmation. The GitHub repo is the deploy source, so committed secrets would reach production
>   — secret scanning is now in CI (report-only). Items below carry a "SiS production note" where
>   the runtime changes the answer.

---

## Authentication Architectural Requirements

**Question:** Section directive.
**Status:** Applicable
**Comment:** Directive; items assessed individually. Key context: the app implements **no authentication of its own**; all authN is delegated to Snowflake via `externalbrowser` SSO.

**Question:** Use a single, well-vetted authentication mechanism with strong auth and robust logging/monitoring.
**Status:** Applicable
**Comment:** Locally, a single mechanism is used: Snowflake `externalbrowser` SSO (`src/snowflake_client.py:79-91`, default in `config/settings.py:29`), routed through the corporate IdP with MFA/strong auth. **SiS production note:** under Streamlit in Snowflake the user is already authenticated by their **Snowflake account login** (Snowsight); the externalbrowser path is not used in production. Either way authN is a single, well-vetted, platform-delegated mechanism. Auth abuse logging/monitoring lives at the IdP/Snowflake tier, **not** in the app (no login UI). Gap to declare: no app-side authentication logging/alerting (in production, rely on Snowflake login history / access history).

**Question:** Follow EA mandates (Ardoq link).
**Status:** Applicable
**Comment:** Organizational/Enterprise-Architecture compliance requirement; cannot be verified from the repository alone. Assumption/follow-up: confirm the externalbrowser-SSO + Snowflake design conforms to the linked EA mandate before sign-off. Flagged as uncertain pending EA review.

**Question:** Consistent control strength across all authentication pathways / identity APIs; avoid weaker alternatives.
**Status:** Applicable
**Comment:** Locally only one auth pathway exists (externalbrowser), but `SNOWFLAKE_AUTHENTICATOR` is **env-configurable** (`config/settings.py:29`), so an operator could substitute a weaker method (e.g. username/password `snowflake` auth) — a dev-runtime concern. **SiS production note:** in SiS there is no authenticator setting at all (auth is the Snowflake session via `get_active_session()`), so the weaker-alternative risk does not exist in production. Follow-up: document that password-based authenticators must not be used for any local/non-SiS execution.

**Question:** Authenticate communications between components/APIs/middleware using individual user accounts.
**Status:** Applicable
**Comment:** The app is a single-process monolith (no inter-service APIs/middleware), so component-to-component auth is largely moot. The one external link (Snowflake) authenticates with the **individual user's** SSO identity — not a shared service account — which satisfies the individual-account principle and gives per-user accountability in Snowflake's audit trail.

---

## Data Protection and Privacy Architectural Requirements

**Question:** Section directive.
**Status:** Applicable
**Comment:** Directive; items assessed individually.

**Question:** Each protection level has defined requirements (encryption, integrity, retention, privacy, confidentiality) consistently applied.
**Status:** Applicable
**Comment:** The repository defines **no formal protection-level/data-classification scheme**. The schema processed in snowflake mode (`UC_GP_CSC`, Quality schemas) is undeclared in terms of sensitivity. Gap/follow-up: define the protection level for the warehouse data this app reads; this `odin.md` should record the classification so downstream encryption/retention requirements are explicit. Relevant to compliance review.

**Question:** Process to identify and classify all sensitive data into protection levels.
**Status:** Applicable
**Comment:** No data-classification process is present in the repo. The app does process potentially confidential corporate cost-estimate/quality data plus a corporate user identity (snowflake mode). Gap/follow-up: classify the source datasets and exported scorecards; needed to size the encryption/handling controls already discussed in the Data Protection theme.

**Question:** Regularly verify protection requirements are integrated into the architecture.
**Status:** Applicable
**Comment:** No recurring verification process is documented. This Odin assessment is the current point-in-time verification. Follow-up: schedule periodic re-assessment, especially before enabling snowflake mode against new schemas.

---

## Cryptographic Architectural Requirements

**Question:** Section directive.
**Status:** Applicable
**Comment:** Directive; items assessed individually. Overarching fact: the app **manages no cryptographic key material or secrets of its own** — all crypto is delegated to the Snowflake connector (TLS) and the IdP (SSO tokens).

**Question:** Protect key material/secrets using secure key vaults or API-based alternatives.
**Status:** Not Applicable
**Comment:** The app generates and stores no cryptographic keys or passwords. `externalbrowser` SSO means no secret credential is persisted; the only local config (`.env`) holds non-secret connection identifiers (account/user/warehouse/schema) and is gitignored. There is no key material to place in a vault. (The commit-hygiene risk of the local `.env` is captured under the Data Protection theme.)

**Question:** All keys/passwords replaceable; re-encryption process; key-management policy per NIST SP 800-57.
**Status:** Not Applicable
**Comment:** No app-managed keys or passwords exist to rotate or re-encrypt. SSO token lifecycle and TLS material are managed by the IdP and the Snowflake connector, outside this codebase.

**Question:** Limit symmetric keys/passwords/API secrets shared with clients; treat client-shared secrets as clear-text.
**Status:** Not Applicable
**Comment:** The app shares no symmetric keys, passwords, or API secrets with any client. There is no client-secret distribution channel.

---

## Secure Software Development Lifecycle Requirements

**Question:** Section directive.
**Status:** Applicable
**Comment:** Directive; items assessed individually.

**Question:** Centralized, simple, reusable security controls (avoid duplication).
**Status:** Applicable
**Comment:** Positive evidence: security-relevant logic is centralized and reused — a single CSV-injection sanitizer (`_sanitize_csv_cell`, `ui/step_06/_export.py:28`), one parameterized Snowflake fetch path (`src/data_product_builder.py`), one settings module, and a single `html.escape` discipline for HTML rendering. Supports the "centralized control" objective for SAST review.

**Question:** Threat modeling for every design change / sprint planning.
**Status:** Applicable
**Comment:** This Odin threat-modeling assessment is the current artifact. Follow-up: integrate lightweight threat modeling into future changes (e.g. before enabling new Snowflake schemas or adding upload/import features).

**Question:** Adopt a secure SDLC integrating security at every stage.
**Status:** Applicable
**Comment:** Controls in place: CI (`.github/workflows/tests.yml`) runs `ruff` lint + `pytest` (~1,250 tests, ≥90% coverage, on Python 3.11), and a **report-only security workflow** (`.github/workflows/security.yml`) now runs **SAST (bandit), SCA (pip-audit), and secret scanning (gitleaks)** on push to `main`/`dev` and PRs. ARCHITECTURE.md/README now describe the SiS deployment. **Residual gaps:** the OSS scanners are an early-warning layer, **not** the authoritative enterprise tools — **Erebor (SAST) / JFrog Xray (SCA) / Nexus** and **Heimdall (DAST)** still need wiring via the org pipeline; and **branch protection** on the deploy branch (B2) is not yet set. Follow-up: onboard to the org scanning pipeline and enforce branch protection + PR review.

**Question:** Security analysis of high-level architecture and connected remote services.
**Status:** Applicable
**Comment:** `ARCHITECTURE.md` documents the architecture, data flows, and the single connected remote service (Snowflake). This assessment extends that with the security view. Control in place; the one remote dependency is well-scoped.

**Question:** Secure coding checklist/guidelines available to developers and testers.
**Status:** Applicable
**Comment:** Informal secure-coding guidance exists in ARCHITECTURE.md ("Silent except is forbidden", guarded `.index()`, parameterized SQL pushdown that is "injection-safe", CSV-injection sanitization). There is **no formal security checklist/policy** document. Gap/follow-up: formalize a secure-coding checklist for contributors.

**Question:** User stories/features include functional security constraints (permissions/access limits).
**Status:** Applicable
**Comment:** Revised for the SiS target. Because the deployed app can be multi-user (USAGE grants) and runs under a shared owner's-rights role, the access model is a genuine design decision that should be captured as an explicit requirement: *who may open the app* and *what data the app's role may read*. No in-app feature-permission layer exists today. Follow-up: document these constraints (intended audience, role scope, whether any data must be hidden per viewer) before deployment.

**Question:** Document/justify all trust boundaries, components, and significant data flows.
**Status:** Applicable
**Comment:** ARCHITECTURE.md documents components and data flows; the primary trust boundary is the app↔Snowflake TLS/SSO connection (browser↔app is loopback). This `odin.md` should formalize that single trust boundary. Control largely in place.

---

## Mobile architecture Requirements

**Question:** Section directive.
**Status:** Applicable
**Comment:** Directive; however the entire section is **Not Applicable** — `data-quality-scorecard` is a desktop/browser Streamlit app, not a mobile application (no iOS/Android codebase, no mobile dependencies).

**Question:** Mobile app architecture with centralized controls and threat model.
**Status:** Not Applicable
**Comment:** No mobile application exists.

**Question:** Privacy-regulation compliance, update enforcement, mobile key management.
**Status:** Not Applicable
**Comment:** No mobile application exists; no mobile key/update mechanisms apply.

**Question:** Security across SDLC, responsible-disclosure policy, sensitive-data identification (mobile).
**Status:** Not Applicable
**Comment:** No mobile application exists. (General SDLC/sensitive-data items are covered in the SDLC and Data Protection themes.)

---

## Input and Output Architectural Requirements

**Question:** Section directive.
**Status:** Applicable
**Comment:** Directive; items assessed individually.

**Question:** Avoid serialization with untrusted clients; if used, add integrity/encryption to prevent deserialization/object-injection attacks.
**Status:** Applicable
**Comment:** The app performs **no untrusted deserialization** — confirmed no `pickle`/`yaml.load`/`marshal`/`eval` anywhere. Serialization is **output-only**: CSV and `json.dumps(...)` exports (`ui/step_06/_export.py`); the config JSON is exported, never re-imported. Control in place (no object-injection surface). Positive evidence for SAST deserialization checks.

**Question:** Output encoding as close to the interpreter as possible.
**Status:** Applicable
**Comment:** Two output interpreters: the **browser** and **spreadsheet apps**. For the browser, the app uses `unsafe_allow_html=True` widely but **escapes data-derived values at the render site** with `html.escape(...)` (e.g. `dp.name`, code, status label in `ui/step_06/_breakdown.py:115-117`); static stylesheets carry no user data. For CSV, `_sanitize_csv_cell` neutralizes formula injection at write time. Control in place. Follow-up/uncertainty: there are ~100 `unsafe_allow_html` sites; recommend a periodic audit to ensure every dynamic value (especially Snowflake-derived column names/values) remains escaped, since an unescaped one would be a stored-XSS vector.

**Question:** Establish input/output handling requirements based on data type/content/regulation.
**Status:** Applicable
**Comment:** Input handling is type/catalog-driven: domain/system selections come from fixed catalogs, weights/params are numeric, project-filter IDs run through `_canonicalize_id`, and `dqr_validation.py` checks per-dimension type/param compatibility before a rule runs. Output handling defined for CSV/JSON exports (sanitized, typed). Control in place; the regulatory/classification dimension ties back to the open data-classification follow-up.

**Question:** Enforce input validation at a trusted service layer.
**Status:** Applicable
**Comment:** Validation runs in the Python layer (server-side relative to the browser): constrained selections, `_canonicalize_id` normalization, guarded `.index()` lookups, and `src/dqr_validation.py` compatibility checks. User-supplied filter values reach Snowflake only as **parameterized bind values**, never concatenated into SQL (`src/data_product_builder.py:79-110`). Control in place; relevant positive evidence for SAST injection checks.

---

## Access Control Architectural Requirements

**Question:** Section directive.
**Status:** Applicable
**Comment:** Directive; items assessed individually. Core fact: the app enforces **no access control of its own**; data authorization is delegated to Snowflake RBAC via the user's SSO identity.

**Question:** Single, well-vetted access-control mechanism; all requests pass through it.
**Status:** Applicable
**Comment:** Access to data is governed by a single mechanism — Snowflake **role/RBAC**, evaluated server-side. The app has no alternative data-access path (only the Snowflake connection). Enforcement is external (Snowflake), not in-app. **SiS production note:** two distinct controls now apply — (a) **USAGE grants on the Streamlit object** decide *who can open the app* (potentially multi-user), and (b) the app's **owner's/caller's-rights role** decides *what data the app can read*. Both must be deliberately scoped. Follow-up: define and document who is granted the app and under which role it executes.

**Question:** Component communications use least necessary privilege.
**Status:** Applicable
**Comment:** Locally the connection runs with the **user's own role** (optional `SNOWFLAKE_ROLE`) and warehouse `TRUSTED_WH`; the app issues only `SELECT` (read-only). **SiS production note:** in SiS the app runs with its **owner's-rights role** by default, which becomes the single most important access control — if that role is over-privileged, every viewer effectively inherits it. Follow-up (high priority): create a dedicated **least-privilege, read-only** role for the SiS app scoped to exactly the required schemas (`UC_GP_CSC`, Quality), and run the app under it rather than a broad personal/admin role.

**Question:** Adaptable access-control solution; trusted server-side enforcement points, not client-side.
**Status:** Applicable
**Comment:** Enforcement is entirely server-side at Snowflake; there is no client-side access decision to bypass (the app holds no auth tokens and makes no authorization decisions). Aligns with "no client-side enforcement."

**Question:** Enforce Principle of Least Privilege across all functions/data/URLs/services/resources.
**Status:** Applicable
**Comment:** The app is **read-only** by design — `snowflake_client` performs only `SELECT` (no INSERT/UPDATE/DELETE/DDL), so even a compromised session cannot mutate warehouse data. Follow-up: pair this with a read-only Snowflake role to enforce least privilege at the platform tier.

**Question:** Implement ABAC/feature-based access control with role-allocated permissions.
**Status:** Applicable
**Comment:** Revised in light of the SiS production target. The app implements no in-app ABAC/feature gating, **but** SiS makes it potentially **multi-user** (anyone granted USAGE on the Streamlit object can open it), and all such users share the app's single owner's-rights role — so they all see the same data with no per-user/attribute differentiation inside the app. Authorization is delegated entirely to Snowflake RBAC (grants on the object + the role's grants). Gap/decision to document: if different viewer populations must see different data (e.g. per-domain or per-project), the owner's-rights model cannot express that and either caller's-rights, separate app instances, or Snowflake row-access policies would be required. Follow-up: confirm the intended audience and whether a single shared role is acceptable.

---

## Business Logic Architectural Requirements

**Question:** Section directive.
**Status:** Applicable
**Comment:** Directive; items assessed individually.

**Question:** High-value flows (auth, session mgmt, access control) thread-safe and resistant to TOCTOU races.
**Status:** Not Applicable
**Comment:** The app implements no authentication, session-management, or access-control business logic of its own (all delegated to Snowflake/IdP). Streamlit executes a session's script **sequentially** per rerun, so there are no concurrent high-value security flows susceptible to TOCTOU within the app.

**Question:** Maintain definitions/documentation of components and their business/security functions.
**Status:** Applicable
**Comment:** `ARCHITECTURE.md` thoroughly documents each module's role (engines, builders, scorecard, UI steps, session/navigation). Control in place; supports security assessment transparency.

**Question:** Critical business-logic flows do not share unsynchronized state.
**Status:** Not Applicable
**Comment:** No security-critical flows exist in the app. There is module-level shared state (the process-wide `_SHARED` Snowflake client and the stateful mock RNG), but it is non-security, single-user, and accessed sequentially per Streamlit run; the shared client is explicitly closed/reset on restart/domain switch. No unsynchronized security state.

---

## Configuration Architectural Requirements

**Question:** Section directive.
**Status:** Applicable
**Comment:** Directive; items assessed individually.

**Question:** Sandbox/containerize/isolate components at network level; sign binaries to untrusted devices, use trusted connections/verified endpoints.
**Status:** Applicable
**Comment:** Locally the app is **not containerized or sandboxed** — it runs directly via `streamlit run app.py` on the user's machine (relies on the host for isolation). **SiS production note:** Streamlit in Snowflake runs the app inside Snowflake's **managed, sandboxed compute** with platform-enforced network isolation — so in production this requirement is **largely satisfied by the platform**, not the app. No binaries are distributed/signed (source pulled from Git); no unsafe deserialization to isolate. Follow-up: document the SiS execution/isolation model in ARCHITECTURE.md (currently it only describes local execution).

**Question:** Segregate components by trust level (firewall/API gateways); run components under unique low-privilege OS accounts.
**Status:** Applicable
**Comment:** Single component; it runs under the **invoking user's own OS account**, not a dedicated low-privilege service account. The only trust boundary (Snowflake) is crossed over TLS+SSO. Gap/assumption: no separate service account or network segmentation; trust segregation depends on the corporate host. Follow-up if centrally hosted.

**Question:** Build pipeline with automated secure-deployment verification, warns of outdated/insecure components, avoids deprecated client-side tech.
**Status:** Applicable
**Comment:** **Most pipeline-relevant item — substantially improved.** CI now runs lint + tests plus a report-only **SCA (pip-audit)** and **secret scan** (`.github/workflows/security.yml`). Dependencies were **refreshed to clear known advisories** (streamlit 1.50→≥1.54, urllib3 1.26→2.x, pyarrow/requests/pyjwt/tornado/pillow/python-dotenv/pytest); `pip-audit` now reports **no known vulnerabilities** on `requirements.lock`. The production dependency set is declared in **`environment.yml`** (Snowflake Anaconda channel). **Residual gaps:** the in-repo SCA scans `requirements.lock` (PyPI) as a proxy — the **authoritative SiS scan must run via JFrog Xray against the Anaconda packages** (PyPI tools can't resolve the conda set); a **deploy-verification step** for the Git→Snowflake integration and **dependency-update alerting** are still to add. Follow-up: onboard `environment.yml` to JFrog Xray and add deploy verification.

---

## Secure File Upload Architectural Requirements

**Question:** Section directive.
**Status:** Applicable
**Comment:** Directive; the app has **no file-upload feature**, so the upload-specific items below are Not Applicable. It only produces user-initiated **downloads**.

**Question:** Serve user-uploaded files as octet-stream or from an unrelated domain.
**Status:** Not Applicable
**Comment:** No uploads. The app's downloads are generated in-memory and delivered via Streamlit `download_button` as typed attachments (`text/csv`, `application/json`) — not served from a web root, so the direct-access risk this addresses does not arise.

**Question:** Store user-uploaded files outside the web root.
**Status:** Not Applicable
**Comment:** No uploads and no server-side file persistence; exports exist only as in-memory bytes handed to the browser.

**Question:** Implement a Content Security Policy (CSP) to reduce XSS from uploaded files.
**Status:** Not Applicable
**Comment:** No uploaded files. (The app does not set a CSP — a general Streamlit limitation — but with no upload vector and `html.escape` on rendered data, this upload-specific control does not apply. XSS hygiene is tracked under the I/O output-encoding item.)

---

## Malicious Software Architectural Requirements

**Question:** Section directive.
**Status:** Applicable
**Comment:** Directive; item assessed below.

**Question:** Source-code control in use; check-ins tied to issues/tickets; access control; identifiable users; change traceability.
**Status:** Applicable
**Comment:** The project is in Git/GitHub with identifiable authorship (commits by Guilherme Oliveira) and GitHub access control. Gap: the repo currently shows a single "Initial commit" with **no evidence of issue/ticket linkage, PR review, or branch protection**. **SiS production note (raises the stakes):** because SiS deploys directly from this GitHub repo via a Git integration, the repo *is* the production artifact — an unreviewed or malicious commit (or a committed secret) flows straight into the deployed app. Follow-up (high priority): enforce branch protection + mandatory PR review + ticket references on the branch SiS deploys from, and restrict who can push.

---

## Communications Architectural Requirements

**Question:** Section directive.
**Status:** Applicable
**Comment:** Directive; items assessed individually.

**Question:** Verify authenticity of each party; validate TLS certificates and chains.
**Status:** Applicable
**Comment:** The Snowflake connector validates TLS server certificates (and OCSP) by default, and the app **does not disable it** — confirmed no `insecure_mode`/`verify=False`/OCSP-disabling flags anywhere. Control in place via connector defaults. Follow-up: keep a guard that these are never set to insecure values.

**Question:** Encrypt communications between components (containers/systems/sites/cloud).
**Status:** Applicable
**Comment:** Locally, the app↔Snowflake link is TLS-encrypted and browser↔app is loopback (localhost). **SiS production note:** in SiS the data-access link is **in-platform** (the app runs inside Snowflake, reaching data via the active session — no external network hop), and the user↔app channel is Snowsight over **Snowflake-managed TLS**. Encryption in transit is platform-provided in production. Control in place in both runtimes.

**Question:** Maintain these practices consistently across all components.
**Status:** Applicable
**Comment:** There is a single external communication path (Snowflake), consistently TLS-protected; no plaintext inter-component links exist. Consistency is trivially satisfied given the monolithic, single-link architecture.

---

## Errors, Logging and Auditing Architectural Requirements

**Question:** Section directive.
**Status:** Applicable
**Comment:** Directive; items assessed individually.

**Question:** Verify logging practices are adhered to and logs are securely managed (integrity/confidentiality).
**Status:** Applicable
**Comment:** The app uses stdlib `logging` (`logger.warning(..., exc_info=True)`) per the ARCHITECTURE "no silent except" rule; logs record failure reasons/traces, not row-level data. Logs go to the **local console/stderr** with no secure storage/retention/integrity management. Gap: no managed log storage. Follow-up/uncertainty: confirm connector exception traces captured via `exc_info` cannot surface bound filter values; keep log level at WARNING+ in shared environments.

**Question:** Securely transmit logs to a remote system for analysis/alerting/escalation.
**Status:** Applicable
**Comment:** Revised for the SiS target. Locally there is no remote log shipping. **SiS production note:** Streamlit in Snowflake supports centralized logging/telemetry via **Snowflake event tables**, and Snowflake **Access History / Query History** centrally records what the app's role queried. The app does not currently configure event-table logging. Follow-up: enable event-table logging for the SiS app and rely on Snowflake access/query history for centralized analysis and alerting — this is achievable in production where it was not locally.

**Question:** Use a standardized logging format/approach consistently across the system.
**Status:** Applicable
**Comment:** Logging is applied consistently via `logging.getLogger(__name__)` across modules, with the ARCHITECTURE-mandated pattern for exception handling. No custom structured (e.g. JSON) log format is defined. Control partial; consistent approach in place.
