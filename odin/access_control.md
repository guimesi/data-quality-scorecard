# Access Control — Odin Threat Modeling Assessment

**Application:** `data-quality-scorecard`

**Framing context:** The app enforces **no access control of its own** — authorization is
delegated to **Snowflake RBAC**. Under SiS this is two distinct controls: **USAGE grants on the
Streamlit object** (who may open the app) and the app's **owner's/caller's-rights role** (what
data it can read). The app is **read-only** (only `SELECT`; no INSERT/UPDATE/DELETE/DDL — verified
in `src/snowflake_client.py`), has **no administrative interface**, no per-object id API, and no
in-app role logic. The project-filter input is a **data filter, not an authorization boundary**.
Enforcement is server-side at Snowflake (a trusted layer), never client-side. (Overlaps the
Access Control Architectural theme; answered here operationally.)

> **SiS multi-user caveat (recurring):** because viewers granted USAGE share a single
> owner's-rights role, they all see the same data with no per-user differentiation. Per-user/
> per-project restriction would require **Snowflake row-access policies** or caller's-rights —
> the central object-level-authorization follow-up (cross-ref Authentication BOLA / Architecture
> ABAC).

---

## General Access Control Security Requirements

**Question:** Deny by default; use a whitelist (explicit grant) approach.
**Status:** Applicable
**Comment:** Satisfied at the data tier: Snowflake RBAC grants only explicitly allowed objects (deny-by-default), and the app's control flow fails safe (mode/domain gates reroute incomplete sessions). The app itself defines no permissions. Cross-ref Access Control Architecture.

**Question:** Enforce the principle of least privilege.
**Status:** Applicable
**Comment:** The app is read-only (cannot mutate data even if compromised). **Follow-up (high priority):** run the SiS app under a **dedicated least-privilege, read-only role** scoped to the required schemas, not a broad personal/admin role. Cross-ref Access Control Architecture.

**Question:** Clearly document access-control rules.
**Status:** Applicable
**Comment:** **Gap:** the access model (who is granted USAGE on the Streamlit object, which role the app executes as, schema scope) is **not documented** in the repo. Follow-up: document the SiS grant/role model alongside ARCHITECTURE.

**Question:** Enforce access control on all requests (including server-side redirects); manage in a secure server environment.
**Status:** Applicable
**Comment:** Every data request runs under the Snowflake session's role (enforced server-side); the app has **no server-side redirects**, and under SiS it executes in Snowflake's **sandboxed** environment. Delegated/satisfied.

**Question:** Integrate access control into data-layer queries; apply rate limiting.
**Status:** Applicable
**Comment:** Data-layer access control **is** Snowflake RBAC — queries execute under the role's grants. **Rate limiting** is not implemented in the app; it is a Snowflake/warehouse-tier concern (no app-exposed API to flood). Follow-up: rely on Snowflake resource controls; note as a platform responsibility.

**Question:** Validate user roles/permissions for each request; reject those lacking legitimate business purpose.
**Status:** Applicable
**Comment:** Per-request authorization is enforced by Snowflake (every query is evaluated against the session role); the app makes no role decisions and cannot escalate. Delegated.

---

## Other Access Control Considerations Requirements

**Question:** Administrative interfaces should use strong MFA.
**Status:** Not Applicable
**Comment:** The app exposes **no administrative interface**. Snowflake account/role administration is performed outside the app (Snowsight), protected by the corporate IdP's MFA. No in-app admin surface to protect.

**Question:** Disable directory browsing; prevent disclosure of sensitive file/directory metadata.
**Status:** Applicable
**Comment:** Satisfied: the app serves no static files or directories (no filesystem exposure; downloads are generated in memory). There is no directory-browsing or file-metadata-disclosure surface. Affirm.

**Question:** Use step-up/adaptive authentication for lower-value systems; segregation of duties for high-value applications.
**Status:** Applicable
**Comment:** The app performs **no state-changing or fraud-sensitive transactions** (read-only scorecards), so in-app step-up auth and segregation of duties are not warranted. Any duty/role segregation is expressed via Snowflake roles. Follow-up only if a state-changing feature is later added. Cross-ref Session Management.

**Question:** (Narrative) These measures help ensure robust security and integrity of sensitive systems.
**Status:** Not Applicable
**Comment:** Narrative summary statement, not an actionable control; the substantive controls are addressed in the items above.

---

## General Access Control Design Requirements

**Question:** Enforce least privilege; protect against unauthorized access and privilege escalation.
**Status:** Applicable
**Comment:** Access is limited to what the Snowflake role grants; the app is read-only and contains **no role-switching/privilege-elevation path**. Follow-up: dedicated least-privilege role (above). Cross-ref Access Control Architecture.

**Question:** Design access controls to fail securely; exceptions must not compromise security.
**Status:** Applicable
**Comment:** Fails safe: the app's gates reroute incomplete sessions, rule dependencies that are missing raise `CustomRuleNotEvaluated` (no silent bypass), and any unauthorized data access is **denied by Snowflake**. Exceptions degrade to error/"Not evaluated" states, not to elevated access. Cross-ref Code Quality (deny-by-default).

**Question:** Protect user/data attributes from manipulation; enforce rules on a trusted service layer.
**Status:** Applicable
**Comment:** The user identity is the **Snowflake session** (not an app-held, manipulable attribute), and authorization is enforced **server-side at Snowflake** (trusted layer), not in the client. The app exposes no attribute the client could tamper with to elevate access.

**Question:** New users/roles start with minimal permissions (deny by default); new features granted explicitly.
**Status:** Applicable
**Comment:** Under SiS, a new user has **no access until explicitly granted** USAGE on the Streamlit object (and the role's grants) — deny-by-default at the Snowflake tier. Follow-up: keep grant issuance deliberate and documented. Delegated/satisfied.

---

## Operation Level Access Control Requirements

**Question:** Strong access controls and security measures to maintain data integrity and confidentiality.
**Status:** Applicable
**Comment:** Integrity: the app is **read-only**, so it cannot alter source data regardless of input. Confidentiality: data access is scoped by the Snowflake role and encrypted at rest/in transit by the platform (under SiS). Cross-ref Data Protection / Stored Cryptography.

**Question:** Implement robust anti-CSRF mechanisms for authenticated and unauthenticated functionality, including against automated attacks.
**Status:** Applicable
**Comment:** CSRF is mitigated by **Streamlit's default XSRF protection**, the authenticated Snowsight context under SiS, and the app's **read-only** nature (no state-changing endpoints to forge). Follow-up: verify XSRF protection remains enabled (do not disable it in any added config.toml); verify the SiS-served context at the endpoint. Cross-ref Session Management.

**Question:** Safeguard sensitive data/APIs against direct object attacks (unauthorized create/read/update/delete).
**Status:** Applicable
**Comment:** No IDOR/CRUD surface: the app is read-only (no create/update/delete) and exposes **no per-object id API** — data access is whole-data-product reads governed by Snowflake RBAC; the project filter is a data filter, not an object-authorization key. **Caveat:** under multi-user SiS all viewers share the owner's-rights role, so read access is uniform — per-user object restriction would need row-access policies. Cross-ref Authentication (BOLA) / Architecture (ABAC).

**Question:** Prevent altering someone else's data or accessing all records without permission.
**Status:** Applicable
**Comment:** Altering data is impossible (read-only). "Accessing all records" is bounded by the **Snowflake role's grants** — the app reads only what the role permits. The residual consideration is the shared-role multi-user model (same caveat as above): if different viewers must be limited to different records, enforce it with Snowflake row-access policies rather than in the app.
