# === access_control ===

## General Access Control Security Requirements

**Deny by default; use a whitelist (explicit grant) approach.**
Status: Applicable
Comment: Satisfied at the data tier: Snowflake RBAC grants only explicitly allowed objects (deny-by-default), and control flow fails safe. The app itself defines no permissions.

**Enforce the principle of least privilege.**
Status: Applicable
Comment: Read-only by design (only SELECT issued). Follow-up (high priority): run the SiS app under a dedicated least-privilege, read-only role scoped to required schemas, so writes are denied by Snowflake regardless of code path.

**Clearly document access-control rules.**
Status: Applicable
Comment: Gap: the access model (who is granted USAGE, which role the app runs as, schema scope) is not documented in the repo. Follow-up: document the SiS grant/role model.

**Enforce access control on all requests (including server-side redirects); manage in a secure server environment.**
Status: Applicable
Comment: Every data request runs under the Snowflake session's role (enforced server-side); the app has no server-side redirects and runs in Snowflake's sandboxed environment.

**Integrate access control into data-layer queries; apply rate limiting.**
Status: Applicable
Comment: Data-layer access control is Snowflake RBAC. Rate limiting is not implemented in the app; it is a Snowflake/warehouse-tier concern (no app-exposed API to flood).

**Validate user roles/permissions for each request; reject those lacking legitimate business purpose.**
Status: Applicable
Comment: Per-request authorization is enforced by Snowflake (every query evaluated against the session role); the app makes no role decisions and cannot escalate.

## Other Access Control Considerations Requirements

**Administrative interfaces should use strong MFA.**
Status: Not Applicable
Comment: The app exposes no administrative interface. Snowflake account/role administration is done outside the app (Snowsight), protected by the corporate IdP's MFA.

**Disable directory browsing; prevent disclosure of sensitive file/directory metadata.**
Status: Applicable
Comment: Satisfied: the app serves no static files or directories (downloads are generated in memory), so there is no directory-browsing or file-metadata-disclosure surface.

**Use step-up/adaptive authentication for lower-value systems; segregation of duties for high-value applications.**
Status: Applicable
Comment: The app performs no state-changing or fraud-sensitive transactions (read-only), so in-app step-up auth and segregation of duties are not warranted. Follow-up only if a state-changing feature is later added.

**(Narrative) These measures help ensure robust security and integrity of sensitive systems.**
Status: Not Applicable
Comment: Narrative summary statement, not an actionable control; the substantive controls are addressed in the items above.

## General Access Control Design Requirements

**Enforce least privilege; protect against unauthorized access and privilege escalation.**
Status: Applicable
Comment: Access is limited to what the Snowflake role grants; the app is read-only and contains no role-switching/privilege-elevation path. Follow-up: dedicated least-privilege role.

**Design access controls to fail securely; exceptions must not compromise security.**
Status: Applicable
Comment: Fails safe: gates reroute incomplete sessions, missing rule dependencies raise CustomRuleNotEvaluated (no silent bypass), and unauthorized data access is denied by Snowflake. Exceptions degrade to error states, not elevated access.

**Protect user/data attributes from manipulation; enforce rules on a trusted service layer.**
Status: Applicable
Comment: User identity is the Snowflake session (not an app-held, manipulable attribute), and authorization is enforced server-side at Snowflake. The app exposes no attribute the client could tamper with to elevate access.

**New users/roles start with minimal permissions (deny by default); new features granted explicitly.**
Status: Applicable
Comment: Under SiS, a new user has no access until explicitly granted USAGE on the Streamlit object (and the role's grants) — deny-by-default. Follow-up: keep grant issuance deliberate and documented.

## Operation Level Access Control Requirements

**Strong access controls and security measures to maintain data integrity and confidentiality.**
Status: Applicable
Comment: Integrity: the app is read-only, so it cannot alter source data. Confidentiality: data access is scoped by the Snowflake role and encrypted at rest/in transit by the platform.

**Implement robust anti-CSRF mechanisms for authenticated and unauthenticated functionality, including against automated attacks.**
Status: Applicable
Comment: CSRF is mitigated by Streamlit's default XSRF protection, the authenticated Snowsight context, and the read-only nature (no state-changing endpoints to forge). Follow-up: verify XSRF protection stays enabled.

**Safeguard sensitive data/APIs against direct object attacks (unauthorized create/read/update/delete).**
Status: Applicable
Comment: No IDOR/CRUD surface: read-only with no per-object id API; the project filter is a data filter, not an object key. Caveat: under multi-user SiS all viewers share the owner's-rights role, so per-user object restriction would need row-access policies.

**Prevent altering someone else's data or accessing all records without permission.**
Status: Applicable
Comment: Altering data is impossible (read-only); "accessing all records" is bounded by the Snowflake role's grants. To limit different viewers to different records, enforce it with Snowflake row-access policies rather than in the app.

# === architecture_design_and_threat_modeling ===

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

# === authentication ===

## SAML Security Requirements

**Validate the timestamp and verify the service-provider signature.**
Status: Not Applicable
Comment: No SAML handling in the app; assertion validation is done by the Snowflake connector/IdP.

**Validate the assertion signature against metadata key, not the embedded key.**
Status: Not Applicable
Comment: No SAML handling in the app.

**Check that the assertion and its parent tag are signed.**
Status: Not Applicable
Comment: No SAML handling in the app.

## General Authentication Security Requirements

**Implement object-level authorization checks in every function accessing data by user input (BOLA / API1:2019).**
Status: Applicable
Comment: No in-app object-level authorization; access is governed by Snowflake RBAC. Under multi-user SiS all viewers share one owner's-rights role. Per-user restriction must use Snowflake row-access policies/caller's-rights.

**Inform users of sensitive account activities (device lists, IP/location, block devices).**
Status: Not Applicable
Comment: The app has no account-management surface; account-activity visibility is an IdP/Snowflake capability.

**Default service credentials must not be used in production/non-production.**
Status: Applicable
Comment: Satisfied: the app uses no service or default credentials. Follow-up: ensure the SiS app runs under a dedicated least-privilege role, not a default/shared admin role.

**Authentication mechanisms correctly implemented to prevent token compromise / identity assumption (API2:2019).**
Status: Applicable
Comment: Delegated to Snowflake SSO / corporate IdP; the app issues, stores, and validates no tokens itself, so there is no app-side token-handling flaw.

**Each component authenticates every connection; standalone services (SQL Server, Redis) require authentication.**
Status: Applicable
Comment: Single-process monolith whose only backend connection (Snowflake) requires authentication. No unauthenticated standalone services (no Redis/cache/secondary DB).

**Source code must not include production credentials.**
Status: Applicable
Comment: Satisfied and high-priority since the GitHub repo is the SiS deploy source: no credentials in tracked source; `.env` is gitignored. Secret scanning (gitleaks) runs in CI. Follow-up: consider a pre-commit gitleaks hook.

## Single or Multi Factor One Time Verifier Requirements

**Log/reject reused TOTPs; single-use; defined lifetime.**
Status: Not Applicable
Comment: No OTP in the app; one-time-verifier handling is an IdP/Snowflake-MFA responsibility.

**Revoke physical OTP generators across sessions.**
Status: Not Applicable
Comment: No OTP in the app.

**Approved crypto for OTP generation/seeding/verification; protect keys in HSM.**
Status: Not Applicable
Comment: No OTP in the app.

## Credential Storage Requirements

**Salt + one-way hash passwords with unique salts.**
Status: Not Applicable
Comment: No password storage; authentication is SSO with nothing to salt/hash.

**KDF with secret salt stored separately.**
Status: Not Applicable
Comment: No password storage.

**Unique sufficient-length salt; store salt and hash securely.**
Status: Not Applicable
Comment: No password storage.

## Authentication and Session Management Requirements

**Use random session identifiers (stateful) or securely signed tokens (stateless).**
Status: Not Applicable
Comment: The app issues no authentication session identifiers or tokens; the authenticated session is Snowflake's. Streamlit `session_state` is application state, not an auth credential.

**Terminate existing sessions at the remote endpoint on logout.**
Status: Applicable
Comment: Delegated: logging out of Snowflake/Snowsight terminates authentication at the platform. The app also drops its cached connection/state via `close_shared_client()` / `restart_app` on restart/domain switch.

**Web applications must use AAD or an ExxonMobil-approved IdP to authorize OAuth2 access tokens.**
Status: Applicable
Comment: Authentication flows through Snowflake SSO to the corporate IdP (assumed EM-approved); the app handles no OAuth tokens. Follow-up: confirm the configured IdP is on the EM-approved list.

## Look-up Secret Verifier Requirements

**Lookup secrets resistant to offline attacks (unpredictable).**
Status: Not Applicable
Comment: No look-up/recovery secrets used.

**High randomness or salted+hashed lookup secrets.**
Status: Not Applicable
Comment: No look-up/recovery secrets used.

**Single-use lookup secrets.**
Status: Not Applicable
Comment: No look-up/recovery secrets used.

## General Authenticator Requirements

**Notify users if authentication factors are changed/replaced.**
Status: Not Applicable
Comment: Factor management is an IdP/Snowflake responsibility; the app has no authenticator management.

**Anti-automation controls (rate limiting, CAPTCHA) against brute force; notify on changes.**
Status: Not Applicable
Comment: The app has no login to brute-force; anti-automation for authentication is enforced at the IdP/Snowflake tier.

**Weak authenticators (SMS) only as secondary verification.**
Status: Not Applicable
Comment: The app implements no authenticators; the choice/strength of factors is the IdP's.

**Implement robust MFA (cryptographic devices, OTP, hardware key press).**
Status: Applicable
Comment: MFA is available via the corporate IdP through Snowflake SSO (delegated, not app-implemented). Follow-up: confirm MFA is enforced for the user population accessing the SiS app.

## Single Sign On (SSO) Security Requirements

**Component Security — all SSO components secured against vulnerabilities.**
Status: Applicable
Comment: SSO components are Snowflake + the corporate IdP (platform-secured); the app is a relying party with no SSO component of its own. Assumes those platforms are hardened/patched by their owners.

**Session Timeouts — auto-logout after inactivity.**
Status: Applicable
Comment: Session/idle timeout is enforced by Snowflake/IdP session policy, not the app. Follow-up: confirm a Snowflake session/idle-timeout policy applies to the SiS app.

**Identity Directory Accuracy.**
Status: Applicable
Comment: The identity directory is the corporate IdP (EM-managed); accuracy/lifecycle is an organizational responsibility, not the app's.

**Device Restrictions for SSO.**
Status: Applicable
Comment: Platform-delegated; device/conditional-access is an IdP policy that cannot be enforced in app code. Follow-up: confirm the corporate IdP enforces any required device/conditional-access policy for the SiS user population.

**Modern Authentication Protocols (e.g. SAML).**
Status: Applicable
Comment: SSO uses modern protocols (SAML/OAuth) between Snowflake and the IdP; the app relies on them rather than implementing legacy auth.

## Cryptographic Software and Devices Verifier Requirements

**Approved algorithms for generation/seeding/verification.**
Status: Not Applicable
Comment: No app crypto verifier; the app manages no keys or crypto.

**Verification keys stored in TPM/HSM/OS secure store.**
Status: Not Applicable
Comment: The app manages no keys.

**Statistically unique challenge nonce to prevent replay.**
Status: Not Applicable
Comment: No app challenge-response.

## JSON Web-Token Security Requirements

**Outer JSON element must be an object, not an array.**
Status: Not Applicable
Comment: No JWT/REST API responses. The `ml_lab_history.json` download is a JSON array, but it is a user-initiated file export, not an API/auth response.

**Reject JWT auth attempts with 403.**
Status: Not Applicable
Comment: No JWT authentication.

**Escape HTML entities / control chars in JSON REST responses.**
Status: Not Applicable
Comment: No REST API; exports use `json.dumps`, which escapes correctly.

**Validate JWT aud/nbf/exp/bearer per request.**
Status: Not Applicable
Comment: No JWT.

## Out of Band Verifier Requirements

**Don't offer cleartext OOB (SMS/PSTN) by default; prefer push.**
Status: Not Applicable
Comment: No app out-of-band auth; any OOB factor is the IdP's.

**Secure-random initial code over an independent secure channel.**
Status: Not Applicable
Comment: No app out-of-band auth.

## Credential Recovery Requirements

**System-generated recovery secrets not sent in clear text.**
Status: Not Applicable
Comment: No credential/password recovery flow in the app; recovery is handled by the corporate IdP/Snowflake.

**Avoid password hints / knowledge-based auth.**
Status: Not Applicable
Comment: No recovery flow in the app.

**Secure recovery (TOTP/push/offline) without revealing current password.**
Status: Not Applicable
Comment: No recovery flow in the app.

**Re-proof identity at original level if MFA factors lost.**
Status: Not Applicable
Comment: IdP/organizational process.

## Mobile apps authentication Requirements

**Biometric auth unlocks a keystore, not a boolean API.**
Status: Not Applicable
Comment: No mobile app.

**Remote endpoint prevents excessive credential submissions.**
Status: Not Applicable
Comment: No mobile app; brute-force protection is IdP/Snowflake.

**Enforce 2FA at the remote endpoint.**
Status: Not Applicable
Comment: No mobile app; MFA is delegated to the IdP.

## Password Security Requirements

**Allow temporary view of masked password / last character.**
Status: Not Applicable
Comment: No password fields; authentication is SSO.

**Allow users to change passwords.**
Status: Not Applicable
Comment: IdP-managed.

**High bcrypt/PBKDF2 work factor.**
Status: Not Applicable
Comment: No password hashing in the app.

**Use PAGE guidance / password generator.**
Status: Not Applicable
Comment: No passwords in the app.

## Service Authentication Requirements

**Passwords/API keys/integration secrets not in source/repos; use software key stores / TPM / HSM.**
Status: Applicable
Comment: Satisfied today (no secrets in tracked source; `.env` gitignored). The one production secret, the GitHub PAT for the SiS Git integration, must be stored as a Snowflake SECRET object, never in the repo. Secret scanning (gitleaks) is in CI.

**Store passwords/sensitive information with protection against offline recovery attacks.**
Status: Applicable
Comment: The app stores no credentials to recover offline. The only sensitive value (Git-integration secret) is held in Snowflake's secret store, not in the repo. Same secret-scanning follow-up.

## Authenticator Lifecycle Requirements

**Support enrollment/use of subscriber devices (U2F/FIDO).**
Status: Not Applicable
Comment: Authenticator enrollment is an IdP capability; the app implements none.

**System-generated initial passwords/activation codes are random, ≥6 chars, expiring.**
Status: Not Applicable
Comment: The app generates no passwords/activation codes.

**Renewal instructions for time-bound authenticators sent with advance notice.**
Status: Not Applicable
Comment: The app issues no authenticators; renewal/notification is IdP/organizational.

# === business_logic ===

## Business Logic Security Requirements

**Sufficient anti-automation controls to detect/mitigate data exfiltration, excessive requests, and DoS.**
Status: Applicable
Comment: Gap: no app-level anti-automation/rate limiting. Mitigated by SSO-gated read-only access with Snowflake warehouse limits. Residual risk: an authorized user can export all columns (CSV), bounded by their grants. Follow-up: Snowflake resource monitors; column-minimized exports.

**Enforce per-user limits on specific business actions/transactions to prevent abuse.**
Status: Applicable
Comment: No state-changing transactions to meter — actions are read-only and idempotent. Any throttling would be at the Snowflake warehouse tier. Follow-up: minimal; revisit if a state-changing feature is added.

**Monitor for unusual events/activities (out-of-order actions, atypical behavior).**
Status: Applicable
Comment: Out-of-order actions are structurally prevented by the gates and step-visibility predicates, but the app does no anomaly detection. Follow-up: define "unusual" and rely on Snowflake Query/Access History.

**Configurable alerting for detecting automated attacks or unusual activity.**
Status: Applicable
Comment: Gap: no app-level alerting. Alerting would be built on Snowflake event tables/Access History. Follow-up: configure Snowflake-side alerting if required by policy.

**Avoid TOCTOU issues and other race conditions for sensitive operations.**
Status: Not Applicable
Comment: No sensitive/state-changing operations exist, and Streamlit executes a session's script sequentially per rerun, so no concurrent flow is subject to TOCTOU. Shared module-level state is non-security and single-session.

**Ensure all steps are processed within realistic human timeframes (prevent too-fast submission).**
Status: Not Applicable
Comment: The workflow has no transactional submission to rate-check for bot-speed; it is a read-only, idempotent analysis flow. Human-timeframe checks are anti-fraud controls for transactional systems and do not apply.

**Process business-logic flows in sequential order per user, without skipping steps.**
Status: Applicable
Comment: Satisfied: step ordering is enforced via the mode/domain gates and STEP_VISIBILITY_PREDICATES, so a session cannot render a later step without its prerequisites. This is functional-integrity sequencing rather than a security boundary, but it prevents out-of-order state.

**Implement business-logic limits/validations based on threat modeling.**
Status: Applicable
Comment: This assessment is the threat-modeling exercise driving such limits. In-app validations exist (dqr_validation.py rule/param compatibility, required-CDE derivation, weight normalization, CustomRuleNotEvaluated). Follow-ups: least-privilege role, SCA/SAST/DAST, export minimization.

# === code_quality ===

## Mobile app code Quality Requirements

**Identify all third-party components and regularly check them for known vulnerabilities.**
Status: Applicable
Comment: Dependency inventory exists for both runtimes and CI runs report-only SCA (pip-audit), which reported no known vulnerabilities as of the refresh (point-in-time). Authoritative production scan must run via Nexus/JFrog Xray against environment.yml.

**Catch and handle possible exceptions gracefully to maintain stability and security.**
Status: Applicable
Comment: Broad try/except with an enforced "no silent except" rule and graceful degradation (failed builds excluded, missing rule deps raise CustomRuleNotEvaluated). Residual gap: raw-exception interpolation and default Streamlit tracebacks.

**Implement error-handling logic that denies access by default.**
Status: Applicable
Comment: The app fails safe in control flow: incomplete sessions reroute, unknown steps render a generic error, and missing inputs surface rather than fabricate results. Access deny-by-default is enforced at the Snowflake RBAC layer.

**In unmanaged code, ensure memory is allocated, freed, and used securely.**
Status: Not Applicable
Comment: The application is pure, memory-managed Python with no unmanaged code or manual memory management. C-extension dependencies are prebuilt third-party packages whose integrity is an SCA concern.

**Eliminate debugging/developer-assistance code (test code, backdoors, hidden settings); no verbose error/debug logging.**
Status: Applicable
Comment: No backdoors or hidden settings (no eval/exec, source reviewable in Git). Gaps: Streamlit traceback display not disabled, one path interpolates the raw exception, and dev artifacts remain in deployed source. Follow-up: disable error-detail, use generic text, scope/remove dev artifacts.

**Utilize free toolchain security features (bytecode minification, stack protection, PIE, automatic reference counting).**
Status: Not Applicable
Comment: These are native-compilation/mobile-toolchain features. The app is interpreted Python with no compilation or link step, so there are no such build flags to enable.

**Build the app in release mode with production settings, ensuring it is non-debuggable.**
Status: Applicable
Comment: No compiled "release mode" exists, but the equivalent production-hardening is not configured (no Streamlit config disabling dev features or error-detail display). Follow-up: add production Streamlit config with error details and dev/usage-stats off.

## Low code Custom Coding requirements

**When using custom coding and/or connectors, the use of SAST and DAST tools is a must if applicable.**
Status: Applicable
Comment: This fully custom-coded Python app now has report-only SAST (bandit) in CI with no High/Medium issues, plus in-app mitigations (parameterized SQL, html.escape, CSV sanitization). Residual gaps: wire enterprise SAST (Erebor) and run DAST (Heimdall) against the deployed SiS endpoint.

# === communications ===

## Server Communications Security Requirements

**All encrypted connections to external systems must be authenticated.**
Status: Applicable
Comment: The one external connection (Snowflake) is TLS-encrypted and authenticated; no unauthenticated external connections exist.

**Enforce TLS for all inbound/outbound connections; never revert to insecure/unencrypted protocols.**
Status: Applicable
Comment: Outbound to Snowflake is TLS with no plaintext fallback (no `insecure_mode`); no other outbound integrations exist. Inbound is platform-enforced HTTPS.

**Log backend TLS connection failures for monitoring/troubleshooting.**
Status: Applicable
Comment: Partial: connection failures surface as logged exceptions, but there is no dedicated TLS-failure logging or central log store. Follow-up: rely on Snowflake connection/query history and keep log level at WARNING+.

**Use trusted TLS certificates; if self-signed, trust only specific internal CAs and reject others.**
Status: Applicable
Comment: The connector validates the Snowflake endpoint certificate against trusted public CAs; the app configures no self-signed/internal-CA overrides and does not relax validation.

**Enable proper certificate revocation (e.g. OCSP stapling).**
Status: Applicable
Comment: The Snowflake connector performs OCSP revocation checking by default and the app does not disable it. Verify the setting remains enabled.

## General Communication Strategy Requirements

**Tokenize sensitive data (e.g. JSON) where direct access is unnecessary.**
Status: Not Applicable
Comment: The app's function requires direct access to actual data values, and data stays within the TLS/Snowflake boundary with no third party to receive tokenized data.

**Secure non-public traffic across networks; use mechanisms (e.g. nonces) against replay and brute force.**
Status: Applicable
Comment: Non-public app↔Snowflake traffic is TLS-secured. Replay/brute-force defenses are provided by Snowflake/IdP, as the app has no authentication endpoint and issues no nonces.

**Maintain documentation/inventory of endpoints, hosts, and deployed versions; manage deprecated versions; prevent debug endpoints.**
Status: Applicable
Comment: Endpoint inventory is minimal (one Snowflake endpoint), the deployment is documented, and a production dependency inventory exists. Residual gap: debug output is not disabled. Follow-up: replace raw-exception messages with generic in-app error handling.

## Client Communications Security Requirements

**All client connectivity uses secured TLS with no insecure fallback; regularly verify strong algorithms/ciphers/protocols with TLS testing tools.**
Status: Applicable
Comment: Client↔app is HTTPS with no insecure fallback and app↔Snowflake is connector TLS; cipher/protocol strength is platform-owned. Follow-up: TLS testing must target the deployed Snowflake endpoint.

**Disable outdated SSL/TLS (SSLv2/3, TLS 1.0/1.1); prefer the latest TLS.**
Status: Applicable
Comment: TLS version policy is owned by the Snowflake connector/serving layer (modern TLS; legacy versions disabled); the app neither enables nor downgrades old versions. Verify at the deployed endpoint.

## Communications Security Requirements

**Use public-CA-signed TLS certificates that are not expired.**
Status: Applicable
Comment: Snowflake endpoints present public-CA-signed certificates and the connector rejects expired/invalid ones by default; the app neither supplies nor overrides certificates.

**Use OCSP where the stack and CA allow.**
Status: Applicable
Comment: The Snowflake connector performs OCSP revocation checks by default.

**Use an approved TLS configuration; disable insecure ciphers/hashes (DES, 3DES, RC4, IDEA, MD5); manage key length/cipher suites.**
Status: Applicable
Comment: Cipher-suite/key-length selection is owned by the connector/serving layer, which uses modern suites excluding weak algorithms; the app does not weaken cipher selection. Follow-up: confirm via SSG/Heimdall that the endpoint offers no weak ciphers.

**Configure APIs to use HSTS (all content over HTTPS).**
Status: Applicable
Comment: HSTS is a serving-layer response header the app cannot set. Platform-delegated; verify presence at the deployed endpoint.

**Never revert to unencrypted HTTP if HTTPS cannot be established.**
Status: Applicable
Comment: The app never falls back to plaintext: the Snowflake connection has no insecure-mode fallback and the serving layer is HTTPS only.

# === configuration ===

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

# === containers ===

## Storage requirements

**Use a suitable, tested storage driver guaranteeing replication/availability.**
Status: Not Applicable
Comment: No containers or storage drivers; Snowflake provides replicated, highly available storage for source data.

**Persistent data never stored inside a container; use volumes/mount points.**
Status: Not Applicable
Comment: No containers, and the app persists nothing (in-memory session_state only); source data lives in Snowflake.

**Production-ready storage backend in use.**
Status: Not Applicable
Comment: No app-managed storage backend; Snowflake provides production-grade storage for source data.

**Image storage backend redundant and in a secured network zone.**
Status: Not Applicable
Comment: No container images and no image registry exist.

**Backup strategy for persistent data + tested restore.**
Status: Not Applicable
Comment: No container-persisted data; Snowflake Time Travel / Fail-safe covers source-data backup and restore.

## Disaster requirements

**Infrastructure restoration automated, documented, regularly tested.**
Status: Not Applicable
Comment: No self-managed infrastructure; SiS infrastructure is Snowflake-managed and the app is redeployed from Git.

**Regular backups of UCP, DTR, and Swarm (≥ weekly).**
Status: Not Applicable
Comment: No Docker UCP/DTR/Swarm in use.

**On-failure restart policy enabled per container.**
Status: Not Applicable
Comment: No containers; the SiS process lifecycle is platform-managed.

**Automated/documented/tested upgrades & downgrades of infrastructure + Docker Engine.**
Status: Not Applicable
Comment: No Docker Engine or self-managed infrastructure; the runtime is patched and managed by Snowflake.

**Automated/documented/tested recovery of individual apps/services.**
Status: Not Applicable
Comment: No container services; app recovery is a redeploy from the Git integration.

## Logging Monitoring requirements

**Use Docker health-checking for all containers; actively monitor status.**
Status: Not Applicable
Comment: No Docker or containers; SiS app health is platform-monitored.

**Regularly monitor the storage backend.**
Status: Not Applicable
Comment: No app-managed storage backend; Snowflake monitors its own storage.

**Monitor resource usage at node and container levels.**
Status: Not Applicable
Comment: No nodes or containers; warehouse resource usage is observable via Snowflake.

**Set container-platform log level to info in production.**
Status: Not Applicable
Comment: No container platform; app-level logging uses Snowflake event tables in production.

**All logs transferred to and stored in a central location.**
Status: Not Applicable
Comment: No container logs; Snowflake event tables / Access History / Query History provide centralized logging.

## General Containers security requirements

**Only required software packages installed in images (minimal attack surface).**
Status: Not Applicable
Comment: No images built; dependency minimization is handled via the SiS Anaconda environment.yml.

**Use COPY instead of ADD in Dockerfiles.**
Status: Not Applicable
Comment: No Dockerfile exists.

**Exposed services restricted to trusted systems or require authentication.**
Status: Not Applicable
Comment: No container-exposed services; in SiS the app is reachable only via authenticated Snowflake sessions and USAGE grants.

**Base images pinned by hash, not just name/tag.**
Status: Not Applicable
Comment: No base images or Dockerfile.

## Secrets and Keys requirements

**Sensitive info (API keys, passwords) never in configuration files.**
Status: Not Applicable
Comment: Container framing N/A; the repo has no secrets in tracked files and dotenv is removed from the SiS runtime path.

**Secrets managed via a secret-management solution, not env vars.**
Status: Not Applicable
Comment: No container secret store; SiS uses the active Snowflake session and any Git credential is a Snowflake SECRET object.

**RBAC model in place for access control.**
Status: Not Applicable
Comment: No container-orchestration RBAC; real access control is Snowflake roles plus USAGE grants on the Streamlit object.

## Orchestration Management requirements

**Only containers with the same exposure level deployed on the same node.**
Status: Not Applicable
Comment: No nodes, containers, or orchestrator.

**Delete containers no longer needed.**
Status: Not Applicable
Comment: No containers to reap; stale SiS app objects are managed in Snowflake.

**Predefined labels used to identify/manage resources.**
Status: Not Applicable
Comment: No container resources or labels; Snowflake object naming is a platform concern.

## Infrastructure Verification Requirements

**Document the entire infrastructure (nodes, networks, containers), ideally automated.**
Status: Not Applicable
Comment: No self-managed infrastructure; the SiS architecture and data flows are documented in ARCHITECTURE.md.

**Clearly define architecture/design including networking inside/outside the container solution.**
Status: Not Applicable
Comment: No container solution or container networking; networking is entirely Snowflake-internal in SiS.

**Standalone AKS/EKS needs architectural endorsement; OpenShift preferred.**
Status: Not Applicable
Comment: The app uses neither AKS, EKS, nor OpenShift; it runs on Streamlit in Snowflake.

## Container Image requirements

**No images from public repos (e.g. Docker Hub); use vetted internal repos.**
Status: Not Applicable
Comment: No container images are built or pulled; SiS packages come from Snowflake's curated Anaconda channel.

**Enable and regularly run garbage collection on image registries.**
Status: Not Applicable
Comment: No image registry.

**Regular automated security scans of images; pull into on-prem/managed cloud; use cloud registry scanning.**
Status: Not Applicable
Comment: No images to scan; dependency/SCA scanning of the SiS environment is a tracked follow-up.

**Images imported to ExxonMobil environment must be security-scanned via goto/ssgrequest 'Container Image Import'.**
Status: Not Applicable
Comment: No container images are imported.

**Containers always built from the most recent image, not local caches.**
Status: Not Applicable
Comment: No container build or cache; SiS pulls current code from the Git integration on deploy.

**Use specific image tags; only production/master may use `latest`.**
Status: Not Applicable
Comment: No images or tags; versioning is via Git refs on the deploy branch.

## Network requirements

**Activate load balancing (DNS Round Robin / VIP).**
Status: Not Applicable
Comment: No self-managed network or load balancer; traffic distribution and scaling are Snowflake-managed.

**Encrypt communication between containers/nodes on the overlay network.**
Status: Not Applicable
Comment: No overlay network or containers; in-platform and user-to-app traffic is Snowflake-managed TLS.

**Run only necessary services; open only required ports.**
Status: Not Applicable
Comment: The app opens no ports and exposes no services; SiS controls all network exposure.

**Prevent inter-container network communication by default.**
Status: Not Applicable
Comment: No containers or container network.

**Ensure subnets don't overlap (e.g. overlay networks).**
Status: Not Applicable
Comment: No app-managed subnets or overlay networks.

**Each app/service assigned a separate isolated overlay network (L3 segmentation).**
Status: Not Applicable
Comment: No overlay networks; isolation is provided by the Snowflake SiS sandbox.

**Published ports bound to specific node interfaces and minimized.**
Status: Not Applicable
Comment: No published ports or nodes.

**Implement SPF, DKIM, DMARC for end-user email communications.**
Status: Not Applicable
Comment: The app sends no email and has no email-communication channel.

**Activate only required network interfaces (wired/wireless/Bluetooth).**
Status: Not Applicable
Comment: No app-managed host or network interfaces; the runtime host is Snowflake-managed.

# === cryptography ===

## Secret Management requirements

**Avoid storing enterprise user passwords in nonvolatile storage.**
Status: Applicable
Comment: Satisfied: the app stores no passwords anywhere (SSO; no password fields, no password store, no nonvolatile credential persistence).

**Protect memorized secrets using a password hash algorithm.**
Status: Not Applicable
Comment: The app has no memorized secrets/passwords to hash; password handling is the corporate IdP's.

**Must not require arbitrary password changes, store passwords in nonvolatile storage, or truncate memorized secrets.**
Status: Not Applicable
Comment: No password lifecycle in the app; password policy is the IdP's responsibility.

**Use a secrets management solution like a key vault for creating/storing/managing secrets.**
Status: Applicable
Comment: The app manages no secrets of its own. Follow-up: confirm the SiS Git-integration GitHub PAT is vaulted in a Snowflake SECRET object, never in the repo.

**Display a password-strength meter for user-chosen memorized secrets.**
Status: Not Applicable
Comment: No password entry in the app (SSO).

**Impose a maximum length limit on memorized secrets (≥64 characters).**
Status: Not Applicable
Comment: No passwords in the app.

**Require users to enter old memorized secrets for changes.**
Status: Not Applicable
Comment: No password-change flow in the app (IdP-managed).

**Ensure key material is not exposed to the application; use an isolated security module for cryptographic operations.**
Status: Applicable
Comment: Satisfied: no key material is exposed to the app. Cryptographic operations (TLS, SSO token handling) are performed by the Snowflake connector / corporate IdP, not application code.

**Do not require arbitrary changes to memorized secrets.**
Status: Not Applicable
Comment: No passwords in the app; secret-rotation policy is the IdP's.

**Do not truncate memorized secrets; evaluate the entire secret or reject if too long.**
Status: Not Applicable
Comment: No passwords in the app.

**Store a Boolean `password_compromised` value with the user's password hash.**
Status: Not Applicable
Comment: No password store/hash in the app.

**Allow all printable ASCII characters and spaces in memorized secrets.**
Status: Not Applicable
Comment: No passwords in the app.

**User-set memorized secrets ≥8 characters; random API-generated secrets ≥6 characters.**
Status: Not Applicable
Comment: The app sets no passwords and generates no API secrets. (The Git PAT's properties are governed by GitHub/Snowflake.)

**Validate newly changed user passwords against specific criteria.**
Status: Not Applicable
Comment: No password-change flow in the app.

**Composite memorized-secret policy (ASCII/spaces, ≥64 max, hashing, old-password-for-change, min length, complexity feedback).**
Status: Not Applicable
Comment: None of the composite password items apply; the app has no passwords (SSO; all password policy is the corporate IdP's).

## One Time Password security requirements

**Use an approved CSPRNG to generate the OTP seed; prevent reuse even on unsuccessful attempts.**
Status: Not Applicable
Comment: The app implements no OTP. Any MFA/OTP is provided by the corporate IdP.

**Prefer TOTP over HOTP or proprietary alternatives.**
Status: Not Applicable
Comment: No OTP in the app; algorithm choice is the IdP's.

## Mobile apps Cryptography Requirements

**Verify the app uses secure random number generation and proven cryptographic primitives configured per best practices.**
Status: Not Applicable
Comment: No mobile app and no cryptographic operations. `np.random` is used solely for ML statistics and deterministic mock data, never for security values (preempts a SAST weak-randomness false positive).

**Avoid deprecated algorithms, hardcoded keys, and reuse of cryptographic keys for multiple purposes.**
Status: Not Applicable
Comment: No mobile app and no app cryptography. Verified: no cryptographic algorithms in app code, no hardcoded keys, and no keys to reuse. TLS suite selection is owned by the Snowflake connector/platform.

# === data_protection ===

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

# === error_handling_and_logging ===

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

# === file_and_resources ===

## File Storage Requirements

**Section directive.**
Status: Applicable
Comment: Directive; items assessed individually for the current (upload-disabled) state.

**Store files from untrusted sources outside the web root, with limited permissions and strong validation.**
Status: Not Applicable
Comment: App accepts no files from untrusted sources (upload disabled) and performs no filesystem writes. Re-evaluate strong validation when the snapshot feature is re-enabled.

**Scan files from untrusted sources with antivirus scanners.**
Status: Not Applicable
Comment: No untrusted files are accepted while upload is disabled, so nothing to scan. Follow-up: re-evaluate AV/malware scanning when upload is re-enabled (it was an open gap when active).

## File Upload Requirements

**Section directive.**
Status: Applicable
Comment: Directive; upload feature is disabled, so the items below are Not Applicable pending rework.

**Prevent acceptance of large files that could fill storage / cause DoS.**
Status: Not Applicable
Comment: No upload path exposed (`st.file_uploader` removed). Re-evaluate (set explicit `server.maxUploadSize`) if/when upload is re-enabled.

**Enforce file size quotas and max number of files per user.**
Status: Not Applicable
Comment: No upload path exposed; no per-user file intake. Re-evaluate quotas when the feature is re-enabled.

**Check compressed files for "zip bombs".**
Status: Not Applicable
Comment: No upload path, and even when active only `json`/`csv` were accepted (no archives/decompression). No zip-bomb vector now or previously.

## File Download Requirements

**Section directive.**
Status: Applicable
Comment: Directive; the download capability remains active, so these items are still in scope.

**Ensure direct requests to uploaded files are never executed as HTML/JavaScript.**
Status: Applicable
Comment: No uploaded files exist to re-serve. Generated downloads are delivered via `st.download_button` with explicit MIME as attachments, never as HTML/JS responses. Control satisfied.

**Configure the web tier to serve only specific file extensions; block backups/temp/compressed files.**
Status: Not Applicable
Comment: No web tier serves static files from a directory; downloads are generated in memory and the serving tier is not app-configurable. No file directory exists for extension filtering to govern.

## SSRF Protection Requirements

**Section directive.**
Status: Applicable
Comment: Directive; item assessed below.

**Whitelist of resources/systems the server can send requests to or load data/files from.**
Status: Applicable
Comment: Satisfied by design: the only outbound target is the fixed Snowflake connection, with no HTTP-fetching libraries and no user-controllable URL/host. The implicit whitelist is that single endpoint.

## File Integrity Requirements

**Section directive.**
Status: Applicable
Comment: Directive; item assessed below.

**Validate files from untrusted sources to ensure they match the expected type based on content.**
Status: Not Applicable
Comment: No untrusted files are ingested while upload is disabled; the retained loaders are unreachable from the UI. Follow-up: when re-enabled, add content/schema validation (prior impl lacked magic-byte sniffing).

## File Execution Requirements

**Section directive.**
Status: Applicable
Comment: Directive; with upload disabled, no user-submitted filename/metadata is accepted at all.

**Prevent path traversal — don't use user-submitted filename metadata with system/framework filesystems.**
Status: Not Applicable
Comment: No user-submitted filename metadata is accepted, and the app performs no filesystem operations. No path-traversal surface.

**Validate/ignore user-submitted filename to prevent RFI/LFI.**
Status: Not Applicable
Comment: No user file/filename intake and no dynamic file inclusion from user input. No RFI/LFI surface.

**Don't use untrusted file metadata with system APIs (OS command injection).**
Status: Not Applicable
Comment: No file-metadata intake, and there is no `subprocess`/`os.system`/shell execution anywhere. No OS-command-injection surface.

**Protect against reflective file download (RFD) by validating/ignoring user filenames and setting headers.**
Status: Applicable
Comment: Download feature is active but filenames are app-generated from a catalog-constrained code, with fixed extensions, MIME/attachment disposition, and CSV cells sanitized. RFD risk low; follow up only if user-controlled text ever feeds a download filename.

**Avoid including and executing functionality from untrusted sources.**
Status: Applicable
Comment: No `eval`/`exec`/`pickle`/`yaml.load`/dynamic import, and no untrusted content is parsed or executed. Residual angle is third-party dependencies; report-only SCA + secret scanning run in CI, with enterprise scan as the follow-up.

## File and Resources Security requirements

**Section directive.**
Status: Applicable
Comment: Directive; items assessed individually for the current (upload-disabled) state.

**Serve non-public files through a web service or signed download link, not direct links.**
Status: Not Applicable
Comment: App serves no stored files and exposes no direct file links; downloads are generated in memory on demand via `st.download_button`. No stored-file-serving model exists for this control to govern.

**Generate filenames for uploaded files instead of using external filenames.**
Status: Not Applicable
Comment: No uploads are accepted, so no upload filenames are handled or stored (download filenames are app-generated regardless). Re-evaluate when upload is re-enabled.

**Store newly uploaded files in an inaccessible location until validated.**
Status: Not Applicable
Comment: No uploads are accepted; when previously active, uploads were held in memory only and parse-validated, with no accessible storage location. Re-evaluate on re-enable.

**Use third-party malware scanners to scan uploaded files.**
Status: Not Applicable
Comment: No uploads to scan while the feature is disabled. Follow-up: re-evaluate malware scanning when upload is re-enabled (it was an open gap when active).

**Validate that uploaded files match expected formats and their file extensions.**
Status: Not Applicable
Comment: No uploads are accepted. Retained loaders enforce structural checks but receive no UI input today. Follow-up: when re-enabled, restore/extend format + extension validation and consider content-type sniffing.

# === graphql_security ===

## GraphQL and other Web Service Data Layer Security Requirements

**Use query whitelisting, depth/amount limiting, and query cost analysis to prevent DoS from expensive nested queries.**
Status: Not Applicable
Comment: No client-facing GraphQL/query layer exists; only fixed-shape, parameterized Snowflake reads with bounded result volume.

**Implement authorization logic at the business-logic layer rather than the GraphQL layer.**
Status: Not Applicable
Comment: No GraphQL layer exists; authorization is enforced at the Snowflake RBAC tier, not in the application.

# === input_validation_sanitization_and_encoding ===

## General Validation Security Requirements

**Validate redirect URLs against a whitelist of known-safe locations.**
Status: Not Applicable
Comment: No URL redirect/forward functionality; navigation is internal step changes via server-side session state, not HTTP redirects to user-supplied URLs.

**Validate all request data (parameters, cookies, headers, URLs) on a whitelist on a trusted system.**
Status: Applicable
Comment: Widget inputs are validated server-side: catalog selections are whitelisted, numerics are bounded, and free-text project filters pass through `_canonicalize_id` and are used only as bound SQL values.

**Prevent SSRF by validating externally supplied URLs against a whitelist.**
Status: Applicable
Comment: The only outbound target is the fixed Snowflake connection; no HTTP-fetching libraries and no user-supplied URLs. The implicit whitelist is the single Snowflake endpoint.

## Input Validation and output encoding requirements

**Include a cryptographic signature with any language-serialized object.**
Status: Not Applicable
Comment: No language-native serialization (no `pickle`/Java) — only JSON/CSV data formats, so there is no language-serialized object to sign.

**Use parameterized queries / stored procedures / ORM / DB-specific encoding for queries with external input.**
Status: Applicable
Comment: The only external input reaching SQL (project-filter IDs) is bound, never concatenated. Table/schema f-string interpolation is annotated with justified `# nosec B608`.

**Normalize all input to a pre-defined Unicode normalization form or reject non-normalized input.**
Status: Applicable
Comment: Gap (low impact): no explicit Unicode normalization. Free-text project IDs are whitespace-stripped and numeric-coerced by `_canonicalize_id` but not normalized; follow-up if non-ASCII identifiers become possible.

**Normalize Unicode strings before sending to other systems or storing them.**
Status: Applicable
Comment: Partial: values sent to Snowflake are canonicalized via `_canonicalize_id` (strip + integer coercion) but not Unicode-normalized. Same low-impact gap; bind-parameterization mitigates injection risk.

**Avoid language-specific serialization (e.g. Java's built-in serialization).**
Status: Applicable
Comment: Satisfied: no `pickle`/Java/native serialization; only `json.dumps`/`pd.to_csv` for output and `json.loads`/`pd.read_csv` for parsing.

**Specify a character set for each request and input source.**
Status: Applicable
Comment: UTF-8 is specified explicitly where the app controls encoding: exports `encode("utf-8")` and CSV is written/read as UTF-8.

**Encode or sanitize HTML output; use pre-existing libraries for HTML sanitization.**
Status: Applicable
Comment: Data-derived values inside `unsafe_allow_html` are escaped with stdlib `html.escape`; Streamlit auto-escapes standard widgets. Follow-up: audit the ~100 `unsafe_allow_html` sites to ensure every dynamic value stays escaped.

**Sanitize user input before passing it over IMAP, POP3, or SMTP protocols.**
Status: Not Applicable
Comment: No email/IMAP/POP3/SMTP functionality (no `smtplib`/`imaplib`/`poplib`).

**Reject requests with input that does not meet validation rules.**
Status: Applicable
Comment: Incompatible Standard DQR assignments are filtered by `src/dqr_validation.py`; stale selectbox values fall back via guarded `.index()`; custom rules with missing dependencies raise `CustomRuleNotEvaluated`.

## Input Validation Requirements

**Protect against mass parameter assignment attacks.**
Status: Not Applicable
Comment: No auto-binding of request payloads to objects; models are built field-by-field from constrained widgets. No mass-assignment surface.

**Ensure structured data is strongly typed and validated against a schema (allowed chars, length, pattern).**
Status: Applicable
Comment: Partial: domain models are typed dataclasses and `src/dqr_validation.py` validates type compatibility, but there is no declarative schema enforcing length/pattern/charset on free-text inputs. Follow-up: add length/pattern bounds if needed.

**Defend against HTTP parameter pollution attacks.**
Status: Not Applicable
Comment: The app does not parse raw HTTP query parameters (Streamlit transport); no duplicate-parameter parsing surface to pollute.

**Validate all input using positive validation (whitelisting).**
Status: Applicable
Comment: Domain/system/dimension/source selections are whitelisted against fixed catalogs; numeric inputs are range-bounded. The free-text project filter is normalized + bind-parameterized rather than strictly pattern-whitelisted.

**Allow URL redirects/forwards only to whitelisted destinations or warn.**
Status: Not Applicable
Comment: No URL redirect/forward feature exists (internal session-state navigation only).

## XML-Specific Validation and Encoding requirements

**Sanitize/encode input before inserting into XML responses, files, or databases.**
Status: Not Applicable
Comment: The app produces no XML and performs no database writes (read-only). DB-read injection is handled via parameterized queries.

**Prevent injection flaws by not sending untrusted data to interpreters without validation.**
Status: Applicable
Comment: Injection prevention covers the interpreters actually used: SQL (bind parameters), HTML (`html.escape`), and CSV (`_sanitize_csv_cell`). No XML interpreter is used.

**Disable loading DTDs when parsing XML / use a whitelist of safe DTDs.**
Status: Not Applicable
Comment: The app parses no XML (no lxml/etree/xml). No DTD/XXE surface.

**Use parameterized XPath queries or escape input in XPath.**
Status: Not Applicable
Comment: No XPath usage anywhere.

## Memory, String, and Unmanaged Code Requirements

**Dereferences a NULL pointer expected to be valid.**
Status: Not Applicable
Comment: Pure-Python app code; no pointers or manual memory. Python `None`-attribute access is guarded by code patterns and is not a memory-safety issue.

**Ensure format strings are constant and do not take hostile input.**
Status: Applicable
Comment: All `%s`/`%d` occurrences are constant logging templates (values passed as logging args) or SQL bind placeholders — never a user-controlled format template.

**Incorrectly reusing freed memory (use-after-free).**
Status: Not Applicable
Comment: Python is garbage-collected; no manual memory management in app code.

**Accesses memory outside buffer boundaries.**
Status: Not Applicable
Comment: Memory-safe Python; no direct buffer access in app code.

**Use memory-safe string operations / safe memory copy / pointer arithmetic.**
Status: Not Applicable
Comment: No unmanaged code or pointer arithmetic in app code. C-extension dependencies (numpy/pandas/pyarrow) are a dependency/SCA concern.

**Consider write/read operations that could cause memory corruption out of range.**
Status: Not Applicable
Comment: Memory-safe Python; no out-of-range memory operations in app code.

**Use sign/range/input validation to prevent integer overflows.**
Status: Not Applicable
Comment: Python integers are arbitrary-precision. Fixed-width numpy dtype overflow is a data-correctness concern, not a security boundary, and is not driven by untrusted input.

## Sanitization and Sandboxing Requirements

**Sanitize/disable/sandbox user-supplied SVG to prevent XSS.**
Status: Not Applicable
Comment: The app accepts no user-supplied SVG. Charts are app-generated by Plotly; the disabled upload accepted only JSON/CSV.

**Sanitize unstructured data (allowed characters, length).**
Status: Applicable
Comment: Partial: free-text project IDs are normalized via `_canonicalize_id`, but no explicit length/character-class cap is enforced. Low risk (bind-parameterized, not raw HTML). Follow-up: add length/charset bounds.

**Protect against SSRF by validating/sanitizing untrusted data; whitelist protocols/domains/paths/ports.**
Status: Applicable
Comment: Single fixed Snowflake egress, no user-supplied URLs, no HTTP libraries.

**Sanitize/disable/sandbox scriptable or template content (Markdown, CSS, XSL, BBCode).**
Status: Applicable
Comment: Markdown and injected CSS are all app-authored static content; user/data-derived values are `html.escape`d before insertion. No user-supplied scriptable/template content is rendered.

**Sanitize user input before passing it to mail systems (SMTP/IMAP injection).**
Status: Not Applicable
Comment: No mail functionality.

**Sanitize untrusted HTML from WYSIWYG editors.**
Status: Not Applicable
Comment: No WYSIWYG/rich-text editor; the app accepts no untrusted HTML input.

**Avoid eval()/dynamic code execution; sanitize/sandbox if unavoidable.**
Status: Applicable
Comment: Satisfied: no `eval`/`exec`/dynamic code execution anywhere; uploaded content (when active) was parsed as data only.

## Deserialization Prevention Requirements

**Use JSON.parse for parsing JSON, avoiding eval().**
Status: Applicable
Comment: JSON is parsed with `json.loads` (in the now-disabled loader) — never `eval`. There is no custom JavaScript backend.

**Avoid or protect deserialization of untrusted data (JSON/XML/YAML parsers).**
Status: Applicable
Comment: No untrusted deserialization beyond JSON/CSV parsed strictly as data (no object reconstruction); no `pickle`/`yaml.load`/XML parsing. The upload entry point is currently disabled.

**Use integrity checks or encryption for serialized objects.**
Status: Applicable
Comment: Gap (low risk): exported JSON/CSV are not signed/encrypted. The re-import path parses them as data, not reconstructable objects, so the residual concern is tamper-detection. Follow-up: add an integrity check if exports become trust-sensitive.

**Restrict XML parsers to the most restrictive configuration; disable external entities (XXE).**
Status: Not Applicable
Comment: No XML parsing in the app (no lxml/etree/xml). No XXE surface.

## Output Encoding and Injection Prevention Requirements

**Prevent Local File Inclusion (LFI) and Remote File Inclusion (RFI) attacks.**
Status: Applicable
Comment: No file inclusion from user input, no dynamic import, no filesystem operations, and (with upload disabled) no user filename intake. No LFI/RFI surface.

**Use parameterized queries / ORM / entity frameworks to protect against DB injection.**
Status: Applicable
Comment: Parameterized Snowflake reads with bound filter values. Read-only access further limits impact.

**Implement context-aware output escaping to protect against XSS.**
Status: Applicable
Comment: `html.escape` for the HTML context, Streamlit auto-escaping for standard widgets, and `_sanitize_csv_cell` for the spreadsheet context. Context-appropriate per output target.

**Ensure output encoding is relevant for the interpreter and context, preserving charset/locale.**
Status: Applicable
Comment: UTF-8 is preserved across exports/imports; HTML, CSV, and JSON outputs each use their appropriate encoding/escaping.

**Use context-specific output encoding when parameterized mechanisms are unavailable.**
Status: Applicable
Comment: Demonstrated by the CSV formula-injection sanitizer `_sanitize_csv_cell` — spreadsheets have no parameterization, so context-specific neutralization is applied at write time.

**Protect against DLL Hijacking by signing executables and verifying signatures.**
Status: Not Applicable
Comment: The app ships no executables/DLLs; it is pure Python run via Streamlit. No native binary load path to hijack.

**Protect against JavaScript, JSON, XPath, and LDAP injection attacks.**
Status: Applicable
Comment: JSON output is safely encoded via `json.dumps` (no manual string assembly); there is no custom JavaScript, XPath, or LDAP usage. The JSON-encoding control is the applicable part.

**Protect against XML injection.**
Status: Not Applicable
Comment: The app neither consumes nor produces XML. No XML-injection surface.

**Prevent OS command injection (parameterized OS queries / command-line output encoding).**
Status: Applicable
Comment: No `subprocess`/`os.system`/shell execution anywhere, and no user input is passed to a system/command API. No OS-command-injection surface.

# === iot_security ===

## Physical Security requirements

**Require authentication for debug interfaces or ports.**
Status: Not Applicable
Comment: No hardware debug ports.

**Make device circuitry tamper-resistant (epoxy/resin).**
Status: Not Applicable
Comment: No physical device.

**Ensure no backdoors or hidden entry points.**
Status: Applicable
Comment: The principle applies in code: no eval/exec/backdoor and source is reviewable in Git.

**Incorporate hardware security features (security chips/coprocessors).**
Status: Not Applicable
Comment: No hardware.

**Ensure device can recover after a power outage.**
Status: Not Applicable
Comment: No device; SiS state is platform-managed.

**Use a unique physical identifier for device distinction.**
Status: Not Applicable
Comment: No device.

**Disable unnecessary physical interfaces or ports.**
Status: Not Applicable
Comment: No physical interfaces.

**Restrict direct access to administrative capabilities.**
Status: Applicable
Comment: Maps to Snowflake RBAC / least-privilege role plus USAGE grants, with no in-app admin surface.

**Validate device root-of-trust boot process and monitor for anomalies.**
Status: Not Applicable
Comment: No device boot.

## Secure Coding Guidelines requirements

**Avoid deploying debug versions of code; exclude unnecessary files.**
Status: Applicable
Comment: Gap: no production hardening config and dev artifacts (notebook, tests, docs) are in the Git-deployed source.

**Prevent injection by separating untrusted data from commands/queries.**
Status: Applicable
Comment: In place: parameterized SQL, html.escape, and CSV formula sanitization.

**Cryptographically sign code; implement run-time protection and secure execution monitoring.**
Status: Not Applicable
Comment: No shipped binary to sign; run-time isolation is provided by the SiS sandbox.

**Sanitize input in web applications using URL or HTML encoding.**
Status: Applicable
Comment: In place: html.escape on data rendered via unsafe_allow_html plus Streamlit auto-escaping.

**Handle errors gracefully without revealing sensitive information.**
Status: Applicable
Comment: Partial; gap is raw-exception interpolation and Streamlit default tracebacks with no config disabling them.

**Do not hard-code credentials; store securely and ensure updateable.**
Status: Applicable
Comment: Satisfied: no hard-coded credentials and .env is gitignored holding only non-secret identifiers.

**Validate all data transferred over interfaces (type, length, format).**
Status: Applicable
Comment: Partial: typed dataclasses and compatibility checks exist; gap is no length/pattern bounds on free-text inputs.

**Use static code analyzers like Erebor to test for vulnerabilities.**
Status: Applicable
Comment: CI runs report-only SAST (bandit); residual is wiring the enterprise Erebor SAST via the org pipeline.

**Test web interfaces for XSS, SQLi, and CSRF using tools like Heimdall.**
Status: Applicable
Comment: Gap: no Heimdall/DAST run yet (needs a deployed endpoint); in-app XSS/SQLi/CSRF mitigations exist.

**Use patched libraries and third-party components; tools like Nexus.**
Status: Applicable
Comment: CI runs report-only SCA (pip-audit); residual is the authoritative Nexus/JFrog Xray scan against the Anaconda set.

## Network Connections requirements

**Authenticate every incoming connection.**
Status: Applicable
Comment: Under SiS every connection is an authenticated Snowflake session; locally it is localhost.

**Use SPF, DKIM, DMARC for end-user communications.**
Status: Not Applicable
Comment: The app sends no email and has no email channel.

**Use trusted TLS certificates; reject untrusted certificates.**
Status: Applicable
Comment: The Snowflake connector validates TLS by default and the app never disables it.

**Never exchange credentials in clear text; provide strong encryption (AES-256).**
Status: Applicable
Comment: The app exchanges no credentials itself and all data-in-transit is TLS.

**Fully encrypt user sessions with HTTPS and HSTS.**
Status: Applicable
Comment: Under SiS the UI is served by Snowsight over HTTPS; HSTS is a Snowflake serving-layer header to verify at endpoint.

**Disable old SSL/TLS versions; prefer the latest TLS.**
Status: Applicable
Comment: TLS version/cipher selection is owned by the Snowflake connector/serving layer; the app does not downgrade.

**Activate only necessary interfaces/services; open only required ports.**
Status: Applicable
Comment: The app opens no ports and makes a single outbound Snowflake connection; exposure is Snowflake-managed under SiS.

## Data Protection requirements

**Do not store personal/sensitive/credential data in plain text.**
Status: Applicable
Comment: The app persists nothing and stores no plaintext credentials; residual is user-initiated plaintext CSV/JSON downloads.

**Follow privacy-by-design; process personal data lawfully with consent.**
Status: Applicable
Comment: Processes corporate data under corporate policy with no consumer PII; follow-up is documenting data classification.

**Provide capability to erase all personal/sensitive/credential data on disposal.**
Status: Not Applicable
Comment: No device disposal and no app-persisted personal/credential data.

**Encrypt regulated private data at rest (PII/GDPR).**
Status: Applicable
Comment: Under SiS Snowflake encrypts at rest by default; residual gap is plaintext exports.

**Ensure only authorized personnel access users' personal data.**
Status: Applicable
Comment: Enforced by Snowflake RBAC (the app's role plus USAGE grants).

## Credential Management requirements

**Implement 2-factor authentication for accessing sensitive data.**
Status: Applicable
Comment: Delegated to Snowflake SSO/IdP, which supports MFA; the app implements no auth of its own.

**Use hardware secure storage for critical sensitive data.**
Status: Not Applicable
Comment: No device/hardware; the app stores no secrets.

**Store credentials/keys in SAM/TPM/HSM/trusted key store.**
Status: Not Applicable
Comment: The app manages no credentials/keys.

**Keep device IDs and authentication keys secure post-deployment.**
Status: Not Applicable
Comment: No device IDs/keys.

**Good password management (complex passwords, secure transmission).**
Status: Not Applicable
Comment: The app has no passwords (SSO).

**Unique certificates per device; manage/revoke.**
Status: Not Applicable
Comment: No devices/certificates.

**Factory reset fully removes all user data/credentials.**
Status: Not Applicable
Comment: No device.

**Use a secrets management solution (keyvault, secret manager).**
Status: Applicable
Comment: The one production secret, the GitHub PAT for SiS Git integration, should be a Snowflake SECRET object, not in the repo.

## Device Secure Boot requirements

**Each boot stage completes before proceeding.**
Status: Not Applicable
Comment: No boot process.

**Hardware tamper-resistant capabilities (SAM/TPM) for boot.**
Status: Not Applicable
Comment: No hardware.

**Handle boot failures gracefully.**
Status: Not Applicable
Comment: No boot.

**Verify expected hardware at each boot stage.**
Status: Not Applicable
Comment: No hardware.

**Always use ROM-based secure boot with multi-stage bootloader.**
Status: Not Applicable
Comment: No bootloader.

## Encryption requirements

**Remove weaker algorithm options to prevent downgrade attacks.**
Status: Applicable
Comment: TLS cipher/version selection is owned by the Snowflake connector/platform; the app implements no negotiable crypto.

**Avoid insecure block/padding/small-block ciphers and weak hashing.**
Status: Not Applicable
Comment: The app implements no cryptography of its own; TLS is platform-provided.

**Ensure cryptographic operations are constant-time.**
Status: Not Applicable
Comment: No app-implemented crypto.

**Store encryption keys in secure modules (SAM/TPM/HSM/key store).**
Status: Not Applicable
Comment: The app manages no keys.

**Avoid insecure protocols like FTP and Telnet.**
Status: Applicable
Comment: Satisfied: the app uses only the TLS-protected Snowflake connection with no FTP/Telnet/cleartext protocols.

**Use industry-standard cipher suites, strongest algorithms, latest TLS.**
Status: Applicable
Comment: Provided by the Snowflake connector/platform TLS stack; the app does not weaken it.

**Apply encryption appropriate to the data classification.**
Status: Applicable
Comment: Under SiS Snowflake encryption at rest/in transit applies; the open item is formal data classification.

**Ensure cryptographic components can be reconfigured/upgraded/swapped.**
Status: Not Applicable
Comment: The app has no crypto components; the TLS stack upgrades via the connector/platform dependency.

## Secure Operating System requirements

**Implement an encrypted file system.**
Status: Not Applicable
Comment: Snowflake-managed storage, encrypted by the platform.

**Include only necessary OS components.**
Status: Not Applicable
Comment: Snowflake-managed runtime.

**Assign minimum access rights to files/directories.**
Status: Not Applicable
Comment: No app-managed filesystem.

**Securely boot the OS and keep components updated.**
Status: Not Applicable
Comment: Snowflake-managed.

**Disable services; restrict write permissions to the root filesystem.**
Status: Not Applicable
Comment: Snowflake-managed; the app writes no files.

## Securing Software Updates requirements

**Verify digital signatures/certificates before updating.**
Status: Not Applicable
Comment: No update package; the integrity analog is Git branch protection / optional signed commits.

**Fail-safe mechanism for safe state during update failures.**
Status: Not Applicable
Comment: No device update; a bad SiS deploy is recoverable by redeploying a prior Git ref.

**Identify and manage all sensitive data created/processed by the application.**
Status: Applicable
Comment: Applies generally; the data-classification/inventory follow-up is tracked in Data Protection.

**Encrypt update packages to prevent reverse engineering.**
Status: Not Applicable
Comment: No update package; source is in Git.

**Cryptographically validate integrity/authenticity of update packages.**
Status: Not Applicable
Comment: No update package; the analog is Git integrity plus branch protection.

**Encrypt sensitive information using approved algorithms (confidentiality/integrity).**
Status: Applicable
Comment: TLS in transit plus Snowflake at-rest encryption under SiS; no app-implemented crypto.

**Automatically resolve/install dependencies during updates; safe state if unresolved.**
Status: Not Applicable
Comment: No device update; the analog is SiS resolving Anaconda deps from environment.yml at deploy.

**Classify and delete old/out-of-date sensitive personal information automatically.**
Status: Not Applicable
Comment: The app stores no PII; retention is Snowflake's.

**Implement anti-rollback to prevent reverting to vulnerable versions.**
Status: Not Applicable
Comment: No firmware versioning; Git history governs versions.

**Assess production software images to remove debug/symbolic information.**
Status: Applicable
Comment: Analog applies: remove dev artifacts/debug from the deployed source.

**Provide clear language on data collection/use; obtain opt-in consent.**
Status: Applicable
Comment: Organizational/assumption: corporate data, with handling to be documented.

**Identify the software update mechanism in the DSLA.**
Status: Not Applicable
Comment: No device/DSLA.

**Audit access to sensitive data without logging the data itself.**
Status: Applicable
Comment: Snowflake Access/Query History records access not data values; the app logs identifiers, not row data.

**Overwrite sensitive information in memory when no longer needed.**
Status: Not Applicable
Comment: Not reliably achievable in Python (GC); session caches are cleared on restart.

**Protect against TOCTOU between validation and installation.**
Status: Not Applicable
Comment: No install step; the SiS Git integration deploys a specific ref.

**Clearly identify update support timespan/frequency in the DSLA.**
Status: Not Applicable
Comment: No device/DSLA.

## Logging requirements

**Set max log file size, rotate logs, store in a separate partition.**
Status: Not Applicable
Comment: The app manages no log files; under SiS event-table storage is Snowflake-managed.

**Restrict access rights to log files to the minimum necessary.**
Status: Applicable
Comment: Under SiS log/audit data (event tables, Query/Login History) is RBAC-protected by Snowflake.

**Ensure logged data complies with data protection regulations.**
Status: Applicable
Comment: The app logs identifiers/rule-ids, not row data; verify exc_info/{e} paths don't surface data.

**Implement log levels (lightweight + detailed when needed).**
Status: Applicable
Comment: Stdlib logging levels are used consistently.

**Send log data over a secure channel if sensitive/tamper-protected.**
Status: Applicable
Comment: Under SiS telemetry to event tables stays within the Snowflake boundary.

**Run the logging function in a separate OS process.**
Status: Not Applicable
Comment: No such architecture; logging is in-process stdlib / platform event tables.

**Synchronize to an accurate time source for correlating timestamps.**
Status: Applicable
Comment: Gap: app/log timestamps are local-time, not UTC; Snowflake platform logs are UTC.

**For limited capacity, log start-up/shutdown, login/access attempts, unexpected events.**
Status: Applicable
Comment: The app logs unexpected/processing events; login/access is recorded by Snowflake.

# === malicious_code ===

## Malicious Code Search Requirements

**Verify source code and third-party libraries do not contain Easter eggs or unwanted functionality.**
Status: Applicable
Comment: Source reviewed — no Easter eggs/unwanted functionality, no dynamic execution. Deps scanned by report-only SCA (pip-audit) in CI, clean as of refresh. Residual: authoritative scan via Nexus/JFrog Xray on `environment.yml`.

**Search for time bombs by examining date/time-related functions.**
Status: Applicable
Comment: Date/time usage is legitimate and documented — date-relative DQRs and snapshots compare against `datetime.now()`; mock data anchors to `_MOCK_NOW`. No time bombs or date-gated hidden behaviour.

**Ensure no unauthorized phone-home / data-collection capabilities; obtain permission if present.**
Status: Applicable
Comment: Only intentional outbound is the Snowflake connection; no HTTP-fetching libraries or analytics in app code. Gap: Streamlit's default usage-stats telemetry (`browser.gatherUsageStats`) is not disabled.

**Ensure no backdoors (hard-coded accounts, code obfuscation, rootkits).**
Status: Applicable
Comment: No hard-coded accounts/credentials in tracked source, no code obfuscation (readable Python), and no rootkit/privilege capability (no native code).

**Check for malicious code such as salami attacks, logic bypasses, or logic bombs.**
Status: Applicable
Comment: No logic bombs or hidden bypasses. Scoring/DQR logic is deterministic and test-covered; rules with missing dependencies raise `CustomRuleNotEvaluated` rather than silently bypassing checks.

**Avoid excessive permissions to privacy features (contacts, camera, microphone, location).**
Status: Not Applicable
Comment: Web/Streamlit app with no device-permission model; it requests no access to contacts/camera/microphone/location.

## Code Integrity Controls Requirements

**Use a code-analysis tool that detects potentially malicious code, unsafe file operations, and network connections.**
Status: Applicable
Comment: CI runs report-only SAST (bandit) detecting malicious patterns, unsafe file ops, and risky calls; in-app posture is favourable. Residual: enterprise SAST (Erebor) still needs wiring via the org pipeline.

## Deployed Application Integrity Controls

**Auto-updates obtained over secure channels and digitally signed; validate signatures before installation.**
Status: Applicable
Comment: No client-side auto-update mechanism; production updates are deployments via the Snowflake Git integration over HTTPS. Integrity rests on branch protection. Follow-up: enforce branch protection on the deploy branch.

**Employ integrity protections (code signing / SRI); avoid loading code from untrusted sources.**
Status: Applicable
Comment: Loads no code from untrusted sources — no dynamic/remote imports, no `eval`/`exec`, no external CDN assets (SRI not needed). Code signing is N/A; Git integrity + branch protection is the equivalent control.

**Protect against sub-domain takeovers (regularly check DNS names for expiry/changes).**
Status: Not Applicable
Comment: The app manages no DNS records or custom domains; under SiS it is served on a Snowflake-owned hostname, and DNS lifecycle is Snowflake's responsibility.

## Network Communication Requirements

**Use a certificate store or pin the endpoint certificate/public key; reject different certificates/keys.**
Status: Applicable
Comment: The Snowflake connector validates the endpoint certificate against the CA trust store (with OCSP) and the app never disables it. Certificate/public-key pinning is not implemented — a deliberate, acceptable choice for the managed connector.

**Avoid relying on a single insecure communication channel for critical operations.**
Status: Applicable
Comment: There is a single external channel (Snowflake), but it is TLS-secured — not insecure. No critical operation traverses an unencrypted channel.

**Encrypt data on the network using TLS; ensure consistent use of secure channels.**
Status: Applicable
Comment: All data-in-transit to Snowflake uses TLS; under SiS the user-to-app channel is Snowsight HTTPS and data access is in-platform. Consistent secure-channel use.

**Verify the X.509 certificate of the remote endpoint; accept only trusted-CA-signed certificates.**
Status: Applicable
Comment: The Snowflake connector verifies the remote X.509 certificate chain against trusted CAs by default; the app does not weaken this.

**Depend on up-to-date connectivity and security libraries.**
Status: Applicable
Comment: Connectivity/security libraries were refreshed (`urllib3`, `cryptography`, `requests`, `pyjwt`) and are vulnerability-checked by report-only SCA (pip-audit), clean as of refresh. Residual: authoritative SCA via JFrog Xray on the Anaconda set plus update alerting.

**Align TLS settings with current best practices (or as close as mobile OS support allows).**
Status: Applicable
Comment: TLS version/cipher selection is owned by the Snowflake connector/serving layer (modern suites); the app does not downgrade or override them. Platform-delegated; verify at the deployed endpoint.

# === mobile_security ===

## Resiliency against Reverse Engineering Requirements

**Implement device binding using a unique device fingerprint.**
Status: Not Applicable
Comment: No mobile/device context; access is bound to Snowflake identity, not a device fingerprint.

**Trigger various types of responses, including delayed and stealthy ones (anti-analysis).**
Status: Not Applicable
Comment: Anti-reverse-engineering logic protects distributed mobile binaries; there is no client binary here.

**Apply application-level payload encryption for defense in depth.**
Status: Not Applicable
Comment: No mobile client/transport; transport is TLS via the Snowflake connector/Snowsight.

**Apply obfuscation to programmatic defenses to impede dynamic analysis.**
Status: Not Applicable
Comment: No distributed binary; the app is server-side Python not shipped to a client.

**Detect and respond to the app running in an emulator.**
Status: Not Applicable
Comment: No mobile runtime; there is no emulator concept for a Streamlit web app.

**Detect and respond to tampering with code/data in memory, executables, and sandbox data.**
Status: Not Applicable
Comment: No client-side executable or mobile sandbox; the app runs in Snowflake's managed compute.

**Detect and respond to widely used reverse engineering tools/frameworks.**
Status: Not Applicable
Comment: No mobile binary is exposed to such tooling.

**Detect and respond to rooted/jailbroken devices.**
Status: Not Applicable
Comment: No mobile device context; root/jailbreak detection does not apply to a web app.

**Prevent debugging and detect/respond to attached debuggers.**
Status: Not Applicable
Comment: No distributed client process for an attacker to attach a debugger to.

**Use robust obfuscation for sensitive computations; prefer hardware-based isolation.**
Status: Not Applicable
Comment: No on-device computation; scoring/DQR logic runs server-side in Snowflake compute.

**Encrypt executable files/libraries; encrypt or pack important code/data segments.**
Status: Not Applicable
Comment: No shipped executables/libraries to encrypt or pack; the app is server-side source.

**Implement multiple mechanisms in each defense category for resiliency.**
Status: Not Applicable
Comment: No mobile anti-tamper defense categories exist for this application.

## Platform Requirements

**Clear WebView's cache, storage, and loaded resources before destruction.**
Status: Not Applicable
Comment: The app uses no WebView; browser caching is handled under the Data Protection theme.

**Prevent usage of custom third-party keyboards when entering sensitive data.**
Status: Not Applicable
Comment: No mobile keyboard context; inputs are entered in a desktop browser.

**Protect sensitive functionality exported through IPC facilities and custom URL schemes.**
Status: Not Applicable
Comment: The app exposes no IPC mechanisms or custom URL schemes.

**Disable JavaScript in WebViews unless explicitly required.**
Status: Not Applicable
Comment: No WebView exists; the UI is rendered by Streamlit in a standard browser.

**Request the minimum set of permissions necessary.**
Status: Not Applicable
Comment: No mobile OS permission model; data-layer least-privilege is covered under Access Control.

**Configure WebViews to allow only necessary protocol handlers (ideally HTTPS only).**
Status: Not Applicable
Comment: No WebView/protocol-handler configuration; the app has no mobile client.

**Protect against screen overlay attacks (Android only).**
Status: Not Applicable
Comment: Android-specific; the app has no Android client.

**Ensure WebView only renders JavaScript within the app package if native methods are exposed.**
Status: Not Applicable
Comment: No WebView and no native bridge; this control has no surface in a Streamlit web app.

# === session_management ===

## Defenses Against Session Management Exploits

**Ensure a valid login session or require re-authentication / secondary verification before sensitive transactions or account modifications.**
Status: Applicable
Comment: A valid Snowflake login session is required to reach the app (platform-enforced), and the app is read-only with no sensitive operations warranting step-up. Follow-up: add a step-up check if a state-changing feature is ever introduced.

## Token-based Session Management

**Use session tokens instead of static API secrets and keys (except legacy).**
Status: Applicable
Comment: Satisfied: the app uses no static API secrets/keys and authenticates via the Snowflake SSO session, not embedded credentials.

**Do not treat OAuth/refresh tokens as proof of presence; allow terminating trust with linked applications.**
Status: Not Applicable
Comment: The app handles no OAuth/refresh tokens; OAuth lifecycle and linked-app trust are owned by the corporate IdP / Snowflake.

**Use digital signatures/encryption/countermeasures for stateless session tokens.**
Status: Not Applicable
Comment: The app issues no stateless session tokens, so there are no token-protection countermeasures to implement.

## Session Binding Requirements

**Generate a new session token upon user authentication.**
Status: Not Applicable
Comment: The app generates no session tokens; session establishment is Snowflake's (a fresh Snowflake session per login).

**Generate session tokens using approved crypto with ≥64 bits of entropy.**
Status: Not Applicable
Comment: No app-generated session tokens; token generation and entropy are Snowflake/IdP's responsibility.

**Store session tokens in the browser securely (secure cookies / HTML5 storage).**
Status: Not Applicable
Comment: The app stores no session tokens client-side; `session_state` is server-side application state, and any browser session token is secured by the Snowsight serving layer.

## Session Logout and Timeout Requirements

**Allow users to view and log out of any/all active sessions and devices.**
Status: Not Applicable
Comment: The app has no session-management UI; viewing and terminating sessions/devices is a Snowflake/IdP capability, not an app feature.

**Terminate all other active sessions after a successful password change.**
Status: Not Applicable
Comment: The app has no passwords or session store; password change and cascading session termination are handled by the corporate IdP / Snowflake.

**Invalidate session tokens upon logout and expiration (prevent back-button/relying-party resume).**
Status: Applicable
Comment: Delegated: session invalidation is enforced by Snowflake/Snowsight; the app holds no auth tokens, and its `session_state`/cached connection are dropped on restart/domain switch (`close_shared_client`, `restart_app`). Follow-up: confirm the Snowflake session-expiration policy applies.

**Periodic re-authentication during active use and after idle periods.**
Status: Applicable
Comment: Delegated to Snowflake/IdP session and idle-timeout policy; the app cannot enforce re-auth. Follow-up: confirm a session/idle-timeout policy is configured for the app's user population.

## Fundamental Session Management Requirements

**Never reveal session tokens in URL parameters or error messages.**
Status: Applicable
Comment: Satisfied: the app has no session tokens to reveal, places no state in URL query parameters, and its verbose error path (`st.error(f"...{e}")`) exposes exception text, not tokens.

## Cookie-based Session Management

**Set the cookie `path` attribute as precisely as possible when sharing a domain.**
Status: Applicable
Comment: Platform-delegated: the app sets no cookies; any session cookie is set by the Snowsight serving layer. Follow-up: verify cookie attributes at the deployed endpoint (SSG/Heimdall).

**Use the `__Host-` prefix for session cookie confidentiality.**
Status: Applicable
Comment: Platform-delegated: the app sets no cookies and cannot apply the `__Host-` prefix; the session cookie is Snowflake's responsibility. Verify at the deployed endpoint.

**Set `HttpOnly` and `Secure` attributes for session cookies.**
Status: Applicable
Comment: Platform-delegated: the app sets no cookies; `HttpOnly`/`Secure` on the browser session cookie are owned by the Snowsight serving layer. Follow-up: confirm these flags via SSG/Heimdall at the deployed endpoint.

**Use the `SameSite` attribute to limit CSRF exposure.**
Status: Applicable
Comment: Platform-delegated: the app sets no cookies; `SameSite` is set by the serving layer (CSRF is additionally mitigated by Streamlit's default XSRF protection). Follow-up: verify at the deployed endpoint.

# === stored_cryptography ===

## Algorithms Requirements

**Ensure cryptographic modules fail securely and handle errors (prevent Padding Oracle attacks).**
Status: Not Applicable
Comment: The app implements no cryptographic module or decryption routine, so there is no padding-oracle surface.

**Authenticate encrypted data using signatures, authenticated cipher modes, or HMAC.**
Status: Not Applicable
Comment: The app encrypts no data of its own; authenticated encryption is handled by TLS and Snowflake storage, not app code.

**Allow reconfiguration/upgrading/swapping of cryptographic algorithms, key lengths, and modes.**
Status: Not Applicable
Comment: No app-implemented cryptographic components exist to reconfigure; TLS is upgradable via the connector and at-rest crypto is Snowflake-managed.

**Avoid insecure block modes, padding modes, small-block ciphers, and weak hashing algorithms.**
Status: Not Applicable
Comment: The app uses no block ciphers, padding modes, or cryptographic hashing. `zlib.crc32` in `src/mock_data.py` is a non-cryptographic seed, not a security hash.

**Perform cryptographic operations in constant-time to avoid information leaks.**
Status: Not Applicable
Comment: No app-implemented cryptographic comparisons or operations exist, so constant-time concerns do not arise in application code.

**Use industry-proven or government-approved cryptographic algorithms, modes, and libraries.**
Status: Not Applicable
Comment: The app selects no cryptographic algorithms. Where crypto applies (TLS in transit, Snowflake at-rest), the proven algorithms come from the connector/platform.

**Configure encryption IVs, cipher configurations, and block modes securely.**
Status: Not Applicable
Comment: The app configures no encryption; there are no IVs, cipher configs, or block modes in application code.

**Ensure nonces, IVs, and single-use numbers are not reused with the same key.**
Status: Not Applicable
Comment: The app generates and manages no nonces, IVs, or keys; this is handled inside the TLS/connector and Snowflake layers.

## Data Classification Requirements

**Encrypt regulated financial data, private data (PII/GDPR), and health data at rest.**
Status: Applicable
Comment: The app persists no regulated data at rest itself, and Snowflake encrypts source data at rest by default. Caveats: user-initiated CSV/JSON exports are plaintext, and data classification is not yet formally declared.

