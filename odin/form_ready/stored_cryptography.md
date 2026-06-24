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
