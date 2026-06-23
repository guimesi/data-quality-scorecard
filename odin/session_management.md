# Session Management — Odin Threat Modeling Assessment

**Application:** `data-quality-scorecard`

**Framing context — the app manages NO authentication session of its own.** It issues no
session tokens, sets no cookies, and has no login/logout flow. The authenticated session is
**Snowflake/Snowsight's** (SSO; `externalbrowser` locally, the Snowflake account login under
SiS). Streamlit `session_state` is **server-side application state** (workflow step, cached
data products/scorecards) — **not** an authentication credential and never sent to the client
as a token. The app is also **read-only** (no account modifications, no writes/DDL).

Consequences for this theme:
- Items about **app-issued/stored session tokens** are **Not Applicable** (the app issues none).
- Items about **session lifecycle (logout, timeout, invalidation, re-auth)** are
  **Applicable but platform-delegated** to Snowflake/IdP (with confirm-the-policy follow-ups).
- Items about **cookie attributes** are **Applicable but platform-delegated** — the app cannot
  set cookies; the Snowsight serving layer owns them, and SSG/Heimdall must verify them at the
  deployed endpoint (consistent with the HTTP-header handling in the Configuration theme).

> **SiS production note:** session establishment, expiration, idle timeout, and the
> browser session cookie are all owned by **Snowflake/Snowsight**, not the app.

---

## Defenses Against Session Management Exploits

**Question:** Ensure a valid login session or require re-authentication / secondary verification before sensitive transactions or account modifications.
**Status:** Applicable
**Comment:** A valid **Snowflake login session is required to reach the app at all** under SiS (platform-enforced). The app itself performs **no sensitive transactions or account modifications** — it is read-only (only `SELECT`; no writes/DDL; no account settings) — so there is no in-app sensitive operation that warrants step-up re-authentication. Cross-ref Authentication / Access Control. Follow-up: if a state-changing feature is ever added, introduce a step-up check.

---

## Token-based Session Management

**Question:** Use session tokens instead of static API secrets and keys (except legacy).
**Status:** Applicable
**Comment:** Satisfied: the app uses **no static API secrets/keys** and authenticates via the Snowflake **SSO session**, not embedded credentials. Affirm. Cross-ref Authentication (no credentials in source).

**Question:** Do not treat OAuth/refresh tokens as proof of presence; allow terminating trust with linked applications.
**Status:** Not Applicable
**Comment:** The app handles no OAuth/refresh tokens; OAuth token lifecycle and linked-app trust are owned by the corporate IdP / Snowflake, not the app.

**Question:** Use digital signatures/encryption/countermeasures for stateless session tokens.
**Status:** Not Applicable
**Comment:** The app issues no stateless session tokens, so there are no token-protection countermeasures to implement.

---

## Session Binding Requirements

**Question:** Generate a new session token upon user authentication.
**Status:** Not Applicable
**Comment:** The app generates no session tokens; session establishment is Snowflake's (a fresh Snowflake session per login).

**Question:** Generate session tokens using approved crypto with ≥64 bits of entropy.
**Status:** Not Applicable
**Comment:** No app-generated session tokens; token generation/entropy is Snowflake/IdP's responsibility.

**Question:** Store session tokens in the browser securely (secure cookies / HTML5 storage).
**Status:** Not Applicable
**Comment:** The app stores no session tokens client-side. `session_state` is server-side application state; the browser session token (if any) is set and secured by the Snowsight serving layer, not the app.

---

## Session Logout and Timeout Requirements

**Question:** Allow users to view and log out of any/all active sessions and devices.
**Status:** Not Applicable
**Comment:** The app has no session-management UI; viewing/terminating sessions and devices is a Snowflake/IdP capability, not an application feature.

**Question:** Terminate all other active sessions after a successful password change.
**Status:** Not Applicable
**Comment:** The app has no passwords or session store; password change and cascading session termination are handled by the corporate IdP / Snowflake.

**Question:** Invalidate session tokens upon logout and expiration (prevent back-button/relying-party resume).
**Status:** Applicable
**Comment:** Delegated: session invalidation on logout/expiration is enforced by Snowflake/Snowsight. The app holds **no auth tokens** that could be replayed, and its server-side `session_state`/cached connection are dropped on restart/domain switch (`close_shared_client`, `restart_app`). Follow-up: confirm the Snowflake session-expiration policy applies to the SiS app. Cross-ref Authentication.

**Question:** Periodic re-authentication during active use and after idle periods.
**Status:** Applicable
**Comment:** Delegated to Snowflake/IdP session and idle-timeout policy; the app cannot enforce re-auth. Follow-up: confirm a session/idle-timeout policy is configured for the SiS app's user population. Cross-ref Authentication (session timeout).

---

## Fundamental Session Management Requirements

**Question:** Never reveal session tokens in URL parameters or error messages.
**Status:** Applicable
**Comment:** Satisfied: the app has **no session tokens to reveal**, does not place state in URL query parameters, and the one verbose error path (`st.error(f"...{e}")`) exposes exception text — not tokens. No token leakage surface. (The generic-error follow-up is tracked in Error Handling.)

---

## Cookie-based Session Management

**Question:** Set the cookie `path` attribute as precisely as possible when sharing a domain.
**Status:** Applicable
**Comment:** Platform-delegated: the app sets no cookies. Any session cookie is set by the Snowsight serving layer under SiS; the app cannot control the `path` attribute. Follow-up: verify cookie attributes at the deployed endpoint (SSG/Heimdall).

**Question:** Use the `__Host-` prefix for session cookie confidentiality.
**Status:** Applicable
**Comment:** Platform-delegated: the app sets no cookies and cannot apply the `__Host-` prefix; the Snowsight-served session cookie is Snowflake's responsibility. Verify at the deployed endpoint.

**Question:** Set `HttpOnly` and `Secure` attributes for session cookies.
**Status:** Applicable
**Comment:** Platform-delegated: the app sets no cookies; `HttpOnly`/`Secure` on the browser session cookie are owned by the Snowsight serving layer. Follow-up: confirm via SSG/Heimdall that the deployed endpoint sets these flags.

**Question:** Use the `SameSite` attribute to limit CSRF exposure.
**Status:** Applicable
**Comment:** Platform-delegated: the app sets no cookies; `SameSite` on the session cookie is set by the serving layer. (CSRF is additionally mitigated by Streamlit's default XSRF protection and the authenticated, Snowflake-served context.) Follow-up: verify at the deployed endpoint.
