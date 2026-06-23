# Cryptography — Odin Threat Modeling Assessment

**Application:** `data-quality-scorecard`

**Framing context — the app implements NO cryptography of its own.** Verified in code: there is
**no `hashlib`/`secrets`/`hmac`/`os.urandom`/`cryptography`/`Fernet` usage, no hashing, no
encryption, no key management, no password handling, and no OTP**. Authentication is SSO (no
passwords stored or processed); TLS is provided by the Snowflake connector / Snowflake platform;
key material is never exposed to the application.

**Important clarification to prevent SAST/Erebor false positives:** the only randomness in the
codebase is `numpy`'s `np.random.default_rng(...)`, used for **non-security** purposes only —
ML Lab statistics (k-means initialization, Dirichlet Monte-Carlo: `src/ml_lab.py`) and
**deterministic** mock-data generation (`src/mock_data.py`, seeded via `zlib.crc32` *for
reproducibility, not security*). No random value is ever used as a token, key, salt, nonce, or
secret, so a CSPRNG is not required. `zlib.crc32` is used as a stable seed, not as a security
hash. These should not be flagged as weak-cryptography/insecure-randomness findings.

> **SiS production note:** the one production secret — the GitHub PAT for the SiS Git
> integration — must live in a **Snowflake SECRET object**, not in the repo (cross-ref Data
> Protection / SiS migration notes). The app itself holds no keys or secrets.

---

## Secret Management requirements

**Question:** Avoid storing enterprise user passwords in nonvolatile storage.
**Status:** Applicable
**Comment:** Satisfied: the app stores **no passwords** anywhere (authentication is SSO; no password fields, no password store, no nonvolatile credential persistence). Affirm. Cross-ref Authentication.

**Question:** Protect memorized secrets using a password hash algorithm.
**Status:** Not Applicable
**Comment:** The app has no memorized secrets/passwords to hash (SSO; password handling is the corporate IdP's).

**Question:** Must not require arbitrary password changes, store passwords in nonvolatile storage, or truncate memorized secrets.
**Status:** Not Applicable
**Comment:** No password lifecycle in the app; password policy is the IdP's responsibility.

**Question:** Use a secrets management solution like a key vault for creating/storing/managing secrets.
**Status:** Applicable
**Comment:** The app manages no secrets of its own. The one production secret (the SiS Git-integration GitHub PAT) should be stored in a **Snowflake SECRET object** (Snowflake's managed secret store), never in the repo. Follow-up: confirm the Git-integration credential is vaulted in Snowflake. Cross-ref Data Protection / SiS migration notes.

**Question:** Display a password-strength meter for user-chosen memorized secrets.
**Status:** Not Applicable
**Comment:** No password entry in the app (SSO).

**Question:** Impose a maximum length limit on memorized secrets (≥64 characters).
**Status:** Not Applicable
**Comment:** No passwords in the app.

**Question:** Require users to enter old memorized secrets for changes.
**Status:** Not Applicable
**Comment:** No password-change flow in the app (IdP-managed).

**Question:** Ensure key material is not exposed to the application; use an isolated security module for cryptographic operations.
**Status:** Applicable
**Comment:** Satisfied: **no key material is exposed to the app** — cryptographic operations (TLS, SSO token handling) are performed by the Snowflake connector / corporate IdP, not by application code. The app performs no cryptographic operations. Affirm. Cross-ref Cryptographic Architecture (no app-managed keys).

**Question:** Do not require arbitrary changes to memorized secrets.
**Status:** Not Applicable
**Comment:** No passwords in the app; secret-rotation policy is the IdP's.

**Question:** Do not truncate memorized secrets; evaluate the entire secret or reject if too long.
**Status:** Not Applicable
**Comment:** No passwords in the app.

**Question:** Store a Boolean `password_compromised` value with the user's password hash.
**Status:** Not Applicable
**Comment:** No password store/hash in the app.

**Question:** Allow all printable ASCII characters and spaces in memorized secrets.
**Status:** Not Applicable
**Comment:** No passwords in the app.

**Question:** User-set memorized secrets ≥8 characters; random API-generated secrets ≥6 characters.
**Status:** Not Applicable
**Comment:** The app sets no passwords and generates no API secrets. (The Git PAT's properties are governed by GitHub/Snowflake, not the app.)

**Question:** Validate newly changed user passwords against specific criteria.
**Status:** Not Applicable
**Comment:** No password-change flow in the app.

**Question:** Composite memorized-secret policy (ASCII/spaces, ≥64 max, hashing, old-password-for-change, min length, complexity feedback).
**Status:** Not Applicable
**Comment:** Composite of the password items above — none apply, as the app has no passwords (SSO; all password policy is the corporate IdP's).

---

## One Time Password security requirements

**Question:** Use an approved CSPRNG to generate the OTP seed; prevent reuse even on unsuccessful attempts.
**Status:** Not Applicable
**Comment:** The app implements no OTP. Any MFA/OTP is provided by the corporate IdP, not the application.

**Question:** Prefer TOTP over HOTP or proprietary alternatives.
**Status:** Not Applicable
**Comment:** No OTP in the app; algorithm choice is the IdP's.

---

## Mobile apps Cryptography Requirements

**Question:** Verify the app uses secure random number generation and proven cryptographic primitives configured per best practices.
**Status:** Not Applicable
**Comment:** There is no mobile app, and the application performs **no cryptographic operations** requiring a CSPRNG. As noted in the framing: `np.random` is used solely for ML statistics and deterministic mock data (never for security values), so no secure-RNG/cryptographic-primitive requirement is triggered. (Stated explicitly to preempt a SAST/Erebor weak-randomness false positive.)

**Question:** Avoid deprecated algorithms, hardcoded keys, and reuse of cryptographic keys for multiple purposes.
**Status:** Not Applicable
**Comment:** No mobile app and no app cryptography. Affirmed by review: **no cryptographic algorithms are used in app code, no hardcoded keys exist** (verified — no key material in tracked source), and there are no keys to reuse. TLS algorithm selection is owned by the Snowflake connector/platform (modern suites).
