## Authentication Architectural Requirements

**Section directive.**
Status: Applicable
Comment: Items assessed individually. The app implements no authentication of its own; all authN is delegated to Snowflake via externalbrowser SSO.

**Use a single, well-vetted authentication mechanism with strong auth and robust logging/monitoring.**
Status: Applicable
Comment: A single platform-delegated mechanism is used (externalbrowser SSO locally; the Snowflake account login under SiS), routed through the corporate IdP with MFA. Gap: no app-side auth logging/alerting; rely on Snowflake login history.

**Follow EA mandates (Ardoq link).**
Status: Applicable
Comment: EA-compliance requirement that cannot be verified from the repo alone. Follow-up: confirm the SSO + Snowflake design conforms to the linked EA mandate before sign-off.

**Consistent control strength across all authentication pathways / identity APIs; avoid weaker alternatives.**
Status: Applicable
Comment: Only externalbrowser is used locally, but SNOWFLAKE_AUTHENTICATOR is env-configurable, so an operator could substitute a weaker method; no such setting exists under SiS. Follow-up: document that password-based authenticators must not be used.

**Authenticate communications between components/APIs/middleware using individual user accounts.**
Status: Applicable
Comment: Single-process monolith, so component-to-component auth is moot. The one external link (Snowflake) authenticates with the individual user's SSO identity, not a shared service account, giving per-user accountability.

## Data Protection and Privacy Architectural Requirements

**Section directive.**
Status: Applicable
Comment: Items assessed individually.

**Each protection level has defined requirements (encryption, integrity, retention, privacy, confidentiality) consistently applied.**
Status: Applicable
Comment: The repo defines no formal protection-level/data-classification scheme; the schemas read in snowflake mode are undeclared for sensitivity. Gap/follow-up: define the protection level so encryption/retention requirements are explicit.

**Process to identify and classify all sensitive data into protection levels.**
Status: Applicable
Comment: No data-classification process exists, yet the app processes potentially confidential corporate cost/quality data plus a corporate user identity. Gap/follow-up: classify the source datasets and exported scorecards.

**Regularly verify protection requirements are integrated into the architecture.**
Status: Applicable
Comment: No recurring verification process is documented; this assessment is the current point-in-time check. Follow-up: schedule periodic re-assessment, especially before enabling snowflake mode against new schemas.

## Cryptographic Architectural Requirements

**Section directive.**
Status: Applicable
Comment: Items assessed individually. The app manages no cryptographic key material or secrets of its own; all crypto is delegated to the Snowflake connector (TLS) and the IdP (SSO tokens).

**Protect key material/secrets using secure key vaults or API-based alternatives.**
Status: Not Applicable
Comment: The app generates and stores no keys or passwords; externalbrowser SSO persists no secret credential, and the local .env holds only non-secret connection identifiers (gitignored). No key material to vault.

**All keys/passwords replaceable; re-encryption process; key-management policy per NIST SP 800-57.**
Status: Not Applicable
Comment: No app-managed keys or passwords exist to rotate or re-encrypt; SSO token lifecycle and TLS material are managed by the IdP and connector, outside this codebase.

**Limit symmetric keys/passwords/API secrets shared with clients; treat client-shared secrets as clear-text.**
Status: Not Applicable
Comment: The app shares no symmetric keys, passwords, or API secrets with any client; there is no client-secret distribution channel.

## Secure Software Development Lifecycle Requirements

**Section directive.**
Status: Applicable
Comment: Items assessed individually.

**Centralized, simple, reusable security controls (avoid duplication).**
Status: Applicable
Comment: Security logic is centralized and reused: a single CSV-injection sanitizer, one parameterized Snowflake fetch path, one settings module, and a single html.escape discipline for HTML rendering.

**Threat modeling for every design change / sprint planning.**
Status: Applicable
Comment: This Odin assessment is the current artifact. Follow-up: integrate lightweight threat modeling into future changes (e.g. before enabling new Snowflake schemas or adding upload features).

**Adopt a secure SDLC integrating security at every stage.**
Status: Applicable
Comment: CI runs ruff lint + pytest plus a report-only security workflow (bandit SAST, pip-audit SCA, gitleaks secret scan). Residual gaps: enterprise tools (Erebor, JFrog Xray, Nexus, Heimdall) and branch protection (B2) still need wiring.

**Security analysis of high-level architecture and connected remote services.**
Status: Applicable
Comment: ARCHITECTURE.md documents the architecture, data flows, and the single connected remote service (Snowflake); this assessment adds the security view. Control in place.

**Secure coding checklist/guidelines available to developers and testers.**
Status: Applicable
Comment: Informal secure-coding guidance exists in ARCHITECTURE.md (no silent except, guarded .index(), parameterized SQL, CSV-injection sanitization), but there is no formal checklist. Gap/follow-up: formalize a secure-coding checklist.

**User stories/features include functional security constraints (permissions/access limits).**
Status: Applicable
Comment: Because the SiS app can be multi-user under a shared owner's-rights role, the access model is a real design decision but no in-app permission layer exists. Follow-up: document who may open the app and what data its role may read before deployment.

**Document/justify all trust boundaries, components, and significant data flows.**
Status: Applicable
Comment: ARCHITECTURE.md documents components and data flows; the primary trust boundary is the app-to-Snowflake TLS/SSO connection (browser-to-app is loopback). Control largely in place.

## Mobile architecture Requirements

**Section directive.**
Status: Applicable
Comment: The entire section is Not Applicable: data-quality-scorecard is a desktop/browser Streamlit app, not a mobile application (no iOS/Android codebase, no mobile dependencies).

**Mobile app architecture with centralized controls and threat model.**
Status: Not Applicable
Comment: No mobile application exists.

**Privacy-regulation compliance, update enforcement, mobile key management.**
Status: Not Applicable
Comment: No mobile application exists; no mobile key/update mechanisms apply.

**Security across SDLC, responsible-disclosure policy, sensitive-data identification (mobile).**
Status: Not Applicable
Comment: No mobile application exists; general SDLC/sensitive-data items are covered in their own themes.

## Input and Output Architectural Requirements

**Section directive.**
Status: Applicable
Comment: Items assessed individually.

**Avoid serialization with untrusted clients; if used, add integrity/encryption to prevent deserialization/object-injection attacks.**
Status: Applicable
Comment: No untrusted deserialization: no pickle/yaml.load/marshal/eval anywhere. Serialization is output-only (CSV and json.dumps exports); the config JSON is exported, never re-imported. No object-injection surface.

**Output encoding as close to the interpreter as possible.**
Status: Applicable
Comment: Browser output uses unsafe_allow_html widely but escapes data-derived values at the render site with html.escape; CSV uses _sanitize_csv_cell at write time. Follow-up: periodically audit the ~100 unsafe_allow_html sites, since an unescaped dynamic value would be a stored-XSS vector.

**Establish input/output handling requirements based on data type/content/regulation.**
Status: Applicable
Comment: Input handling is type/catalog-driven (fixed catalogs, numeric params, canonicalized filter IDs, per-dimension compatibility checks); output handling is defined for sanitized, typed CSV/JSON exports. The regulatory dimension ties to the open data-classification follow-up.

**Enforce input validation at a trusted service layer.**
Status: Applicable
Comment: Validation runs server-side in the Python layer (constrained selections, _canonicalize_id, guarded .index(), compatibility checks). User filter values reach Snowflake only as parameterized bind values, never concatenated into SQL. Control in place.

## Access Control Architectural Requirements

**Section directive.**
Status: Applicable
Comment: Items assessed individually. The app enforces no access control of its own; data authorization is delegated to Snowflake RBAC via the user's SSO identity.

**Single, well-vetted access-control mechanism; all requests pass through it.**
Status: Applicable
Comment: Data access is governed solely by Snowflake RBAC, evaluated server-side, with no alternative path. Under SiS, USAGE grants decide who opens the app and the owner's/caller's-rights role decides what data it reads. Follow-up: define and document both.

**Component communications use least necessary privilege.**
Status: Applicable
Comment: Locally the connection runs with the user's own role and issues only SELECT; under SiS the owner's-rights role becomes the key control, since an over-privileged role is inherited by every viewer. Follow-up (high priority): create a dedicated least-privilege read-only role.

**Adaptable access-control solution; trusted server-side enforcement points, not client-side.**
Status: Applicable
Comment: Enforcement is entirely server-side at Snowflake; the app holds no auth tokens and makes no authorization decisions, so there is no client-side decision to bypass.

**Enforce Principle of Least Privilege across all functions/data/URLs/services/resources.**
Status: Applicable
Comment: The app is read-only by design (only SELECT, no INSERT/UPDATE/DELETE/DDL), so even a compromised session cannot mutate warehouse data. Follow-up: pair with a read-only Snowflake role to enforce least privilege at the platform tier.

**Implement ABAC/feature-based access control with role-allocated permissions.**
Status: Applicable
Comment: No in-app ABAC/feature gating; under SiS all users granted USAGE share one owner's-rights role and see the same data, with authorization delegated to Snowflake RBAC. Gap: if viewer populations need different data, caller's-rights, separate instances, or row-access policies are required. Follow-up: confirm intended audience.

## Business Logic Architectural Requirements

**Section directive.**
Status: Applicable
Comment: Items assessed individually.

**High-value flows (auth, session mgmt, access control) thread-safe and resistant to TOCTOU races.**
Status: Not Applicable
Comment: The app implements no auth, session-management, or access-control logic of its own (all delegated to Snowflake/IdP), and Streamlit runs a session's script sequentially per rerun, so there are no concurrent high-value flows.

**Maintain definitions/documentation of components and their business/security functions.**
Status: Applicable
Comment: ARCHITECTURE.md thoroughly documents each module's role (engines, builders, scorecard, UI steps, session/navigation). Control in place.

**Critical business-logic flows do not share unsynchronized state.**
Status: Not Applicable
Comment: No security-critical flows exist. Module-level shared state (the process-wide _SHARED Snowflake client, the mock RNG) is non-security, single-user, accessed sequentially, and reset on restart/domain switch.

## Configuration Architectural Requirements

**Section directive.**
Status: Applicable
Comment: Items assessed individually.

**Sandbox/containerize/isolate components at network level; sign binaries to untrusted devices, use trusted connections/verified endpoints.**
Status: Applicable
Comment: Locally the app is not containerized (runs via streamlit run, relying on the host); under SiS it runs in Snowflake's managed sandboxed compute with platform-enforced network isolation, so production largely satisfies this. Follow-up: document the SiS isolation model in ARCHITECTURE.md.

**Segregate components by trust level (firewall/API gateways); run components under unique low-privilege OS accounts.**
Status: Applicable
Comment: Single component running under the invoking user's own OS account, not a dedicated service account; the only trust boundary (Snowflake) is crossed over TLS+SSO. Gap: no separate service account or network segmentation. Follow-up if centrally hosted.

**Build pipeline with automated secure-deployment verification, warns of outdated/insecure components, avoids deprecated client-side tech.**
Status: Applicable
Comment: CI now runs report-only SCA (pip-audit) and secret scanning; deps were refreshed to clear advisories (pip-audit on requirements.lock reported none at refresh). Production deps are in environment.yml where streamlit is capped at 1.52.2 by the Anaconda channel; that flags two accepted-risk streamlit advisories: GHSA-7p48-42j8-8846 (Windows-only SSRF, N/A on SiS Linux) and PYSEC-2026-212 (local-access cache weak-hash, negligible). The authoritative scan is JFrog Xray against the Anaconda set. Residual gaps: onboard environment.yml to Xray and add deploy verification + dependency-update alerting.

## Secure File Upload Architectural Requirements

**Section directive.**
Status: Applicable
Comment: The app has no file-upload feature, so the upload-specific items below are Not Applicable; it only produces user-initiated downloads.

**Serve user-uploaded files as octet-stream or from an unrelated domain.**
Status: Not Applicable
Comment: No uploads. Downloads are generated in-memory and delivered via Streamlit download_button as typed attachments, not served from a web root, so the direct-access risk does not arise.

**Store user-uploaded files outside the web root.**
Status: Not Applicable
Comment: No uploads and no server-side file persistence; exports exist only as in-memory bytes handed to the browser.

**Implement a Content Security Policy (CSP) to reduce XSS from uploaded files.**
Status: Not Applicable
Comment: No uploaded files. The app sets no CSP (a general Streamlit limitation), but with no upload vector and html.escape on rendered data this upload-specific control does not apply; XSS hygiene is tracked under the I/O item.

## Malicious Software Architectural Requirements

**Section directive.**
Status: Applicable
Comment: Item assessed below.

**Source-code control in use; check-ins tied to issues/tickets; access control; identifiable users; change traceability.**
Status: Applicable
Comment: The project is in Git/GitHub with identifiable authorship and access control, but shows no issue/ticket linkage, PR review, or branch protection. Since SiS deploys directly from the repo, an unreviewed or malicious commit flows straight to production. Follow-up (high priority): enforce branch protection, mandatory PR review, and ticket references.

## Communications Architectural Requirements

**Section directive.**
Status: Applicable
Comment: Items assessed individually.

**Verify authenticity of each party; validate TLS certificates and chains.**
Status: Applicable
Comment: The Snowflake connector validates TLS server certificates (and OCSP) by default and the app does not disable it (no insecure_mode/verify=False/OCSP-disabling flags). Follow-up: keep a guard that these are never set to insecure values.

**Encrypt communications between components (containers/systems/sites/cloud).**
Status: Applicable
Comment: Locally the app-to-Snowflake link is TLS-encrypted and browser-to-app is loopback; under SiS the data-access link is in-platform and the user-to-app channel is Snowsight over Snowflake-managed TLS. Encryption in transit holds in both runtimes.

**Maintain these practices consistently across all components.**
Status: Applicable
Comment: There is a single external communication path (Snowflake), consistently TLS-protected, with no plaintext inter-component links. Consistency is trivially satisfied given the monolithic, single-link architecture.

## Errors, Logging and Auditing Architectural Requirements

**Section directive.**
Status: Applicable
Comment: Items assessed individually.

**Verify logging practices are adhered to and logs are securely managed (integrity/confidentiality).**
Status: Applicable
Comment: The app uses stdlib logging (logger.warning with exc_info) per the no-silent-except rule, recording failure reasons not row-level data; logs go to local console/stderr with no secure storage/retention. Gap: no managed log storage. Follow-up: confirm traces cannot surface bound filter values.

**Securely transmit logs to a remote system for analysis/alerting/escalation.**
Status: Applicable
Comment: No remote log shipping locally. Under SiS, event tables and Snowflake Access/Query History provide centralized logging, but the app does not yet configure event-table logging. Follow-up: enable event-table logging for the SiS app.

**Use a standardized logging format/approach consistently across the system.**
Status: Applicable
Comment: Logging is applied consistently via logging.getLogger(__name__) across modules with the ARCHITECTURE-mandated exception pattern, though no custom structured (JSON) format is defined. Consistent approach in place.
