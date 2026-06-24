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
