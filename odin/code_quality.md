# Code Quality — Odin Threat Modeling Assessment

**Application:** `data-quality-scorecard`

**Framing context:** This section is titled "Mobile app code Quality", but
`data-quality-scorecard` is a **Python/Streamlit web app** (no mobile app, no native build, no
unmanaged code). The items are assessed on their **general code-quality** merits: those that
map to a managed-language web app are **Applicable** (and cross-referenced to the dedicated
themes to avoid double-claiming); the **mobile/native-toolchain/unmanaged-memory** items are
**Not Applicable**. Relevant facts: pure-Python (memory-managed); pervasive exception handling
with an enforced "no silent except" rule; CI runs `ruff` + `pytest` (~1,242 tests, ~97%
coverage) plus a report-only **security workflow** (SAST bandit + SCA pip-audit + secret scan);
DAST (Heimdall) and the enterprise scanners are still to wire; deps were refreshed (pip-audit clean);
production is **Streamlit in Snowflake** (sandboxed, source pulled from Git).

---

## Mobile app code Quality Requirements

**Question:** Identify all third-party components and regularly check them for known vulnerabilities.
**Status:** Applicable
**Comment:** Inventory exists for both runtimes (`requirements.txt` + pinned `requirements.lock` for local/CI; **`environment.yml`** for SiS/Anaconda), and CI now runs **report-only SCA (pip-audit)**. Dependencies were **refreshed to clear known advisories** (incl. the previously-flagged `urllib3` 1.26→2.x); pip-audit reports **no known vulnerabilities**. Residual: the authoritative production scan must run via **Nexus/JFrog Xray against `environment.yml`** (Anaconda). Cross-ref Configuration (Dependency) / Architecture / IoT (Nexus).

**Question:** Catch and handle possible exceptions gracefully to maintain stability and security.
**Status:** Applicable
**Comment:** In place: broad `try/except` with the enforced "Silent except is forbidden" rule (every handler logs or has a tight reason); graceful degradation — failed data-product builds and scorecards are logged and excluded, missing rule dependencies raise `CustomRuleNotEvaluated` (surfaced as "Not evaluated", never a silent pass). Residual gap: raw-exception interpolation + default Streamlit tracebacks. Cross-ref Error Handling and Logging.

**Question:** Implement error-handling logic that denies access by default.
**Status:** Applicable
**Comment:** The app fails safe in its control flow: the `app.py` mode/domain gates reroute incomplete sessions rather than rendering against unknown state; an unknown step renders a generic error; missing inputs raise/surface rather than fabricating results. **Access** deny-by-default is enforced at the Snowflake RBAC layer (the app has no access-control logic of its own and reads only what the role permits). Cross-ref Access Control / Architecture.

**Question:** In unmanaged code, ensure memory is allocated, freed, and used securely.
**Status:** Not Applicable
**Comment:** The application is pure, memory-managed Python with no unmanaged code or manual memory management. (C-extension dependencies are prebuilt third-party packages; their integrity is an SCA concern, above.) Cross-ref Input Validation (Memory/Unmanaged Code — N/A).

**Question:** Eliminate debugging/developer-assistance code (test code, backdoors, hidden settings); no verbose error/debug logging.
**Status:** Applicable
**Comment:** No backdoors or hidden settings exist (no `eval`/`exec`/dynamic execution; source is reviewable in Git). **Gaps:** Streamlit's default exception-detail/traceback display is not disabled (no `.streamlit/config.toml`), one path interpolates the raw exception (`st.error(f"...{e}")`), and dev artifacts (the Snowflake-connecting `notebooks/data_product_preview.ipynb`, `tests/`) are present in the Git-deployed source. Follow-up: disable Streamlit error-detail in production, replace `{e}` with generic text, and scope/remove dev artifacts from the deployed app. Cross-ref Configuration (debug mode / remove unnecessary files) + Error Handling.

**Question:** Utilize free toolchain security features (bytecode minification, stack protection, PIE, automatic reference counting).
**Status:** Not Applicable
**Comment:** These are native-compilation/mobile-toolchain features. The app is interpreted Python with no compilation/link step (and runs in the Snowflake-managed SiS runtime), so there are no such build flags to enable.

**Question:** Build the app in release mode with production settings, ensuring it is non-debuggable.
**Status:** Applicable
**Comment:** There is no compiled "release mode", but the equivalent production-hardening is **not configured**: no `.streamlit/config.toml` disabling dev features (`runOnSave`, developer tools) or error-detail display. Under SiS the deployment is not a dev session, but error-detail display should be explicitly turned off. Follow-up: add production Streamlit config (`client.showErrorDetails` off, no dev/usage-stats). Cross-ref Configuration (disable debug modes).

---

## Low code Custom Coding requirements

**Question:** When using custom coding and/or connectors, the use of SAST and DAST tools is a must if applicable.
**Status:** Applicable
**Comment:** This is a **fully custom-coded** Python application (with a custom Snowflake data connector), so SAST and DAST are squarely applicable. **SAST is now in CI** (report-only bandit, `.github/workflows/security.yml`; known-safe SQL findings annotated with justified `# nosec`). **Residual gaps:** the enterprise **SAST (Erebor)** still needs wiring, and **DAST (Heimdall)** must run against the deployed SiS endpoint (no DAST in CI). In-app mitigations exist (parameterized SQL, `html.escape`, CSV sanitization, no dynamic execution). Follow-up: onboard Erebor + run Heimdall against the deployed app. Cross-ref IoT Secure Coding / Configuration / Architecture (secure SDLC).
