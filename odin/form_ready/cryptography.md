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
