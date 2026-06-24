## Defenses Against Session Management Exploits

**Ensure a valid login session or require re-authentication / secondary verification before sensitive transactions or account modifications.**
Status: Applicable
Comment: A valid Snowflake login session is required to reach the app (platform-enforced), and the app is read-only with no sensitive operations warranting step-up. Follow-up: add a step-up check if a state-changing feature is ever introduced.

## Token-based Session Management

**Use session tokens instead of static API secrets and keys (except legacy).**
Status: Applicable
Comment: Satisfied: the app uses no static API secrets/keys and authenticates via the Snowflake SSO session, not embedded credentials.

**Do not treat OAuth/refresh tokens as proof of presence; allow terminating trust with linked applications.**
Status: Not Applicable
Comment: The app handles no OAuth/refresh tokens; OAuth lifecycle and linked-app trust are owned by the corporate IdP / Snowflake.

**Use digital signatures/encryption/countermeasures for stateless session tokens.**
Status: Not Applicable
Comment: The app issues no stateless session tokens, so there are no token-protection countermeasures to implement.

## Session Binding Requirements

**Generate a new session token upon user authentication.**
Status: Not Applicable
Comment: The app generates no session tokens; session establishment is Snowflake's (a fresh Snowflake session per login).

**Generate session tokens using approved crypto with ≥64 bits of entropy.**
Status: Not Applicable
Comment: No app-generated session tokens; token generation and entropy are Snowflake/IdP's responsibility.

**Store session tokens in the browser securely (secure cookies / HTML5 storage).**
Status: Not Applicable
Comment: The app stores no session tokens client-side; `session_state` is server-side application state, and any browser session token is secured by the Snowsight serving layer.

## Session Logout and Timeout Requirements

**Allow users to view and log out of any/all active sessions and devices.**
Status: Not Applicable
Comment: The app has no session-management UI; viewing and terminating sessions/devices is a Snowflake/IdP capability, not an app feature.

**Terminate all other active sessions after a successful password change.**
Status: Not Applicable
Comment: The app has no passwords or session store; password change and cascading session termination are handled by the corporate IdP / Snowflake.

**Invalidate session tokens upon logout and expiration (prevent back-button/relying-party resume).**
Status: Applicable
Comment: Delegated: session invalidation is enforced by Snowflake/Snowsight; the app holds no auth tokens, and its `session_state`/cached connection are dropped on restart/domain switch (`close_shared_client`, `restart_app`). Follow-up: confirm the Snowflake session-expiration policy applies.

**Periodic re-authentication during active use and after idle periods.**
Status: Applicable
Comment: Delegated to Snowflake/IdP session and idle-timeout policy; the app cannot enforce re-auth. Follow-up: confirm a session/idle-timeout policy is configured for the app's user population.

## Fundamental Session Management Requirements

**Never reveal session tokens in URL parameters or error messages.**
Status: Applicable
Comment: Satisfied: the app has no session tokens to reveal, places no state in URL query parameters, and its verbose error path (`st.error(f"...{e}")`) exposes exception text, not tokens.

## Cookie-based Session Management

**Set the cookie `path` attribute as precisely as possible when sharing a domain.**
Status: Applicable
Comment: Platform-delegated: the app sets no cookies; any session cookie is set by the Snowsight serving layer. Follow-up: verify cookie attributes at the deployed endpoint (SSG/Heimdall).

**Use the `__Host-` prefix for session cookie confidentiality.**
Status: Applicable
Comment: Platform-delegated: the app sets no cookies and cannot apply the `__Host-` prefix; the session cookie is Snowflake's responsibility. Verify at the deployed endpoint.

**Set `HttpOnly` and `Secure` attributes for session cookies.**
Status: Applicable
Comment: Platform-delegated: the app sets no cookies; `HttpOnly`/`Secure` on the browser session cookie are owned by the Snowsight serving layer. Follow-up: confirm these flags via SSG/Heimdall at the deployed endpoint.

**Use the `SameSite` attribute to limit CSRF exposure.**
Status: Applicable
Comment: Platform-delegated: the app sets no cookies; `SameSite` is set by the serving layer (CSRF is additionally mitigated by Streamlit's default XSRF protection). Follow-up: verify at the deployed endpoint.
