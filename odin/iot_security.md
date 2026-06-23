# IoT Security — Odin Threat Modeling Assessment

**Application:** `data-quality-scorecard`

**Theme-level determination: overwhelmingly Not Applicable — this is not an IoT device.**

`data-quality-scorecard` is a **Python/Streamlit web application** deployed as **Streamlit in
Snowflake**. There is **no hardware, firmware, bootloader, embedded/secure OS, physical
interface/port, device identity, or over-the-air/firmware update mechanism** anywhere in the
project. All physical-security, secure-boot, device-OS, device-credential, and firmware-update
requirements are therefore Not Applicable.

The exceptions are the **general software-security items** embedded in some subsections
(Secure Coding Guidelines, and parts of Network / Data Protection / Encryption / Logging).
Those are **Applicable** and are assessed in depth in the dedicated themes — to avoid
double-claiming controls, the items below are marked Applicable with a **cross-reference** to
the authoritative theme. The org-named tools (Erebor SAST, Heimdall DAST, Nexus SCA) are
called out as concrete pipeline follow-ups.

> **SiS production note:** runtime isolation, OS, storage encryption, boot, and patching of
> the execution environment are all **Snowflake-managed** under SiS — reinforcing the N/A
> status of the device/OS/boot items (they are the platform's responsibility, not the app's).

---

## Physical Security requirements

*All Not Applicable — no physical device/hardware exists.*

**Question:** Require authentication for debug interfaces or ports. — **Not Applicable** — no hardware debug ports.
**Question:** Make device circuitry tamper-resistant (epoxy/resin). — **Not Applicable** — no physical device.
**Question:** Ensure no backdoors or hidden entry points. — **Applicable** — while there is no hardware, the principle (no hidden entry points in code) applies: the app has no `eval`/`exec`/backdoor and source is reviewable in Git. Cross-ref Input Validation (no dynamic execution) + Architecture (branch protection follow-up).
**Question:** Incorporate hardware security features (security chips/coprocessors). — **Not Applicable** — no hardware.
**Question:** Ensure device can recover after a power outage. — **Not Applicable** — no device; SiS state is platform-managed.
**Question:** Use a unique physical identifier for device distinction. — **Not Applicable** — no device.
**Question:** Disable unnecessary physical interfaces or ports. — **Not Applicable** — no physical interfaces.
**Question:** Restrict direct access to administrative capabilities. — **Applicable** — maps to Snowflake RBAC / least-privilege role + USAGE grants (no in-app admin surface). Cross-ref Access Control.
**Question:** Validate device root-of-trust boot process and monitor for anomalies. — **Not Applicable** — no device boot.

---

## Secure Coding Guidelines requirements

**Question:** Avoid deploying debug versions of code; exclude unnecessary files.
**Status:** Applicable
**Comment:** Gap: no production hardening config (debug/error-detail display) and dev artifacts (notebook, tests, docs) are in the Git-deployed source. Cross-ref Configuration ("remove unnecessary features" + "disable debug modes").

**Question:** Prevent injection by separating untrusted data from commands/queries.
**Status:** Applicable
**Comment:** In place: parameterized SQL (bound filter values), `html.escape`, CSV formula sanitization. Cross-ref Input Validation, Sanitization and Encoding.

**Question:** Cryptographically sign code; implement run-time protection and secure execution monitoring.
**Status:** Not Applicable
**Comment:** No shipped binary to sign (pure-Python source deployed from Git). Run-time isolation is provided by the SiS sandbox. The practical integrity control is Git branch protection + (optional) signed commits — cross-ref Architecture (source-control / Malicious Software follow-ups).

**Question:** Sanitize input in web applications using URL or HTML encoding.
**Status:** Applicable
**Comment:** In place: `html.escape` on data rendered via `unsafe_allow_html`; Streamlit auto-escaping. Cross-ref Input Validation (output-encoding).

**Question:** Handle errors gracefully without revealing sensitive information.
**Status:** Applicable
**Comment:** Partial; gap = raw-exception interpolation (`st.error(f"...{e}")`) + Streamlit default tracebacks (no config disabling). Cross-ref Error Handling and Logging.

**Question:** Do not hard-code credentials; store securely and ensure updateable.
**Status:** Applicable
**Comment:** Satisfied: no hard-coded credentials (SSO locally; Snowflake session under SiS); `.env` is gitignored/untracked and holds non-secret identifiers. Cross-ref Data Protection (secret hygiene; secret-scanning follow-up).

**Question:** Validate all data transferred over interfaces (type, length, format).
**Status:** Applicable
**Comment:** Partial: typed dataclasses, `dqr_validation` compatibility checks, `_canonicalize_id`; gap = no length/pattern bounds on free-text inputs. Cross-ref Input Validation.

**Question:** Use static code analyzers like Erebor to test for vulnerabilities.
**Status:** Applicable
**Comment:** **Partly addressed:** CI now runs **report-only SAST (bandit)** (`.github/workflows/security.yml`). **Residual:** the enterprise **Erebor** SAST still needs wiring via the org pipeline. Follow-up: onboard Erebor. Cross-ref Architecture (secure SDLC).

**Question:** Test web interfaces for XSS, SQLi, and CSRF using tools like Heimdall.
**Status:** Applicable
**Comment:** **Gap — directly named:** no Heimdall/DAST run yet (DAST needs a deployed endpoint, which doesn't exist until the SiS app is created). In-app mitigations exist (XSS → `html.escape`; SQLi → parameterized queries; CSRF → Streamlit XSRF default + Snowflake-served under SiS). Follow-up: run Heimdall against the deployed SiS endpoint once deployed. Cross-ref Input Validation + Configuration.

**Question:** Use patched libraries and third-party components; tools like Nexus.
**Status:** Applicable
**Comment:** **Partly addressed:** CI now runs **report-only SCA (pip-audit)**; deps were refreshed (incl. `urllib3` 1.26→2.x) and pip-audit reports no known vulnerabilities; production deps are declared in **`environment.yml`**. **Residual:** the authoritative scan must run via **Nexus/JFrog Xray against the Anaconda set**. Follow-up: onboard `environment.yml` to Nexus/Xray. Cross-ref Configuration (Dependency) + Architecture.

---

## Network Connections requirements

**Question:** Authenticate every incoming connection.
**Status:** Applicable
**Comment:** Under SiS every connection is an authenticated Snowflake session (Snowsight login); locally it is localhost. Platform-delegated. Cross-ref Authentication.

**Question:** Use SPF, DKIM, DMARC for end-user communications.
**Status:** Not Applicable
**Comment:** The app sends no email and has no email channel.

**Question:** Use trusted TLS certificates; reject untrusted certificates.
**Status:** Applicable
**Comment:** The Snowflake connector validates TLS by default and the app never disables it (no `insecure_mode`). Cross-ref Communications.

**Question:** Never exchange credentials in clear text; provide strong encryption (AES-256).
**Status:** Applicable
**Comment:** The app exchanges no credentials itself (SSO/session); all data-in-transit is TLS. Cross-ref Communications + Data Protection.

**Question:** Fully encrypt user sessions with HTTPS and HSTS.
**Status:** Applicable
**Comment:** Platform-delegated: under SiS the UI is served by Snowsight over HTTPS; HSTS is a Snowflake-serving-layer header. The app cannot set it. Follow-up: verify at the deployed endpoint (Heimdall/SSG). Cross-ref Configuration (HTTP headers).

**Question:** Disable old SSL/TLS versions; prefer the latest TLS.
**Status:** Applicable
**Comment:** TLS version/cipher selection is owned by the Snowflake connector / Snowflake serving layer (modern TLS); the app does not downgrade. Platform-delegated; verify at endpoint.

**Question:** Activate only necessary interfaces/services; open only required ports.
**Status:** Applicable
**Comment:** The app opens no ports of its own and makes a single outbound connection (Snowflake); under SiS, network exposure is Snowflake-managed. Cross-ref Configuration / Containers (network minimization).

---

## Data Protection requirements

**Question:** Do not store personal/sensitive/credential data in plain text.
**Status:** Applicable
**Comment:** The app persists nothing and stores no credentials in plaintext (SSO). Residual: user-initiated CSV/JSON downloads are plaintext (user-controlled). Cross-ref Data Protection theme.

**Question:** Follow privacy-by-design; process personal data lawfully with consent.
**Status:** Applicable
**Comment:** Organizational/assumption: processes corporate data under corporate policy; no consumer PII collection. Follow-up: document data classification/handling. Cross-ref Data Protection.

**Question:** Provide capability to erase all personal/sensitive/credential data on disposal.
**Status:** Not Applicable
**Comment:** No device disposal and no app-persisted personal/credential data (session_state cleared on restart; source data lifecycle is Snowflake's).

**Question:** Encrypt regulated private data at rest (PII/GDPR).
**Status:** Applicable
**Comment:** Under SiS, Snowflake encrypts at rest by default; residual gap = plaintext exports. Classification pending. Cross-ref Data Protection.

**Question:** Ensure only authorized personnel access users' personal data.
**Status:** Applicable
**Comment:** Enforced by Snowflake RBAC (the app's role + USAGE grants). Cross-ref Access Control.

---

## Credential Management requirements

**Question:** Implement 2-factor authentication for accessing sensitive data.
**Status:** Applicable
**Comment:** Delegated to Snowflake SSO/IdP, which supports MFA. The app implements no auth of its own. Cross-ref Authentication.

**Question:** Use hardware secure storage for critical sensitive data. — **Not Applicable** — no device/hardware; the app stores no secrets.
**Question:** Store credentials/keys in SAM/TPM/HSM/trusted key store. — **Not Applicable** — the app manages no credentials/keys (SSO/session). Cross-ref Cryptographic Architecture (N/A).
**Question:** Keep device IDs and authentication keys secure post-deployment. — **Not Applicable** — no device IDs/keys.
**Question:** Good password management (complex passwords, secure transmission). — **Not Applicable** — the app has no passwords (SSO).
**Question:** Unique certificates per device; manage/revoke. — **Not Applicable** — no devices/certificates.
**Question:** Factory reset fully removes all user data/credentials. — **Not Applicable** — no device.

**Question:** Use a secrets management solution (keyvault, secret manager).
**Status:** Applicable
**Comment:** The app uses no app-managed secrets; the one production secret — the GitHub PAT for the SiS Git integration — should be stored as a **Snowflake SECRET object**, not in the repo. Cross-ref SiS migration notes + Data Protection.

---

## Device Secure Boot requirements

*All Not Applicable — there is no device, bootloader, or boot process.*

**Question:** Each boot stage completes before proceeding. — **Not Applicable** — no boot process.
**Question:** Hardware tamper-resistant capabilities (SAM/TPM) for boot. — **Not Applicable** — no hardware.
**Question:** Handle boot failures gracefully. — **Not Applicable** — no boot.
**Question:** Verify expected hardware at each boot stage. — **Not Applicable** — no hardware.
**Question:** Always use ROM-based secure boot with multi-stage bootloader. — **Not Applicable** — no bootloader.

---

## Encryption requirements

**Question:** Remove weaker algorithm options to prevent downgrade attacks.
**Status:** Applicable
**Comment:** TLS cipher/version selection is owned by the Snowflake connector / platform (modern suites); the app implements no negotiable crypto. Platform-delegated.

**Question:** Avoid insecure block/padding/small-block ciphers and weak hashing. — **Not Applicable** — the app implements no cryptography of its own (no hashing/encryption in app code). TLS is platform-provided.
**Question:** Ensure cryptographic operations are constant-time. — **Not Applicable** — no app-implemented crypto.

**Question:** Store encryption keys in secure modules (SAM/TPM/HSM/key store). — **Not Applicable** — the app manages no keys.

**Question:** Avoid insecure protocols like FTP and Telnet.
**Status:** Applicable
**Comment:** Satisfied: the app uses only the TLS-protected Snowflake connection; no FTP/Telnet/cleartext protocols. Affirm.

**Question:** Use industry-standard cipher suites, strongest algorithms, latest TLS.
**Status:** Applicable
**Comment:** Provided by the Snowflake connector/platform TLS stack; the app does not weaken it. Platform-delegated; verify at endpoint.

**Question:** Apply encryption appropriate to the data classification.
**Status:** Applicable
**Comment:** Under SiS, Snowflake encryption at rest/in transit applies; the open item is formal data classification. Cross-ref Data Protection.

**Question:** Ensure cryptographic components can be reconfigured/upgraded/swapped. — **Not Applicable** — the app has no crypto components; the TLS stack is upgraded via the connector/platform dependency.

---

## Secure Operating System requirements

*All Not Applicable — the app manages no operating system; under SiS the OS/runtime is Snowflake-managed (encrypted storage, minimal components, patching, least-privilege all platform-owned).*

**Question:** Implement an encrypted file system. — **Not Applicable** — Snowflake-managed storage (encrypted by platform).
**Question:** Include only necessary OS components. — **Not Applicable** — Snowflake-managed runtime.
**Question:** Assign minimum access rights to files/directories. — **Not Applicable** — no app-managed filesystem.
**Question:** Securely boot the OS and keep components updated. — **Not Applicable** — Snowflake-managed.
**Question:** Disable services; restrict write permissions to the root filesystem. — **Not Applicable** — Snowflake-managed; the app writes no files.

---

## Securing Software Updates requirements

*Predominantly Not Applicable — there is no device firmware/OTA update mechanism. Production "updates" mean redeploying the app from Git to SiS; a few items have a software-deploy analog and are marked Applicable with cross-references.*

**Question:** Verify digital signatures/certificates before updating. — **Not Applicable** — no update package; integrity analog is Git branch protection / (optional) signed commits (cross-ref Architecture).
**Question:** Fail-safe mechanism for safe state during update failures. — **Not Applicable** — no device update; a bad SiS deploy is recoverable by redeploying a prior Git ref.
**Question:** Identify and manage all sensitive data created/processed by the application.
**Status:** Applicable
**Comment:** Applies generally; the data-classification/inventory follow-up is tracked in Data Protection (no device-update context).
**Question:** Encrypt update packages to prevent reverse engineering. — **Not Applicable** — no update package (source is in Git).
**Question:** Cryptographically validate integrity/authenticity of update packages. — **Not Applicable** — no update package; analog = Git integrity + branch protection.
**Question:** Encrypt sensitive information using approved algorithms (confidentiality/integrity).
**Status:** Applicable
**Comment:** TLS in transit + Snowflake at-rest encryption under SiS; no app-implemented crypto. Cross-ref Data Protection / Communications.
**Question:** Automatically resolve/install dependencies during updates; safe state if unresolved. — **Not Applicable** — no device update; analog = SiS resolves Anaconda deps from `environment.yml` at deploy (now present in the repo).
**Question:** Classify and delete old/out-of-date sensitive personal information automatically. — **Not Applicable** — the app stores no PII; retention is Snowflake's.
**Question:** Implement anti-rollback to prevent reverting to vulnerable versions. — **Not Applicable** — no firmware versioning; Git history governs versions.
**Question:** Assess production software images to remove debug/symbolic information.
**Status:** Applicable
**Comment:** Analog applies: remove dev artifacts/debug from the deployed source. Cross-ref Configuration.
**Question:** Provide clear language on data collection/use; obtain opt-in consent. — **Applicable** — organizational/assumption (corporate data; document handling). Cross-ref Data Protection.
**Question:** Identify the software update mechanism in the DSLA. — **Not Applicable** — no device/DSLA.
**Question:** Audit access to sensitive data without logging the data itself.
**Status:** Applicable
**Comment:** Snowflake Access/Query History records access (not data values); the app logs identifiers, not row data. Cross-ref Error Handling and Logging.
**Question:** Overwrite sensitive information in memory when no longer needed. — **Not Applicable** — not reliably achievable in Python (GC); session caches are cleared on restart. Cross-ref Data Protection (in-memory note).
**Question:** Protect against TOCTOU between validation and installation. — **Not Applicable** — no install step; the SiS Git integration deploys a specific ref.
**Question:** Clearly identify update support timespan/frequency in the DSLA. — **Not Applicable** — no device/DSLA.

---

## Logging requirements

**Question:** Set max log file size, rotate logs, store in a separate partition. — **Not Applicable** — the app manages no log files (stdlib logging to stderr); under SiS, event-table storage is Snowflake-managed.

**Question:** Restrict access rights to log files to the minimum necessary.
**Status:** Applicable
**Comment:** Under SiS, log/audit data (event tables, Query/Login History) is RBAC-protected by Snowflake. Cross-ref Error Handling and Logging.

**Question:** Ensure logged data complies with data protection regulations.
**Status:** Applicable
**Comment:** The app logs identifiers/rule-ids, not row data; verify `exc_info`/`{e}` paths don't surface data. Cross-ref Error Handling and Logging.

**Question:** Implement log levels (lightweight + detailed when needed).
**Status:** Applicable
**Comment:** Stdlib logging levels are used consistently (`logger.warning`, etc.). Cross-ref Error Handling and Logging.

**Question:** Send log data over a secure channel if sensitive/tamper-protected.
**Status:** Applicable
**Comment:** Under SiS, telemetry to event tables stays within the Snowflake boundary. Cross-ref Error Handling and Logging.

**Question:** Run the logging function in a separate OS process. — **Not Applicable** — no such architecture; logging is in-process stdlib / platform event tables.

**Question:** Synchronize to an accurate time source for correlating timestamps.
**Status:** Applicable
**Comment:** Gap: app/log timestamps are local-time (`datetime.now()`), not UTC. Cross-ref Error Handling and Logging (UTC follow-up). Snowflake platform logs are UTC.

**Question:** For limited capacity, log start-up/shutdown, login/access attempts, unexpected events.
**Status:** Applicable
**Comment:** The app logs unexpected/processing events; login/access is recorded by Snowflake (Login/Access History). Cross-ref Authentication + Error Handling and Logging.
