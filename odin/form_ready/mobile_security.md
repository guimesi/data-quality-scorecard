## Resiliency against Reverse Engineering Requirements

**Implement device binding using a unique device fingerprint.**
Status: Not Applicable
Comment: No mobile/device context; access is bound to Snowflake identity, not a device fingerprint.

**Trigger various types of responses, including delayed and stealthy ones (anti-analysis).**
Status: Not Applicable
Comment: Anti-reverse-engineering logic protects distributed mobile binaries; there is no client binary here.

**Apply application-level payload encryption for defense in depth.**
Status: Not Applicable
Comment: No mobile client/transport; transport is TLS via the Snowflake connector/Snowsight.

**Apply obfuscation to programmatic defenses to impede dynamic analysis.**
Status: Not Applicable
Comment: No distributed binary; the app is server-side Python not shipped to a client.

**Detect and respond to the app running in an emulator.**
Status: Not Applicable
Comment: No mobile runtime; there is no emulator concept for a Streamlit web app.

**Detect and respond to tampering with code/data in memory, executables, and sandbox data.**
Status: Not Applicable
Comment: No client-side executable or mobile sandbox; the app runs in Snowflake's managed compute.

**Detect and respond to widely used reverse engineering tools/frameworks.**
Status: Not Applicable
Comment: No mobile binary is exposed to such tooling.

**Detect and respond to rooted/jailbroken devices.**
Status: Not Applicable
Comment: No mobile device context; root/jailbreak detection does not apply to a web app.

**Prevent debugging and detect/respond to attached debuggers.**
Status: Not Applicable
Comment: No distributed client process for an attacker to attach a debugger to.

**Use robust obfuscation for sensitive computations; prefer hardware-based isolation.**
Status: Not Applicable
Comment: No on-device computation; scoring/DQR logic runs server-side in Snowflake compute.

**Encrypt executable files/libraries; encrypt or pack important code/data segments.**
Status: Not Applicable
Comment: No shipped executables/libraries to encrypt or pack; the app is server-side source.

**Implement multiple mechanisms in each defense category for resiliency.**
Status: Not Applicable
Comment: No mobile anti-tamper defense categories exist for this application.

## Platform Requirements

**Clear WebView's cache, storage, and loaded resources before destruction.**
Status: Not Applicable
Comment: The app uses no WebView; browser caching is handled under the Data Protection theme.

**Prevent usage of custom third-party keyboards when entering sensitive data.**
Status: Not Applicable
Comment: No mobile keyboard context; inputs are entered in a desktop browser.

**Protect sensitive functionality exported through IPC facilities and custom URL schemes.**
Status: Not Applicable
Comment: The app exposes no IPC mechanisms or custom URL schemes.

**Disable JavaScript in WebViews unless explicitly required.**
Status: Not Applicable
Comment: No WebView exists; the UI is rendered by Streamlit in a standard browser.

**Request the minimum set of permissions necessary.**
Status: Not Applicable
Comment: No mobile OS permission model; data-layer least-privilege is covered under Access Control.

**Configure WebViews to allow only necessary protocol handlers (ideally HTTPS only).**
Status: Not Applicable
Comment: No WebView/protocol-handler configuration; the app has no mobile client.

**Protect against screen overlay attacks (Android only).**
Status: Not Applicable
Comment: Android-specific; the app has no Android client.

**Ensure WebView only renders JavaScript within the app package if native methods are exposed.**
Status: Not Applicable
Comment: No WebView and no native bridge; this control has no surface in a Streamlit web app.
