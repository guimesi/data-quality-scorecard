# Malicious Code — Odin Threat Modeling Assessment

**Application:** `data-quality-scorecard`

**Framing context:** The application source is **reviewable, un-obfuscated Python** in Git.
Established by review: **no `eval`/`exec`/`pickle`/dynamic import, no `subprocess`/`os.system`,
no hard-coded accounts/credentials/keys** in tracked source, and **no remote code loading**.
The only intentional network egress is the **Snowflake connection** (the app's purpose), over
TLS. Date/time functions are used legitimately (date-relative DQRs compare to `datetime.now()`;
mock data anchors to a captured `_MOCK_NOW`) — documented in ARCHITECTURE, not date-gated hidden
behaviour. Behaviour is locked down by ~1,250 unit tests.

> **Concrete phone-home note (still open):** there is **no `.streamlit/config.toml`**, so
> Streamlit's default **usage-stats telemetry** (`browser.gatherUsageStats`) is at its default —
> a potential unintended "phone home" in **local** runs. Under **SiS** the app runs in
> Snowflake's sandbox with **no arbitrary external egress**, so telemetry cannot leave the
> Snowflake boundary (and warehouse-runtime `config.toml` only honours `[theme]`, so the flag
> isn't app-settable there anyway). Follow-up: for local/non-SiS runs, disable
> `browser.gatherUsageStats`; confirm SiS egress behaviour at deploy time.

> **SiS production note:** the deploy path is the **Snowflake Git integration over HTTPS** (no
> client-side auto-update/binary); deploy-integrity comes from Git branch protection + the
> Snowflake-owned hostname, not app-level code signing.

---

## Malicious Code Search Requirements

**Question:** Verify source code and third-party libraries do not contain Easter eggs or unwanted functionality.
**Status:** Applicable
**Comment:** Application source reviewed — no Easter eggs/unwanted functionality, no dynamic execution. Third-party libraries are now scanned by **report-only SCA (pip-audit) in CI**, and deps were refreshed (pip-audit clean as of the refresh; **JFrog Xray on the PR is authoritative**). **Residual:** the authoritative scan against the production (Anaconda) set must run via **Nexus/JFrog Xray on `environment.yml`**. Cross-ref Configuration (Dependency) / Code Quality.

**Question:** Search for time bombs by examining date/time-related functions.
**Status:** Applicable
**Comment:** Affirmed: date/time usage is legitimate and documented — date-relative DQRs (Timeliness/Currency/SQ10) compare against the engine's `datetime.now()`; exports/snapshots stamp `datetime.now()`; mock data anchors to `_MOCK_NOW` captured at import (ARCHITECTURE "Mock data determinism"). **No time bombs / date-gated hidden behaviour.** (Tangential: these date-relative comparisons cause score drift over calendar time — a correctness note already recorded, not malicious.)

**Question:** Ensure no unauthorized phone-home / data-collection capabilities; obtain permission if present.
**Status:** Applicable
**Comment:** The app's only intentional outbound is the Snowflake data connection (its core function); there are no HTTP-fetching libraries or analytics calls in app code. **Gap:** Streamlit's default usage-stats telemetry is not disabled (no config.toml). Follow-up: disable `browser.gatherUsageStats` and confirm no telemetry leaves the Snowflake boundary under SiS.

**Question:** Ensure no backdoors (hard-coded accounts, code obfuscation, rootkits).
**Status:** Applicable
**Comment:** Affirmed: **no hard-coded accounts/credentials** in tracked source (verified via `git ls-files` + grep), **no code obfuscation** (readable Python), and no rootkit/privilege capability (no native code, runs in the SiS sandbox). Cross-ref Authentication / Data Protection (secret-scanning follow-up to keep it that way).

**Question:** Check for malicious code such as salami attacks, logic bypasses, or logic bombs.
**Status:** Applicable
**Comment:** No logic bombs/hidden bypasses found. The scoring/DQR logic is deterministic and covered by ~1,250 unit tests; rules with missing dependencies raise `CustomRuleNotEvaluated` (explicit "Not evaluated") rather than silently bypassing checks (ARCHITECTURE rule). Assurance rests on code review + the test suite; SAST would add automated coverage (below).

**Question:** Avoid excessive permissions to privacy features (contacts, camera, microphone, location).
**Status:** Not Applicable
**Comment:** Web/Streamlit app with no device-permission model; it requests no access to contacts/camera/microphone/location.

---

## Code Integrity Controls Requirements

**Question:** Use a code-analysis tool that detects potentially malicious code, unsafe file operations, and network connections.
**Status:** Applicable
**Comment:** CI now runs **report-only SAST (bandit)** that detects malicious patterns, unsafe file ops, and risky calls (`.github/workflows/security.yml`); in-app posture is favourable (no filesystem writes; single fixed network endpoint). **Residual:** the enterprise **SAST (Erebor)** still needs wiring via the org pipeline. Follow-up: onboard Erebor. Cross-ref Code Quality / Configuration / Architecture.

---

## Deployed Application Integrity Controls

**Question:** Auto-updates obtained over secure channels and digitally signed; validate signatures before installation.
**Status:** Applicable
**Comment:** The app has **no client-side auto-update mechanism**. Production "updates" are deployments via the **Snowflake Git integration over HTTPS**, which pulls a specific repo ref. Integrity analog: branch protection + restricted push + (optional) signed commits, since the repo is the deploy source. Follow-up: enforce branch protection on the deploy branch (cross-ref Architecture — source control / Malicious Software).

**Question:** Employ integrity protections (code signing / SRI); avoid loading code from untrusted sources.
**Status:** Applicable
**Comment:** Affirmed: the app **loads no code from untrusted sources** — no dynamic/remote imports, no `eval`/`exec`, and **no external CDN assets** (so SRI is not needed; Streamlit serves bundled assets). Dependencies come from trusted channels (PyPI locally / Snowflake Anaconda in SiS). Code signing of a Python/SiS app is not applicable; Git integrity + branch protection is the equivalent control. Cross-ref Configuration (SRI N/A) / Architecture.

**Question:** Protect against sub-domain takeovers (regularly check DNS names for expiry/changes).
**Status:** Not Applicable
**Comment:** The app manages no DNS records or custom domains. Under SiS it is served on a **Snowflake-owned hostname** (Snowsight / `*.snowflakecomputing.app`); DNS lifecycle is Snowflake's responsibility, not the app's.

---

## Network Communication Requirements

**Question:** Use a certificate store or pin the endpoint certificate/public key; reject different certificates/keys.
**Status:** Applicable
**Comment:** The Snowflake connector validates the endpoint certificate against the system/CA trust store (with OCSP), and the app never disables it (no `insecure_mode`). **Certificate/public-key pinning is not implemented** — a deliberate, acceptable choice for the managed Snowflake connector (CA validation + OCSP). Note as a conscious decision rather than a silent gap. Cross-ref Communications.

**Question:** Avoid relying on a single insecure communication channel for critical operations.
**Status:** Applicable
**Comment:** There is a single external channel (Snowflake), but it is **TLS-secured** — not insecure. No critical operation traverses an unencrypted channel. Affirm.

**Question:** Encrypt data on the network using TLS; ensure consistent use of secure channels.
**Status:** Applicable
**Comment:** All data-in-transit to Snowflake uses TLS; under SiS the user↔app channel is Snowsight HTTPS and data access is in-platform. Consistent secure-channel use. Cross-ref Communications.

**Question:** Verify the X.509 certificate of the remote endpoint; accept only trusted-CA-signed certificates.
**Status:** Applicable
**Comment:** Satisfied: the Snowflake connector verifies the remote X.509 certificate chain against trusted CAs by default; the app does not weaken this. Affirm.

**Question:** Depend on up-to-date connectivity and security libraries.
**Status:** Applicable
**Comment:** Connectivity/security libraries were **refreshed** (`urllib3` 1.26→2.x, `cryptography`/`requests`/`pyjwt` updated) and are now **vulnerability-checked by report-only SCA (pip-audit)** in CI — pip-audit reported no known vulnerabilities as of the refresh (point-in-time; **JFrog Xray on the PR is authoritative**); the production set is declared in **`environment.yml`**. **Residual:** authoritative SCA via JFrog Xray on the Anaconda set + dependency-update alerting. Cross-ref Configuration / Architecture.

**Question:** Align TLS settings with current best practices (or as close as mobile OS support allows).
**Status:** Applicable
**Comment:** TLS version/cipher selection is owned by the Snowflake connector / Snowflake serving layer (modern suites); the app does not downgrade or override them. Not a mobile app. Platform-delegated; verify at the deployed endpoint (SSG/Heimdall). Cross-ref Communications / Configuration.
