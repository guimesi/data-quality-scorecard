## Mobile app code Quality Requirements

**Identify all third-party components and regularly check them for known vulnerabilities.**
Status: Applicable
Comment: Dependency inventory exists for both runtimes and CI runs report-only SCA (pip-audit), which reported no known vulnerabilities as of the refresh (point-in-time). Authoritative production scan must run via Nexus/JFrog Xray against environment.yml.

**Catch and handle possible exceptions gracefully to maintain stability and security.**
Status: Applicable
Comment: Broad try/except with an enforced "no silent except" rule and graceful degradation (failed builds excluded, missing rule deps raise CustomRuleNotEvaluated). Residual gap: raw-exception interpolation and default Streamlit tracebacks.

**Implement error-handling logic that denies access by default.**
Status: Applicable
Comment: The app fails safe in control flow: incomplete sessions reroute, unknown steps render a generic error, and missing inputs surface rather than fabricate results. Access deny-by-default is enforced at the Snowflake RBAC layer.

**In unmanaged code, ensure memory is allocated, freed, and used securely.**
Status: Not Applicable
Comment: The application is pure, memory-managed Python with no unmanaged code or manual memory management. C-extension dependencies are prebuilt third-party packages whose integrity is an SCA concern.

**Eliminate debugging/developer-assistance code (test code, backdoors, hidden settings); no verbose error/debug logging.**
Status: Applicable
Comment: No backdoors or hidden settings (no eval/exec, source reviewable in Git). Gaps: Streamlit traceback display not disabled, one path interpolates the raw exception, and dev artifacts remain in deployed source. Follow-up: disable error-detail, use generic text, scope/remove dev artifacts.

**Utilize free toolchain security features (bytecode minification, stack protection, PIE, automatic reference counting).**
Status: Not Applicable
Comment: These are native-compilation/mobile-toolchain features. The app is interpreted Python with no compilation or link step, so there are no such build flags to enable.

**Build the app in release mode with production settings, ensuring it is non-debuggable.**
Status: Applicable
Comment: No compiled "release mode" exists, but the equivalent production-hardening is not configured (no Streamlit config disabling dev features or error-detail display). Follow-up: add production Streamlit config with error details and dev/usage-stats off.

## Low code Custom Coding requirements

**When using custom coding and/or connectors, the use of SAST and DAST tools is a must if applicable.**
Status: Applicable
Comment: This fully custom-coded Python app now has report-only SAST (bandit) in CI with no High/Medium issues, plus in-app mitigations (parameterized SQL, html.escape, CSV sanitization). Residual gaps: wire enterprise SAST (Erebor) and run DAST (Heimdall) against the deployed SiS endpoint.
