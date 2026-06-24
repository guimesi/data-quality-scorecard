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
