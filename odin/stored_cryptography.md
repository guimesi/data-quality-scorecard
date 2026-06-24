# Stored Cryptography — Odin Threat Modeling Assessment

**Application:** `data-quality-scorecard`

**Framing context:** The application implements **no cryptography of its own** — no encryption,
hashing, key management, IVs, nonces, cipher configuration, or constant-time routines (verified:
no `hashlib`/`secrets`/`hmac`/`cryptography`/`Fernet` in app code; the only randomness is
non-security `np.random`/`zlib.crc32` for ML stats and deterministic mock data — see the
Cryptography theme). It also **persists no data at rest itself** (no filesystem writes;
`session_state` is in-memory; CSV/JSON are user-initiated downloads). Cryptographic operations
that do occur are **platform-provided**: TLS in transit (Snowflake connector) and, under SiS,
**Snowflake encryption at rest** for source data.

Consequently the **Algorithms** items (which govern how an application *implements* crypto) are
**Not Applicable** — there is no app crypto module to misconfigure. The **Data Classification**
at-rest-encryption item is **Applicable** (platform-satisfied for source data, with an open
classification follow-up and a plaintext-export caveat).

---

## Algorithms Requirements

**Question:** Ensure cryptographic modules fail securely and handle errors (prevent Padding Oracle attacks).
**Status:** Not Applicable
**Comment:** The app implements no cryptographic module / decryption routine, so there is no padding-oracle surface. TLS error handling is internal to the Snowflake connector, not app code.

**Question:** Authenticate encrypted data using signatures, authenticated cipher modes, or HMAC.
**Status:** Not Applicable
**Comment:** The app encrypts no data of its own (nothing to authenticate). Authenticated encryption for data in transit/at rest is handled by TLS (connector) and Snowflake storage — not implemented in app code.

**Question:** Allow reconfiguration/upgrading/swapping of cryptographic algorithms, key lengths, and modes.
**Status:** Not Applicable
**Comment:** No app-implemented cryptographic components exist to reconfigure. The TLS stack is upgradable via the connector/platform dependency (an SCA/dependency concern, tracked in Configuration/Architecture), and at-rest crypto is Snowflake-managed.

**Question:** Avoid insecure block modes, padding modes, small-block ciphers, and weak hashing algorithms.
**Status:** Not Applicable
**Comment:** The app uses no block ciphers, padding modes, or cryptographic hashing. (`zlib.crc32` in `src/mock_data.py` is a non-cryptographic seed for deterministic mock data, not a security hash — see Cryptography theme; not to be flagged as weak hashing.)

**Question:** Perform cryptographic operations in constant-time to avoid information leaks.
**Status:** Not Applicable
**Comment:** No app-implemented cryptographic comparisons/operations exist; constant-time concerns do not arise in application code.

**Question:** Use industry-proven or government-approved cryptographic algorithms, modes, and libraries.
**Status:** Not Applicable
**Comment:** The app selects no cryptographic algorithms. Where crypto applies (TLS in transit, Snowflake at-rest encryption), the proven/approved algorithms are provided by the Snowflake connector/platform, not chosen by the app.

**Question:** Configure encryption IVs, cipher configurations, and block modes securely.
**Status:** Not Applicable
**Comment:** The app configures no encryption — there are no IVs/cipher configs/block modes in application code.

**Question:** Ensure nonces, IVs, and single-use numbers are not reused with the same key.
**Status:** Not Applicable
**Comment:** The app generates and manages no nonces/IVs/keys; this is handled inside the TLS/connector and Snowflake layers.

---

## Data Classification Requirements

**Question:** Encrypt regulated financial data, private data (PII/GDPR), and health data at rest.
**Status:** Applicable
**Comment:** Relevant to the data the app reads in Snowflake mode — internal **cost-estimate / quality** data (potentially confidential, financial-adjacent business data) plus a **corporate user identity** (email, limited PII). No health data is involved. The app **persists no regulated data at rest itself**. Under SiS, **Snowflake encrypts data at rest by default**, so the source-data at-rest requirement is **satisfied by the platform**. Residual gaps/follow-ups: (1) user-initiated **CSV/JSON exports are plaintext** — bounded under SiS (they stay within the Snowflake boundary) but plaintext on a local disk in the legacy local mode; (2) **data classification is not formally declared** — confirming the sensitivity tier of `UC_GP_CSC`/Quality schemas determines which financial/PII regulations (e.g. GDPR) actually apply and whether export handling needs tightening. Cross-ref Data Protection (encryption at rest / classification follow-up).
