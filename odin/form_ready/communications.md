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
