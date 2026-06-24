# Business Logic — Odin Threat Modeling Assessment

**Application:** `data-quality-scorecard`

**Framing context:** The application's "business logic flow" is the **read-only scorecard-building
workflow** (mode → domain → systems → data-product review → CDEs → DQR assignment → weights →
dashboard → ML Lab). Key facts: it performs **no state-changing transactions** (read-only Snowflake
`SELECT`s; outputs are in-memory scorecards + user-initiated downloads); it runs **sequentially per
Streamlit session** (single authenticated user); and it **enforces step ordering** via the two
gates in `app.py` (mode gate, domain gate) and `STEP_VISIBILITY_PREDICATES` / navigation
(ARCHITECTURE: "Two gates in app.py, in order"). There is **no app-level anti-automation, rate
limiting, monitoring, or alerting** — those are platform (Snowflake) concerns under SiS.

---

## Business Logic Security Requirements

**Question:** Sufficient anti-automation controls to detect/mitigate data exfiltration, excessive requests, and DoS.
**Status:** Applicable
**Comment:** **Gap:** the app implements no anti-automation / rate limiting. Mitigating factors: access is **SSO-gated** (only authenticated Snowflake users), the app is **read-only**, and resource/throughput limits are enforced by the **Snowflake warehouse** under SiS. Residual exfiltration consideration: an authorized user can export all columns of a data product (CSV) — bounded by their Snowflake grants (cross-ref Data Protection "excessive data exposure"). Follow-up: rely on Snowflake resource monitors/Query History; consider column-minimized exports.

**Question:** Enforce per-user limits on specific business actions/transactions to prevent abuse.
**Status:** Applicable
**Comment:** The app has **no state-changing transactions** to meter — actions (build scorecard, export) are read-only and idempotent, so per-user transaction limits have low relevance. Under multi-user SiS, all viewers share the owner's-rights role, so any throttling would be at the Snowflake warehouse tier, not per-app-user. Follow-up: minimal; revisit if a state-changing feature is added.

**Question:** Monitor for unusual events/activities (out-of-order actions, atypical behavior).
**Status:** Applicable
**Comment:** Out-of-order actions are **structurally prevented** (the gates + step-visibility predicates stop a user reaching a later step without its prerequisites — e.g. no dashboard without built data products). However, the app performs **no anomaly monitoring/detection**. Gap: monitoring is delegated to **Snowflake Query/Access History** at the platform tier. Follow-up: define what "unusual" looks like and rely on Snowflake auditing.

**Question:** Configurable alerting for detecting automated attacks or unusual activity.
**Status:** Applicable
**Comment:** **Gap:** no app-level alerting exists. Under SiS, alerting would be built on Snowflake event tables / Access History (platform), not in the app. Follow-up: configure Snowflake-side alerting if required by policy. Cross-ref Error Handling and Logging.

**Question:** Avoid TOCTOU issues and other race conditions for sensitive operations.
**Status:** Not Applicable
**Comment:** There are **no sensitive/state-changing operations**, and Streamlit executes a session's script **sequentially** per rerun, so there is no concurrent sensitive flow subject to TOCTOU. Module-level shared state (the cached Snowflake client, mock RNG) is non-security and single-session. Cross-ref Business Logic Architectural (also N/A).

**Question:** Ensure all steps are processed within realistic human timeframes (prevent too-fast submission).
**Status:** Not Applicable
**Comment:** The workflow has **no transactional submission** to rate-check for bot-speed; it is a read-only, idempotent analysis flow. Human-timeframe / too-fast-submission checks are anti-fraud controls for transactional systems and do not apply here.

**Question:** Process business-logic flows in sequential order per user, without skipping steps.
**Status:** Applicable
**Comment:** Satisfied: step ordering is enforced via `app.py`'s mode/domain gates and `STEP_VISIBILITY_PREDICATES` / navigation — a session cannot render a later step without its prerequisites (e.g. data-product build precedes the dashboard; domain must be set for domain-shaped steps). This is functional-integrity sequencing (single-user workflow) rather than a security boundary, but it does prevent out-of-order state. Cross-ref ARCHITECTURE ("Two gates in app.py").

**Question:** Implement business-logic limits/validations based on threat modeling.
**Status:** Applicable
**Comment:** This Odin assessment is the threat-modeling exercise driving such limits. In-app validations already exist: `src/dqr_validation.py` (rule/param compatibility), required-CDE derivation, weight distribution/normalization, and `CustomRuleNotEvaluated` for missing dependencies. Follow-ups identified across themes (least-privilege role, SCA/SAST/DAST, export minimization) are the threat-model-driven additions. Cross-ref Input Validation / Access Control.
