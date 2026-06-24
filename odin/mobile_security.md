# Mobile Security — Odin Threat Modeling Assessment

**Application:** `data-quality-scorecard`

**Theme-level determination: the entire Mobile Security theme is Not Applicable.**

`data-quality-scorecard` is a **Python/Streamlit web application**, not a native mobile app.
There is **no iOS/Android codebase, no compiled mobile binary (APK/IPA), no WebView, no
native libraries, no IPC/custom URL schemes, and no mobile platform dependencies** in the
repository. Locally it runs in a desktop browser via `streamlit run`; in production it runs
as **Streamlit in Snowflake**, reached through the Snowflake/Snowsight browser UI. None of
the mobile-specific concepts below (reverse engineering of distributed mobile binaries,
root/jailbreak/emulator detection, WebView hardening, mobile permission models, screen
overlays) have any surface in this application. This is consistent with the "Mobile
architecture Requirements" section (Architecture theme), also marked Not Applicable.

> **Note:** these items would only become Applicable if a native mobile client were built
> for this application — which is not on the roadmap. The relevant non-mobile equivalents
> (auth, data protection, input/output handling, dependency integrity) are covered in the
> Data Protection, Architecture, and File and Resources themes.

---

## Resiliency against Reverse Engineering Requirements

**Question:** Implement device binding using a unique device fingerprint.
**Status:** Not Applicable
**Comment:** No mobile app/device context; the app runs server-side (SiS) / in a desktop browser. Access is bound to the user's Snowflake identity, not a device fingerprint.

**Question:** Trigger various types of responses, including delayed and stealthy ones (anti-analysis).
**Status:** Not Applicable
**Comment:** Anti-reverse-engineering response logic applies to distributed mobile binaries; there is no client binary to protect.

**Question:** Apply application-level payload encryption for defense in depth.
**Status:** Not Applicable
**Comment:** No mobile client/transport to add payload encryption to. Transport is TLS (Snowflake connector / Snowsight); covered under the Communications theme.

**Question:** Apply obfuscation to programmatic defenses to impede dynamic analysis.
**Status:** Not Applicable
**Comment:** No distributed binary; the app is server-side Python (source not shipped to an untrusted client). Code obfuscation does not apply.

**Question:** Detect and respond to the app running in an emulator.
**Status:** Not Applicable
**Comment:** No mobile runtime; there is no emulator concept for a Streamlit web app.

**Question:** Detect and respond to tampering with code/data in memory, executables, and sandbox data.
**Status:** Not Applicable
**Comment:** No client-side executable or mobile sandbox. The app runs in Snowflake's managed compute; integrity of that environment is a platform responsibility.

**Question:** Detect and respond to widely used reverse engineering tools/frameworks.
**Status:** Not Applicable
**Comment:** No mobile binary exposed to such tooling.

**Question:** Detect and respond to rooted/jailbroken devices.
**Status:** Not Applicable
**Comment:** No mobile device context; root/jailbreak detection does not apply to a browser/server web app.

**Question:** Prevent debugging and detect/respond to attached debuggers.
**Status:** Not Applicable
**Comment:** No distributed client process for an attacker to attach a debugger to.

**Question:** Use robust obfuscation for sensitive computations; prefer hardware-based isolation.
**Status:** Not Applicable
**Comment:** No on-device sensitive computation. Scoring/DQR logic runs server-side (SiS sandbox / Snowflake compute), not on a client device.

**Question:** Encrypt executable files/libraries; encrypt or pack important code/data segments.
**Status:** Not Applicable
**Comment:** No shipped executables/libraries to encrypt or pack; the app is server-side source.

**Question:** Implement multiple mechanisms in each defense category for resiliency.
**Status:** Not Applicable
**Comment:** No mobile anti-tamper defense categories exist for this application.

---

## Platform Requirements

**Question:** Clear WebView's cache, storage, and loaded resources before destruction.
**Status:** Not Applicable
**Comment:** The app uses no WebView (no mobile app). Browser caching is addressed (as a platform/framework concern) under the Data Protection theme.

**Question:** Prevent usage of custom third-party keyboards when entering sensitive data.
**Status:** Not Applicable
**Comment:** No mobile keyboard context; inputs are entered in a desktop browser.

**Question:** Protect sensitive functionality exported through IPC facilities and custom URL schemes.
**Status:** Not Applicable
**Comment:** The app exposes no IPC mechanisms or custom URL schemes (no mobile/native components).

**Question:** Disable JavaScript in WebViews unless explicitly required.
**Status:** Not Applicable
**Comment:** No WebView exists. (The app's UI is rendered by Streamlit in a standard browser; XSS hygiene via `html.escape` is covered under the Input/Output theme.)

**Question:** Request the minimum set of permissions necessary.
**Status:** Not Applicable
**Comment:** No mobile OS permission model. Least-privilege at the data layer (Snowflake role/grants) is covered under the Access Control theme.

**Question:** Configure WebViews to allow only necessary protocol handlers (ideally HTTPS only).
**Status:** Not Applicable
**Comment:** No WebView/protocol-handler configuration; the app has no mobile client.

**Question:** Protect against screen overlay attacks (Android only).
**Status:** Not Applicable
**Comment:** Android-specific; the app has no Android client.

**Question:** Ensure WebView only renders JavaScript within the app package if native methods are exposed.
**Status:** Not Applicable
**Comment:** No WebView and no native bridge; this control has no surface in a Streamlit web app.
