## Malicious Code Search Requirements

**Verify source code and third-party libraries do not contain Easter eggs or unwanted functionality.**
Status: Applicable
Comment: Source reviewed — no Easter eggs/unwanted functionality, no dynamic execution. Deps scanned by report-only SCA (pip-audit) in CI, clean as of refresh. Residual: authoritative scan via Nexus/JFrog Xray on `environment.yml`.

**Search for time bombs by examining date/time-related functions.**
Status: Applicable
Comment: Date/time usage is legitimate and documented — date-relative DQRs and snapshots compare against `datetime.now()`; mock data anchors to `_MOCK_NOW`. No time bombs or date-gated hidden behaviour.

**Ensure no unauthorized phone-home / data-collection capabilities; obtain permission if present.**
Status: Applicable
Comment: Only intentional outbound is the Snowflake connection; no HTTP-fetching libraries or analytics in app code. Gap: Streamlit's default usage-stats telemetry (`browser.gatherUsageStats`) is not disabled.

**Ensure no backdoors (hard-coded accounts, code obfuscation, rootkits).**
Status: Applicable
Comment: No hard-coded accounts/credentials in tracked source, no code obfuscation (readable Python), and no rootkit/privilege capability (no native code).

**Check for malicious code such as salami attacks, logic bypasses, or logic bombs.**
Status: Applicable
Comment: No logic bombs or hidden bypasses. Scoring/DQR logic is deterministic and test-covered; rules with missing dependencies raise `CustomRuleNotEvaluated` rather than silently bypassing checks.

**Avoid excessive permissions to privacy features (contacts, camera, microphone, location).**
Status: Not Applicable
Comment: Web/Streamlit app with no device-permission model; it requests no access to contacts/camera/microphone/location.

## Code Integrity Controls Requirements

**Use a code-analysis tool that detects potentially malicious code, unsafe file operations, and network connections.**
Status: Applicable
Comment: CI runs report-only SAST (bandit) detecting malicious patterns, unsafe file ops, and risky calls; in-app posture is favourable. Residual: enterprise SAST (Erebor) still needs wiring via the org pipeline.

## Deployed Application Integrity Controls

**Auto-updates obtained over secure channels and digitally signed; validate signatures before installation.**
Status: Applicable
Comment: No client-side auto-update mechanism; production updates are deployments via the Snowflake Git integration over HTTPS. Integrity rests on branch protection. Follow-up: enforce branch protection on the deploy branch.

**Employ integrity protections (code signing / SRI); avoid loading code from untrusted sources.**
Status: Applicable
Comment: Loads no code from untrusted sources — no dynamic/remote imports, no `eval`/`exec`, no external CDN assets (SRI not needed). Code signing is N/A; Git integrity + branch protection is the equivalent control.

**Protect against sub-domain takeovers (regularly check DNS names for expiry/changes).**
Status: Not Applicable
Comment: The app manages no DNS records or custom domains; under SiS it is served on a Snowflake-owned hostname, and DNS lifecycle is Snowflake's responsibility.

## Network Communication Requirements

**Use a certificate store or pin the endpoint certificate/public key; reject different certificates/keys.**
Status: Applicable
Comment: The Snowflake connector validates the endpoint certificate against the CA trust store (with OCSP) and the app never disables it. Certificate/public-key pinning is not implemented — a deliberate, acceptable choice for the managed connector.

**Avoid relying on a single insecure communication channel for critical operations.**
Status: Applicable
Comment: There is a single external channel (Snowflake), but it is TLS-secured — not insecure. No critical operation traverses an unencrypted channel.

**Encrypt data on the network using TLS; ensure consistent use of secure channels.**
Status: Applicable
Comment: All data-in-transit to Snowflake uses TLS; under SiS the user-to-app channel is Snowsight HTTPS and data access is in-platform. Consistent secure-channel use.

**Verify the X.509 certificate of the remote endpoint; accept only trusted-CA-signed certificates.**
Status: Applicable
Comment: The Snowflake connector verifies the remote X.509 certificate chain against trusted CAs by default; the app does not weaken this.

**Depend on up-to-date connectivity and security libraries.**
Status: Applicable
Comment: Connectivity/security libraries were refreshed (`urllib3`, `cryptography`, `requests`, `pyjwt`) and are vulnerability-checked by report-only SCA (pip-audit), clean as of refresh. Residual: authoritative SCA via JFrog Xray on the Anaconda set plus update alerting.

**Align TLS settings with current best practices (or as close as mobile OS support allows).**
Status: Applicable
Comment: TLS version/cipher selection is owned by the Snowflake connector/serving layer (modern suites); the app does not downgrade or override them. Platform-delegated; verify at the deployed endpoint.
