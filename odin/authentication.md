# Authentication — Odin Threat Modeling Assessment

**Application:** `data-quality-scorecard`

**Framing context — the app implements NO authentication of its own.** All authN is
delegated to **Snowflake SSO** backed by the corporate IdP:
- Locally: `externalbrowser` SSO (the connector opens the browser → IdP).
- Production (SiS): the viewer is already authenticated by their **Snowflake account login**
  (Snowsight); the app runs under its **owner's/caller's-rights role**.

Consequently the app has **no login UI, no password handling or storage, no session-token
issuance, no JWT, no SAML assertion processing, no OTP, and no credential-recovery flow** —
verified in code (no auth/session/token logic; `src/snowflake_client.py` only opens a
connection). Most items in this theme are therefore **Not Applicable (delegated to Snowflake
+ corporate IdP)**. The genuinely application-relevant items are: **no credentials in source**
(critical because the repo is the SiS deploy source), **use of an EM-approved IdP**,
**object-level authorization under multi-user SiS**, and **session termination**.

> **SiS production note:** authentication, MFA, session timeout, identity directory, and
> device/conditional-access policy are all owned by **Snowflake + the corporate IdP**, not the
> app. The app's job is to be a correct relying party and to never hold credentials.

---

## SAML Security Requirements

*All Not Applicable — the app performs no SAML processing.* SSO assertion validation
(timestamp, signature against IdP metadata key, signed assertion/parent) is handled inside the
**Snowflake connector / IdP**, not in application code.

**Question:** Validate the timestamp and verify the service-provider signature. — **Not Applicable** — no SAML handling in the app.
**Question:** Validate the assertion signature against metadata key, not the embedded key. — **Not Applicable** — no SAML handling in the app.
**Question:** Check that the assertion and its parent tag are signed. — **Not Applicable** — no SAML handling in the app.

---

## General Authentication Security Requirements

**Question:** Implement object-level authorization checks in every function accessing data by user input (BOLA / API1:2019).
**Status:** Applicable
**Comment:** The app performs **no in-app object-level authorization** — data access is governed by Snowflake RBAC, and the project filter is a *data filter*, not an authorization boundary. Under SiS the app can be **multi-user** (USAGE grants) sharing one owner's-rights role, so all viewers see the same data with no per-user object checks. If per-user/per-project data restriction is required, it must be enforced via **Snowflake row-access policies / caller's-rights**, not app code. Cross-ref Access Control (ABAC follow-up).

**Question:** Inform users of sensitive account activities (device lists, IP/location, block devices).
**Status:** Not Applicable
**Comment:** The app has no account-management surface; account-activity visibility is an IdP/Snowflake capability.

**Question:** Default service credentials must not be used in production/non-production.
**Status:** Applicable
**Comment:** Satisfied: the app uses **no service or default credentials** (SSO locally; the Snowflake session under SiS). Follow-up: ensure the SiS app runs under a **dedicated least-privilege role**, not a default/shared admin role. Cross-ref Access Control.

**Question:** Authentication mechanisms correctly implemented to prevent token compromise / identity assumption (API2:2019).
**Status:** Applicable
**Comment:** Delegated to a well-vetted mechanism (Snowflake SSO / corporate IdP); the app issues, stores, and validates no tokens itself, so there is no app-side token-handling flaw to exploit. Cross-ref Authentication Architecture.

**Question:** Each component authenticates every connection; standalone services (SQL Server, Redis) require authentication.
**Status:** Applicable
**Comment:** The app is a single-process monolith whose only backend connection — Snowflake — **requires authentication** (SSO/session). There are no unauthenticated standalone services (no Redis/cache/secondary DB). Affirm. Cross-ref Communications / Access Control.

**Question:** Source code must not include production credentials.
**Status:** Applicable
**Comment:** Satisfied and **high-priority for SiS** (the GitHub repo is the deployment source): verified no credentials in tracked source (`git ls-files`); `.env` is gitignored/untracked and holds only non-secret identifiers. **Control added:** secret scanning (gitleaks) now runs in CI (`.github/workflows/security.yml`, report-only). Follow-up: consider a pre-commit gitleaks hook too. Cross-ref Data Protection / Configuration.

---

## Single or Multi Factor One Time Verifier Requirements

*All Not Applicable — the app implements no OTP/TOTP.* One-time-verifier generation, reuse
rejection, lifetime, revocation, and key protection are IdP/Snowflake-MFA responsibilities.

**Question:** Log/reject reused TOTPs; single-use; defined lifetime. — **Not Applicable** — no OTP in the app.
**Question:** Revoke physical OTP generators across sessions. — **Not Applicable** — no OTP in the app.
**Question:** Approved crypto for OTP generation/seeding/verification; protect keys in HSM. — **Not Applicable** — no OTP in the app.

---

## Credential Storage Requirements

*All Not Applicable — the app stores no passwords.* Authentication is SSO; there is nothing
to salt/hash. (No password store, no verifier, no KDF in the codebase.)

**Question:** Salt + one-way hash passwords with unique salts. — **Not Applicable** — no password storage.
**Question:** KDF with secret salt stored separately. — **Not Applicable** — no password storage.
**Question:** Unique sufficient-length salt; store salt and hash securely. — **Not Applicable** — no password storage.

---

## Authentication and Session Management Requirements

**Question:** Use random session identifiers (stateful) or securely signed tokens (stateless).
**Status:** Not Applicable
**Comment:** The app issues no authentication session identifiers or tokens; the authenticated session is Snowflake's. (Streamlit `session_state` is application state, not an authentication credential.)

**Question:** Terminate existing sessions at the remote endpoint on logout.
**Status:** Applicable
**Comment:** Delegated: logging out of Snowflake/Snowsight (or ending the externalbrowser session) terminates authentication at the platform. The app additionally drops its cached connection/state via `close_shared_client()` / `restart_app` on restart/domain switch. Cross-ref Architecture (session handling).

**Question:** Web applications must use AAD or an ExxonMobil-approved IdP to authorize OAuth2 access tokens.
**Status:** Applicable
**Comment:** Authentication flows through Snowflake SSO to the corporate IdP (assumed EM-approved). The app does not handle OAuth tokens directly. Follow-up/uncertainty: confirm the configured IdP is on the EM-approved list and aligns with the EA mandate. Cross-ref Authentication Architecture (EA mandate item).

---

## Look-up Secret Verifier Requirements

*All Not Applicable — the app uses no look-up/recovery secrets.*

**Question:** Lookup secrets resistant to offline attacks (unpredictable). — **Not Applicable** — none used.
**Question:** High randomness or salted+hashed lookup secrets. — **Not Applicable** — none used.
**Question:** Single-use lookup secrets. — **Not Applicable** — none used.

---

## General Authenticator Requirements

**Question:** Notify users if authentication factors are changed/replaced.
**Status:** Not Applicable
**Comment:** Factor management is an IdP/Snowflake responsibility; the app has no authenticator management.

**Question:** Anti-automation controls (rate limiting, CAPTCHA) against brute force; notify on changes.
**Status:** Not Applicable
**Comment:** The app has no login to brute-force; anti-automation for authentication is enforced at the IdP/Snowflake tier.

**Question:** Weak authenticators (SMS) only as secondary verification.
**Status:** Not Applicable
**Comment:** The app implements no authenticators; the choice/strength of factors is the IdP's.

**Question:** Implement robust MFA (cryptographic devices, OTP, hardware key press).
**Status:** Applicable
**Comment:** MFA is **available via the corporate IdP** through Snowflake SSO (delegated, not app-implemented). Follow-up: confirm MFA is enforced for the user population accessing the SiS app. Cross-ref Authentication Architecture.

---

## Single Sign On (SSO) Security Requirements

**Question:** Component Security — all SSO components secured against vulnerabilities.
**Status:** Applicable
**Comment:** The SSO components are **Snowflake + the corporate IdP** (platform-secured); the app is a relying party with no SSO component of its own. Assumption: those platforms are hardened/patched by their owners. Cross-ref Authentication Architecture.

**Question:** Session Timeouts — auto-logout after inactivity.
**Status:** Applicable
**Comment:** Session/idle timeout is enforced by Snowflake/IdP session policy, not the app. Follow-up: confirm a Snowflake session/idle-timeout policy applies to the SiS app.

**Question:** Identity Directory Accuracy.
**Status:** Applicable
**Comment:** The identity directory is the corporate IdP (EM-managed); accuracy/lifecycle is an organizational responsibility, not the app's. Delegated.

**Question:** Device Restrictions for SSO.
**Status:** Applicable
**Comment:** Platform-delegated. Device/conditional-access restrictions are an IdP policy that applies to the deployed SSO system but cannot be enforced in app code (the app has no device-trust surface). Follow-up: confirm the corporate IdP enforces any required device/conditional-access policy for the SiS app's user population. Cross-ref Authentication Architecture.

**Question:** Modern Authentication Protocols (e.g. SAML).
**Status:** Applicable
**Comment:** SSO uses modern protocols (SAML/OAuth) between Snowflake and the IdP; the app relies on them rather than implementing legacy auth. Delegated; satisfied by the chosen platform.

---

## Cryptographic Software and Devices Verifier Requirements

*All Not Applicable — the app implements no cryptographic verification/challenge-response.*
(No app-managed keys or crypto; see Cryptographic Architecture, also N/A.)

**Question:** Approved algorithms for generation/seeding/verification. — **Not Applicable** — no app crypto verifier.
**Question:** Verification keys stored in TPM/HSM/OS secure store. — **Not Applicable** — the app manages no keys.
**Question:** Statistically unique challenge nonce to prevent replay. — **Not Applicable** — no app challenge-response.

---

## JSON Web-Token Security Requirements

*All Not Applicable — the app issues/consumes no JWTs and exposes no REST/JWT API.* (The
JSON the app produces are **file downloads**, not authenticated API responses.)

**Question:** Outer JSON element must be an object, not an array. — **Not Applicable** — no JWT/REST API responses. (Note: the `ml_lab_history.json` *download* is a JSON array, but it is a user-initiated file export, not an API/auth response.)
**Question:** Reject JWT auth attempts with 403. — **Not Applicable** — no JWT authentication.
**Question:** Escape HTML entities / control chars in JSON REST responses. — **Not Applicable** — no REST API; exports use `json.dumps` which escapes correctly.
**Question:** Validate JWT aud/nbf/exp/bearer per request. — **Not Applicable** — no JWT.

---

## Out of Band Verifier Requirements

*All Not Applicable — the app has no out-of-band authentication.* Any OOB factor is the IdP's.

**Question:** Don't offer cleartext OOB (SMS/PSTN) by default; prefer push. — **Not Applicable** — no app OOB auth.
**Question:** Secure-random initial code over an independent secure channel. — **Not Applicable** — no app OOB auth.

---

## Credential Recovery Requirements

*All Not Applicable — the app has no credential/password recovery flow.* Password recovery is
handled by the corporate IdP/Snowflake.

**Question:** System-generated recovery secrets not sent in clear text. — **Not Applicable** — no recovery flow in the app.
**Question:** Avoid password hints / knowledge-based auth. — **Not Applicable** — no recovery flow in the app.
**Question:** Secure recovery (TOTP/push/offline) without revealing current password. — **Not Applicable** — no recovery flow in the app.
**Question:** Re-proof identity at original level if MFA factors lost. — **Not Applicable** — IdP/organizational process.

---

## Mobile apps authentication Requirements

*All Not Applicable — there is no mobile application* (see Mobile Security theme).

**Question:** Biometric auth unlocks a keystore, not a boolean API. — **Not Applicable** — no mobile app.
**Question:** Remote endpoint prevents excessive credential submissions. — **Not Applicable** — no mobile app; brute-force protection is IdP/Snowflake.
**Question:** Enforce 2FA at the remote endpoint. — **Not Applicable** — no mobile app; MFA is delegated to the IdP.

---

## Password Security Requirements

*All Not Applicable — the app has no passwords* (SSO authentication; no password fields,
storage, or hashing in the codebase).

**Question:** Allow temporary view of masked password / last character. — **Not Applicable** — no password fields.
**Question:** Allow users to change passwords. — **Not Applicable** — IdP-managed.
**Question:** High bcrypt/PBKDF2 work factor. — **Not Applicable** — no password hashing in the app.
**Question:** Use PAGE guidance / password generator. — **Not Applicable** — no passwords in the app.

---

## Service Authentication Requirements

**Question:** Passwords/API keys/integration secrets not in source/repos; use software key stores / TPM / HSM.
**Status:** Applicable
**Comment:** Satisfied today (no secrets in tracked source; `.env` gitignored). The one production secret — the **GitHub PAT for the SiS Git integration** — must be stored as a **Snowflake SECRET object**, never in the repo (the `deploy/` SQL creates it as a SECRET). **Control added:** secret scanning (gitleaks) is in CI. Cross-ref Data Protection / SiS migration notes.

**Question:** Store passwords/sensitive information with protection against offline recovery attacks.
**Status:** Applicable
**Comment:** The app stores no passwords/credentials to recover offline (SSO; no secret store). The only sensitive value (Git-integration secret) is held in Snowflake's secret store, not on disk in the repo. Affirm + same secret-scanning follow-up.

---

## Authenticator Lifecycle Requirements

**Question:** Support enrollment/use of subscriber devices (U2F/FIDO).
**Status:** Not Applicable
**Comment:** Authenticator enrollment is an IdP capability; the app implements none.

**Question:** System-generated initial passwords/activation codes are random, ≥6 chars, expiring.
**Status:** Not Applicable
**Comment:** The app generates no passwords/activation codes.

**Question:** Renewal instructions for time-bound authenticators sent with advance notice.
**Status:** Not Applicable
**Comment:** The app issues no authenticators; renewal/notification is IdP/organizational.
