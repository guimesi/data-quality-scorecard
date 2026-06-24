## Business Logic Security Requirements

**Sufficient anti-automation controls to detect/mitigate data exfiltration, excessive requests, and DoS.**
Status: Applicable
Comment: Gap: no app-level anti-automation/rate limiting. Mitigated by SSO-gated read-only access with Snowflake warehouse limits. Residual risk: an authorized user can export all columns (CSV), bounded by their grants. Follow-up: Snowflake resource monitors; column-minimized exports.

**Enforce per-user limits on specific business actions/transactions to prevent abuse.**
Status: Applicable
Comment: No state-changing transactions to meter — actions are read-only and idempotent. Any throttling would be at the Snowflake warehouse tier. Follow-up: minimal; revisit if a state-changing feature is added.

**Monitor for unusual events/activities (out-of-order actions, atypical behavior).**
Status: Applicable
Comment: Out-of-order actions are structurally prevented by the gates and step-visibility predicates, but the app does no anomaly detection. Follow-up: define "unusual" and rely on Snowflake Query/Access History.

**Configurable alerting for detecting automated attacks or unusual activity.**
Status: Applicable
Comment: Gap: no app-level alerting. Alerting would be built on Snowflake event tables/Access History. Follow-up: configure Snowflake-side alerting if required by policy.

**Avoid TOCTOU issues and other race conditions for sensitive operations.**
Status: Not Applicable
Comment: No sensitive/state-changing operations exist, and Streamlit executes a session's script sequentially per rerun, so no concurrent flow is subject to TOCTOU. Shared module-level state is non-security and single-session.

**Ensure all steps are processed within realistic human timeframes (prevent too-fast submission).**
Status: Not Applicable
Comment: The workflow has no transactional submission to rate-check for bot-speed; it is a read-only, idempotent analysis flow. Human-timeframe checks are anti-fraud controls for transactional systems and do not apply.

**Process business-logic flows in sequential order per user, without skipping steps.**
Status: Applicable
Comment: Satisfied: step ordering is enforced via the mode/domain gates and STEP_VISIBILITY_PREDICATES, so a session cannot render a later step without its prerequisites. This is functional-integrity sequencing rather than a security boundary, but it prevents out-of-order state.

**Implement business-logic limits/validations based on threat modeling.**
Status: Applicable
Comment: This assessment is the threat-modeling exercise driving such limits. In-app validations exist (dqr_validation.py rule/param compatibility, required-CDE derivation, weight normalization, CustomRuleNotEvaluated). Follow-ups: least-privilege role, SCA/SAST/DAST, export minimization.
