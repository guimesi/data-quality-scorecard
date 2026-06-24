# Communications — Odin Threat Modeling Assessment

**Application:** `data-quality-scorecard`

**Framing context:** The app has a single external communication path — the **Snowflake
connection** — over **TLS**, with the connector performing **X.509 validation against trusted
public CAs and OCSP revocation checks by default**; the app never disables this (no
`insecure_mode`/`verify=False` anywhere) and never falls back to plaintext. Under **SiS**, the
inbound user↔app channel is **Snowsight HTTPS** and data access is in-platform — both
Snowflake-managed. TLS **version/cipher-suite selection and response headers (HSTS) are owned by
the connector / Snowflake serving layer**, not settable from app code; those items are therefore
platform-delegated and verifiable at the deployed endpoint (SSG/Heimdall). (Overlaps the
Communications Architectural theme; answered here at the operational level.)

---

## Server Communications Security Requirements

**Question:** All encrypted connections to external systems must be authenticated.
**Status:** Applicable
**Comment:** Satisfied: the one external connection (Snowflake) is both **TLS-encrypted and authenticated** (SSO locally / the Snowflake session under SiS). No unauthenticated external connections exist. Cross-ref Authentication.

**Question:** Enforce TLS for all inbound/outbound connections; never revert to insecure/unencrypted protocols.
**Status:** Applicable
**Comment:** Outbound to Snowflake is TLS with no plaintext fallback (no `insecure_mode`); there are no other outbound integrations. Inbound is HTTPS via Snowsight under SiS (platform-enforced). Affirm.

**Question:** Log backend TLS connection failures for monitoring/troubleshooting.
**Status:** Applicable
**Comment:** Partial: connection failures surface as exceptions logged via `logger.warning(..., exc_info=True)` (e.g. `src/snowflake_client.py`, one-click/build paths), but there is **no dedicated TLS-failure logging** and no central log store locally. Follow-up: under SiS rely on Snowflake connection/query history for connection diagnostics; keep log level at WARNING+ and avoid leaking values in traces. Cross-ref Error Handling and Logging.

**Question:** Use trusted TLS certificates; if self-signed, trust only specific internal CAs and reject others.
**Status:** Applicable
**Comment:** The connector validates the Snowflake endpoint certificate against trusted **public CAs**; the app configures no self-signed/internal-CA trust overrides and does not relax validation. Affirm.

**Question:** Enable proper certificate revocation (e.g. OCSP stapling).
**Status:** Applicable
**Comment:** The Snowflake connector performs **OCSP certificate-revocation checking by default**, and the app does not disable it (no OCSP-fail-open / `insecure_mode`). Affirm; verify the setting remains enabled.

---

## General Communication Strategy Requirements

**Question:** Tokenize sensitive data (e.g. JSON) where direct access is unnecessary.
**Status:** Not Applicable
**Comment:** The app's function (profiling, scoring, exporting scorecards) **requires direct access to the actual data values**, and data stays within the TLS/Snowflake boundary — there is no third party to whom tokenized data would be passed. Tokenization is not applicable to this workflow.

**Question:** Secure non-public traffic across networks; use mechanisms (e.g. nonces) against replay and brute force.
**Status:** Applicable
**Comment:** Non-public traffic (app↔Snowflake) is TLS-secured. Replay/brute-force defenses for authentication are provided by Snowflake/IdP (the app has no authentication endpoint and issues no nonces of its own). Delegated; cross-ref Authentication / Session Management.

**Question:** Maintain documentation/inventory of endpoints, hosts, and deployed versions; manage deprecated versions; prevent debug endpoints.
**Status:** Applicable
**Comment:** Improved: the external endpoint inventory is minimal (one Snowflake endpoint); the **SiS deployment is now documented** (`deploy/` + ARCHITECTURE/README) and the **production dependency inventory exists** (`environment.yml`, alongside `requirements.lock`). **Residual gap:** **debug output is not disabled** (the `st.error(f"...{e}")` path + Streamlit tracebacks; warehouse-runtime `config.toml` can't set `showErrorDetails`, so the fix is in-app generic error handling). Follow-up: replace raw-exception messages with generic text. Cross-ref Configuration / Error Handling.

---

## Client Communications Security Requirements

**Question:** All client connectivity uses secured TLS with no insecure fallback; regularly verify strong algorithms/ciphers/protocols with TLS testing tools.
**Status:** Applicable
**Comment:** Under SiS the client↔app channel is **Snowsight HTTPS** (no insecure fallback), and the app↔Snowflake channel is connector TLS. Cipher/protocol strength is owned by the platform/connector. Follow-up: regular TLS testing must target the **deployed Snowflake endpoint** (SSG/Heimdall), since the app cannot configure or test the serving TLS itself.

**Question:** Disable outdated SSL/TLS (SSLv2/3, TLS 1.0/1.1); prefer the latest TLS.
**Status:** Applicable
**Comment:** TLS version policy is owned by the Snowflake connector / serving layer (modern TLS; legacy versions disabled by the platform); the app neither enables nor downgrades to old versions. Platform-delegated; verify at the deployed endpoint.

---

## Communications Security Requirements

**Question:** Use public-CA-signed TLS certificates that are not expired.
**Status:** Applicable
**Comment:** Snowflake endpoints present public-CA-signed certificates; the connector rejects expired/invalid certificates by default. The app neither supplies nor overrides certificates. Affirm.

**Question:** Use OCSP where the stack and CA allow.
**Status:** Applicable
**Comment:** Satisfied: the Snowflake connector performs OCSP revocation checks by default (also captured under the revocation item above). Affirm.

**Question:** Use an approved TLS configuration; disable insecure ciphers/hashes (DES, 3DES, RC4, IDEA, MD5); manage key length/cipher suites.
**Status:** Applicable
**Comment:** Cipher-suite/key-length selection is owned by the Snowflake connector / serving layer, which uses modern suites and excludes the listed weak algorithms; the app does not configure or weaken cipher selection. Platform-delegated; follow-up: confirm via SSG/Heimdall that the deployed endpoint offers no weak ciphers.

**Question:** Configure APIs to use HSTS (all content over HTTPS).
**Status:** Applicable
**Comment:** HSTS is a serving-layer response header (Snowsight under SiS); the app cannot set it. Platform-delegated; verify presence at the deployed endpoint. Cross-ref Configuration (HTTP security headers).

**Question:** Never revert to unencrypted HTTP if HTTPS cannot be established.
**Status:** Applicable
**Comment:** Satisfied: the app never falls back to plaintext — the Snowflake connection has no insecure-mode fallback, and Snowsight serves HTTPS only. Affirm.
