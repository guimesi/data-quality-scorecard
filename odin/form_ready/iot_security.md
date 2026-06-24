## Physical Security requirements

**Require authentication for debug interfaces or ports.**
Status: Not Applicable
Comment: No hardware debug ports.

**Make device circuitry tamper-resistant (epoxy/resin).**
Status: Not Applicable
Comment: No physical device.

**Ensure no backdoors or hidden entry points.**
Status: Applicable
Comment: The principle applies in code: no eval/exec/backdoor and source is reviewable in Git.

**Incorporate hardware security features (security chips/coprocessors).**
Status: Not Applicable
Comment: No hardware.

**Ensure device can recover after a power outage.**
Status: Not Applicable
Comment: No device; SiS state is platform-managed.

**Use a unique physical identifier for device distinction.**
Status: Not Applicable
Comment: No device.

**Disable unnecessary physical interfaces or ports.**
Status: Not Applicable
Comment: No physical interfaces.

**Restrict direct access to administrative capabilities.**
Status: Applicable
Comment: Maps to Snowflake RBAC / least-privilege role plus USAGE grants, with no in-app admin surface.

**Validate device root-of-trust boot process and monitor for anomalies.**
Status: Not Applicable
Comment: No device boot.

## Secure Coding Guidelines requirements

**Avoid deploying debug versions of code; exclude unnecessary files.**
Status: Applicable
Comment: Gap: no production hardening config and dev artifacts (notebook, tests, docs) are in the Git-deployed source.

**Prevent injection by separating untrusted data from commands/queries.**
Status: Applicable
Comment: In place: parameterized SQL, html.escape, and CSV formula sanitization.

**Cryptographically sign code; implement run-time protection and secure execution monitoring.**
Status: Not Applicable
Comment: No shipped binary to sign; run-time isolation is provided by the SiS sandbox.

**Sanitize input in web applications using URL or HTML encoding.**
Status: Applicable
Comment: In place: html.escape on data rendered via unsafe_allow_html plus Streamlit auto-escaping.

**Handle errors gracefully without revealing sensitive information.**
Status: Applicable
Comment: Partial; gap is raw-exception interpolation and Streamlit default tracebacks with no config disabling them.

**Do not hard-code credentials; store securely and ensure updateable.**
Status: Applicable
Comment: Satisfied: no hard-coded credentials and .env is gitignored holding only non-secret identifiers.

**Validate all data transferred over interfaces (type, length, format).**
Status: Applicable
Comment: Partial: typed dataclasses and compatibility checks exist; gap is no length/pattern bounds on free-text inputs.

**Use static code analyzers like Erebor to test for vulnerabilities.**
Status: Applicable
Comment: CI runs report-only SAST (bandit); residual is wiring the enterprise Erebor SAST via the org pipeline.

**Test web interfaces for XSS, SQLi, and CSRF using tools like Heimdall.**
Status: Applicable
Comment: Gap: no Heimdall/DAST run yet (needs a deployed endpoint); in-app XSS/SQLi/CSRF mitigations exist.

**Use patched libraries and third-party components; tools like Nexus.**
Status: Applicable
Comment: CI runs report-only SCA (pip-audit); residual is the authoritative Nexus/JFrog Xray scan against the Anaconda set.

## Network Connections requirements

**Authenticate every incoming connection.**
Status: Applicable
Comment: Under SiS every connection is an authenticated Snowflake session; locally it is localhost.

**Use SPF, DKIM, DMARC for end-user communications.**
Status: Not Applicable
Comment: The app sends no email and has no email channel.

**Use trusted TLS certificates; reject untrusted certificates.**
Status: Applicable
Comment: The Snowflake connector validates TLS by default and the app never disables it.

**Never exchange credentials in clear text; provide strong encryption (AES-256).**
Status: Applicable
Comment: The app exchanges no credentials itself and all data-in-transit is TLS.

**Fully encrypt user sessions with HTTPS and HSTS.**
Status: Applicable
Comment: Under SiS the UI is served by Snowsight over HTTPS; HSTS is a Snowflake serving-layer header to verify at endpoint.

**Disable old SSL/TLS versions; prefer the latest TLS.**
Status: Applicable
Comment: TLS version/cipher selection is owned by the Snowflake connector/serving layer; the app does not downgrade.

**Activate only necessary interfaces/services; open only required ports.**
Status: Applicable
Comment: The app opens no ports and makes a single outbound Snowflake connection; exposure is Snowflake-managed under SiS.

## Data Protection requirements

**Do not store personal/sensitive/credential data in plain text.**
Status: Applicable
Comment: The app persists nothing and stores no plaintext credentials; residual is user-initiated plaintext CSV/JSON downloads.

**Follow privacy-by-design; process personal data lawfully with consent.**
Status: Applicable
Comment: Processes corporate data under corporate policy with no consumer PII; follow-up is documenting data classification.

**Provide capability to erase all personal/sensitive/credential data on disposal.**
Status: Not Applicable
Comment: No device disposal and no app-persisted personal/credential data.

**Encrypt regulated private data at rest (PII/GDPR).**
Status: Applicable
Comment: Under SiS Snowflake encrypts at rest by default; residual gap is plaintext exports.

**Ensure only authorized personnel access users' personal data.**
Status: Applicable
Comment: Enforced by Snowflake RBAC (the app's role plus USAGE grants).

## Credential Management requirements

**Implement 2-factor authentication for accessing sensitive data.**
Status: Applicable
Comment: Delegated to Snowflake SSO/IdP, which supports MFA; the app implements no auth of its own.

**Use hardware secure storage for critical sensitive data.**
Status: Not Applicable
Comment: No device/hardware; the app stores no secrets.

**Store credentials/keys in SAM/TPM/HSM/trusted key store.**
Status: Not Applicable
Comment: The app manages no credentials/keys.

**Keep device IDs and authentication keys secure post-deployment.**
Status: Not Applicable
Comment: No device IDs/keys.

**Good password management (complex passwords, secure transmission).**
Status: Not Applicable
Comment: The app has no passwords (SSO).

**Unique certificates per device; manage/revoke.**
Status: Not Applicable
Comment: No devices/certificates.

**Factory reset fully removes all user data/credentials.**
Status: Not Applicable
Comment: No device.

**Use a secrets management solution (keyvault, secret manager).**
Status: Applicable
Comment: The one production secret, the GitHub PAT for SiS Git integration, should be a Snowflake SECRET object, not in the repo.

## Device Secure Boot requirements

**Each boot stage completes before proceeding.**
Status: Not Applicable
Comment: No boot process.

**Hardware tamper-resistant capabilities (SAM/TPM) for boot.**
Status: Not Applicable
Comment: No hardware.

**Handle boot failures gracefully.**
Status: Not Applicable
Comment: No boot.

**Verify expected hardware at each boot stage.**
Status: Not Applicable
Comment: No hardware.

**Always use ROM-based secure boot with multi-stage bootloader.**
Status: Not Applicable
Comment: No bootloader.

## Encryption requirements

**Remove weaker algorithm options to prevent downgrade attacks.**
Status: Applicable
Comment: TLS cipher/version selection is owned by the Snowflake connector/platform; the app implements no negotiable crypto.

**Avoid insecure block/padding/small-block ciphers and weak hashing.**
Status: Not Applicable
Comment: The app implements no cryptography of its own; TLS is platform-provided.

**Ensure cryptographic operations are constant-time.**
Status: Not Applicable
Comment: No app-implemented crypto.

**Store encryption keys in secure modules (SAM/TPM/HSM/key store).**
Status: Not Applicable
Comment: The app manages no keys.

**Avoid insecure protocols like FTP and Telnet.**
Status: Applicable
Comment: Satisfied: the app uses only the TLS-protected Snowflake connection with no FTP/Telnet/cleartext protocols.

**Use industry-standard cipher suites, strongest algorithms, latest TLS.**
Status: Applicable
Comment: Provided by the Snowflake connector/platform TLS stack; the app does not weaken it.

**Apply encryption appropriate to the data classification.**
Status: Applicable
Comment: Under SiS Snowflake encryption at rest/in transit applies; the open item is formal data classification.

**Ensure cryptographic components can be reconfigured/upgraded/swapped.**
Status: Not Applicable
Comment: The app has no crypto components; the TLS stack upgrades via the connector/platform dependency.

## Secure Operating System requirements

**Implement an encrypted file system.**
Status: Not Applicable
Comment: Snowflake-managed storage, encrypted by the platform.

**Include only necessary OS components.**
Status: Not Applicable
Comment: Snowflake-managed runtime.

**Assign minimum access rights to files/directories.**
Status: Not Applicable
Comment: No app-managed filesystem.

**Securely boot the OS and keep components updated.**
Status: Not Applicable
Comment: Snowflake-managed.

**Disable services; restrict write permissions to the root filesystem.**
Status: Not Applicable
Comment: Snowflake-managed; the app writes no files.

## Securing Software Updates requirements

**Verify digital signatures/certificates before updating.**
Status: Not Applicable
Comment: No update package; the integrity analog is Git branch protection / optional signed commits.

**Fail-safe mechanism for safe state during update failures.**
Status: Not Applicable
Comment: No device update; a bad SiS deploy is recoverable by redeploying a prior Git ref.

**Identify and manage all sensitive data created/processed by the application.**
Status: Applicable
Comment: Applies generally; the data-classification/inventory follow-up is tracked in Data Protection.

**Encrypt update packages to prevent reverse engineering.**
Status: Not Applicable
Comment: No update package; source is in Git.

**Cryptographically validate integrity/authenticity of update packages.**
Status: Not Applicable
Comment: No update package; the analog is Git integrity plus branch protection.

**Encrypt sensitive information using approved algorithms (confidentiality/integrity).**
Status: Applicable
Comment: TLS in transit plus Snowflake at-rest encryption under SiS; no app-implemented crypto.

**Automatically resolve/install dependencies during updates; safe state if unresolved.**
Status: Not Applicable
Comment: No device update; the analog is SiS resolving Anaconda deps from environment.yml at deploy.

**Classify and delete old/out-of-date sensitive personal information automatically.**
Status: Not Applicable
Comment: The app stores no PII; retention is Snowflake's.

**Implement anti-rollback to prevent reverting to vulnerable versions.**
Status: Not Applicable
Comment: No firmware versioning; Git history governs versions.

**Assess production software images to remove debug/symbolic information.**
Status: Applicable
Comment: Analog applies: remove dev artifacts/debug from the deployed source.

**Provide clear language on data collection/use; obtain opt-in consent.**
Status: Applicable
Comment: Organizational/assumption: corporate data, with handling to be documented.

**Identify the software update mechanism in the DSLA.**
Status: Not Applicable
Comment: No device/DSLA.

**Audit access to sensitive data without logging the data itself.**
Status: Applicable
Comment: Snowflake Access/Query History records access not data values; the app logs identifiers, not row data.

**Overwrite sensitive information in memory when no longer needed.**
Status: Not Applicable
Comment: Not reliably achievable in Python (GC); session caches are cleared on restart.

**Protect against TOCTOU between validation and installation.**
Status: Not Applicable
Comment: No install step; the SiS Git integration deploys a specific ref.

**Clearly identify update support timespan/frequency in the DSLA.**
Status: Not Applicable
Comment: No device/DSLA.

## Logging requirements

**Set max log file size, rotate logs, store in a separate partition.**
Status: Not Applicable
Comment: The app manages no log files; under SiS event-table storage is Snowflake-managed.

**Restrict access rights to log files to the minimum necessary.**
Status: Applicable
Comment: Under SiS log/audit data (event tables, Query/Login History) is RBAC-protected by Snowflake.

**Ensure logged data complies with data protection regulations.**
Status: Applicable
Comment: The app logs identifiers/rule-ids, not row data; verify exc_info/{e} paths don't surface data.

**Implement log levels (lightweight + detailed when needed).**
Status: Applicable
Comment: Stdlib logging levels are used consistently.

**Send log data over a secure channel if sensitive/tamper-protected.**
Status: Applicable
Comment: Under SiS telemetry to event tables stays within the Snowflake boundary.

**Run the logging function in a separate OS process.**
Status: Not Applicable
Comment: No such architecture; logging is in-process stdlib / platform event tables.

**Synchronize to an accurate time source for correlating timestamps.**
Status: Applicable
Comment: Gap: app/log timestamps are local-time, not UTC; Snowflake platform logs are UTC.

**For limited capacity, log start-up/shutdown, login/access attempts, unexpected events.**
Status: Applicable
Comment: The app logs unexpected/processing events; login/access is recorded by Snowflake.
