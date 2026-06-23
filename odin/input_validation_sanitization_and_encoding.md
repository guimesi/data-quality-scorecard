# Input Validation, Sanitization and Encoding — Odin Threat Modeling Assessment

**Application:** `data-quality-scorecard`

**Framing context:** Streamlit app (local dev; **Streamlit in Snowflake** in production).
Established controls relevant to this theme:

- **SQL:** parameterized — user filter values are bound via `cursor.execute(sql, params)`,
  never concatenated (`src/data_product_builder.py:79-110`, `src/snowflake_client.py`);
  table/db/schema names are internal config, not user input. `_canonicalize_id` normalizes
  filter values.
- **HTML output:** `unsafe_allow_html=True` is used widely, but **data-derived strings are
  `html.escape`d at the render site** (e.g. `ui/step_06/_breakdown.py:115-117`); CSS/markdown
  templates are app-authored static content.
- **CSV output:** `_sanitize_csv_cell` neutralizes spreadsheet formula injection
  (`ui/step_06/_export.py`).
- **No untrusted deserialization / dynamic execution:** no `pickle`/`yaml.load`/`eval`/
  `exec`/dynamic import; serialization is JSON/CSV (data) only. The snapshot **upload feature
  is currently disabled** (loaders retained but unreachable — see File and Resources theme).
- **Verified absent:** XML/XPath/LDAP/SMTP/IMAP, lxml/etree, Unicode normalization,
  user-controlled format strings, `subprocess`/`os.system`, filesystem I/O.
- **Language:** pure-Python app code (memory-managed; no pointers/unmanaged code).

> **SiS production note:** the SQL parameterization must be preserved when
> `src/snowflake_client.py` now uses `get_active_session()` (Snowpark) inside SiS with the
> connector as the local fallback; the WHERE-IN binding is **preserved on both paths** (qmark
> `?` for Snowpark via `session.sql(..., params=...)`, `%s` for the connector).

---

## General Validation Security Requirements

**Question:** Validate redirect URLs against a whitelist of known-safe locations.
**Status:** Not Applicable
**Comment:** The app has no URL redirect/forward functionality. Navigation is internal step changes via `st.session_state.current_step` (server-side), not HTTP redirects to user-supplied URLs.

**Question:** Validate all request data (parameters, cookies, headers, URLs) on a whitelist on a trusted system.
**Status:** Applicable
**Comment:** The app does not parse raw HTTP params/cookies/headers (Streamlit's WebSocket transport handles that), but user inputs (widget values) are validated **server-side in Python**: domain/system/dimension selections come from fixed catalogs (whitelist), weights/params are numeric, and project-filter free-text passes through `_canonicalize_id` and is used only as a bound SQL value. Whitelist-style validation for the constrained inputs; free-text is normalized + parameterized rather than strictly whitelisted.

**Question:** Prevent SSRF by validating externally supplied URLs against a whitelist.
**Status:** Applicable
**Comment:** Satisfied by design: the only outbound target is the fixed Snowflake connection; there are no HTTP-fetching libraries and no user-supplied URLs/hosts. Under SiS there is no external egress at all. The implicit "whitelist" is the single Snowflake endpoint.

---

## Input Validation and output encoding requirements

**Question:** Include a cryptographic signature with any language-serialized object.
**Status:** Not Applicable
**Comment:** The app uses no language-native serialization (no `pickle`/Java serialization) — only JSON/CSV data formats. There is no language-serialized object to sign. (Integrity of exported JSON/CSV is addressed under Deserialization Prevention below.)

**Question:** Use parameterized queries / stored procedures / ORM / DB-specific encoding for queries with external input.
**Status:** Applicable
**Comment:** Strong control in place. The only external input reaching SQL (project-filter IDs) is passed as **bound parameters**, never string-concatenated (`src/data_product_builder.py:79-110`) — and binding is preserved on **both** backends: `%s` to `cursor.execute` (connector) and qmark `?` to `session.sql(..., params=...)` (Snowpark/SiS). The known-safe f-string table/schema interpolation is annotated with justified `# nosec B608`. Positive evidence for SAST SQL-injection checks.

**Question:** Normalize all input to a pre-defined Unicode normalization form or reject non-normalized input.
**Status:** Applicable
**Comment:** Gap (low impact): the app performs **no explicit Unicode normalization** (no `unicodedata.normalize`/NFC/NFKC). Inputs are mostly constrained (catalog selections, numeric values); the one free-text input (project IDs) is whitespace-stripped and numeric-coerced by `_canonicalize_id` but not Unicode-normalized. Risk is low given the input types and parameterized SQL; follow-up: normalize free-text before comparison/storage if non-ASCII identifiers become possible.

**Question:** Normalize Unicode strings before sending to other systems or storing them.
**Status:** Applicable
**Comment:** Partial / gap. Values sent to Snowflake are canonicalized (`_canonicalize_id`: strip + integer coercion) but not Unicode-normalized; the app stores nothing itself. Same low-impact gap as above; bind-parameterization mitigates injection risk regardless.

**Question:** Avoid language-specific serialization (e.g. Java's built-in serialization).
**Status:** Applicable
**Comment:** Satisfied: no `pickle`/Java/native serialization anywhere; only `json.dumps`/`pd.to_csv` for output and `json.loads`/`pd.read_csv` for parsing. Positive evidence for SAST.

**Question:** Specify a character set for each request and input source.
**Status:** Applicable
**Comment:** UTF-8 is specified explicitly where the app controls encoding: exports `encode("utf-8")` (`ui/step_06/_export.py:237`, `ui/step_07/_run_history.py:89`) and the (disabled) loaders `decode("utf-8")`. CSV is written/read as UTF-8. Control in place.

**Question:** Encode or sanitize HTML output; use pre-existing libraries for HTML sanitization.
**Status:** Applicable
**Comment:** In place: data-derived values rendered inside `unsafe_allow_html` are escaped with the stdlib `html.escape(...)` (e.g. `ui/step_06/_breakdown.py:115-117`); Streamlit auto-escapes standard widgets. Follow-up: periodically audit the ~100 `unsafe_allow_html` sites to ensure every dynamic value stays escaped (especially Snowflake-derived column names/values).

**Question:** Sanitize user input before passing it over IMAP, POP3, or SMTP protocols.
**Status:** Not Applicable
**Comment:** The app has no email/IMAP/POP3/SMTP functionality (verified: no `smtplib`/`imaplib`/`poplib`).

**Question:** Reject requests with input that does not meet validation rules.
**Status:** Applicable
**Comment:** In place: incompatible Standard DQR assignments are filtered by `src/dqr_validation.py`; stale/invalid selectbox values fall back via guarded `.index()` (ARCHITECTURE "`.index()` calls are guarded"); custom rules with missing dependencies raise `CustomRuleNotEvaluated` rather than silently passing; (when upload was active, malformed files were rejected with a warning).

---

## Input Validation Requirements

**Question:** Protect against mass parameter assignment attacks.
**Status:** Not Applicable
**Comment:** No auto-binding of request payloads to objects; models are built field-by-field from constrained widgets (also covered in Data Protection). No mass-assignment surface.

**Question:** Ensure structured data is strongly typed and validated against a schema (allowed chars, length, pattern).
**Status:** Applicable
**Comment:** Partial. Domain models are typed dataclasses (`src/models.py`); `src/dqr_validation.py` validates rule/param type compatibility; `src/profiler.py` classifies column dtypes. There is **no declarative schema** (e.g. pydantic) enforcing length/pattern/charset on free-text inputs (project IDs) — though those are normalized and bind-parameterized. Follow-up: add length/pattern bounds on free-text if needed.

**Question:** Defend against HTTP parameter pollution attacks.
**Status:** Not Applicable
**Comment:** The app does not parse raw HTTP query parameters (Streamlit transport); there is no duplicate-parameter parsing surface to pollute.

**Question:** Validate all input using positive validation (whitelisting).
**Status:** Applicable
**Comment:** Mostly satisfied: domain/system/dimension/source selections are whitelisted against fixed catalogs/registries; numeric inputs are range-bounded by usage. The free-text project filter is normalized + bind-parameterized rather than strictly pattern-whitelisted (safe by construction). 

**Question:** Allow URL redirects/forwards only to whitelisted destinations or warn.
**Status:** Not Applicable
**Comment:** No URL redirect/forward feature exists (internal session-state navigation only).

---

## XML-Specific Validation and Encoding requirements

**Question:** Sanitize/encode input before inserting into XML responses, files, or databases.
**Status:** Not Applicable
**Comment:** The app produces no XML and performs no database writes (read-only). DB-read injection is handled via parameterized queries (above).

**Question:** Prevent injection flaws by not sending untrusted data to interpreters without validation.
**Status:** Applicable
**Comment:** General injection-prevention is implemented for the interpreters the app actually uses: **SQL** (bind parameters), **HTML** (`html.escape`), and **spreadsheet/CSV** (`_sanitize_csv_cell`). No XML interpreter is used. Strong overall control.

**Question:** Disable loading DTDs when parsing XML / use a whitelist of safe DTDs.
**Status:** Not Applicable
**Comment:** The app parses no XML (no lxml/etree/xml usage). No DTD/XXE surface.

**Question:** Use parameterized XPath queries or escape input in XPath.
**Status:** Not Applicable
**Comment:** No XPath usage anywhere.

---

## Memory, String, and Unmanaged Code Requirements

**Question:** Dereferences a NULL pointer expected to be valid.
**Status:** Not Applicable
**Comment:** Pure-Python app code; no pointers/manual memory. (Python `None`-attribute access is guarded by code patterns but is not a memory-safety issue.)

**Question:** Ensure format strings are constant and do not take hostile input.
**Status:** Applicable
**Comment:** Satisfied: all `%s`/`%d` occurrences are **constant logging templates** (with values passed as logging args) or **SQL bind placeholders** — never a user-controlled format template. No `str.format`/`%` formatting uses attacker-controlled format specifiers. Positive evidence.

**Question:** Incorrectly reusing freed memory (use-after-free).
**Status:** Not Applicable
**Comment:** Python is garbage-collected; no manual memory management in app code.

**Question:** Accesses memory outside buffer boundaries.
**Status:** Not Applicable
**Comment:** Memory-safe Python; no direct buffer access in app code.

**Question:** Use memory-safe string operations / safe memory copy / pointer arithmetic.
**Status:** Not Applicable
**Comment:** No unmanaged code or pointer arithmetic in app code. (C-extension dependencies — numpy/pandas/pyarrow — are third-party; their integrity is a dependency/SCA concern tracked in the Architecture/SiS notes.)

**Question:** Consider write/read operations that could cause memory corruption out of range.
**Status:** Not Applicable
**Comment:** Memory-safe Python; no out-of-range memory operations in app code.

**Question:** Use sign/range/input validation to prevent integer overflows.
**Status:** Not Applicable
**Comment:** Python integers are arbitrary-precision (no overflow). Fixed-width numpy dtype overflow is possible during numeric computation but is a data-correctness concern, not a security boundary, and is not driven by untrusted input.

---

## Sanitization and Sandboxing Requirements

**Question:** Sanitize/disable/sandbox user-supplied SVG to prevent XSS.
**Status:** Not Applicable
**Comment:** The app accepts no user-supplied SVG. Charts are app-generated by Plotly; the (disabled) upload accepted only JSON/CSV.

**Question:** Sanitize unstructured data (allowed characters, length).
**Status:** Applicable
**Comment:** Partial: free-text project IDs are normalized via `_canonicalize_id`, but no explicit length/character-class cap is enforced. Low risk (bind-parameterized, not rendered as raw HTML). Follow-up: add length/charset bounds if free-text inputs broaden.

**Question:** Protect against SSRF by validating/sanitizing untrusted data; whitelist protocols/domains/paths/ports.
**Status:** Applicable
**Comment:** Satisfied by design — single fixed Snowflake egress, no user-supplied URLs, no HTTP libraries; no external egress under SiS. (Same control as the General Validation SSRF item.)

**Question:** Sanitize/disable/sandbox scriptable or template content (Markdown, CSS, XSL, BBCode).
**Status:** Applicable
**Comment:** The app renders Markdown and injects CSS via `unsafe_allow_html`, but **all template/style content is app-authored static** (stylesheets use sentinel color-swaps, not user data); user/data-derived values are `html.escape`d before insertion. No user-supplied scriptable/template content is rendered. Follow-up: keep this invariant during the `unsafe_allow_html` audit.

**Question:** Sanitize user input before passing it to mail systems (SMTP/IMAP injection).
**Status:** Not Applicable
**Comment:** No mail functionality.

**Question:** Sanitize untrusted HTML from WYSIWYG editors.
**Status:** Not Applicable
**Comment:** No WYSIWYG/rich-text editor; the app accepts no untrusted HTML input.

**Question:** Avoid eval()/dynamic code execution; sanitize/sandbox if unavoidable.
**Status:** Applicable
**Comment:** Satisfied: no `eval`/`exec`/dynamic code execution anywhere; uploaded content (when the feature was active) was parsed as data only. Positive evidence for SAST.

---

## Deserialization Prevention Requirements

**Question:** Use JSON.parse for parsing JSON, avoiding eval().
**Status:** Applicable
**Comment:** Equivalent control on the Python side: JSON is parsed with `json.loads` (`src/ml_lab.py:841`, in the now-disabled loader) — never `eval`. There is no custom JavaScript backend.

**Question:** Avoid or protect deserialization of untrusted data (JSON/XML/YAML parsers).
**Status:** Applicable
**Comment:** In place: no untrusted deserialization beyond JSON/CSV parsed strictly as **data** (no object reconstruction); no `pickle`/`yaml.load`/XML parsing. The upload entry point is currently disabled, further reducing the surface. Snowflake-read data is typed via the connector.

**Question:** Use integrity checks or encryption for serialized objects.
**Status:** Applicable
**Comment:** Gap (low risk): exported JSON/CSV are **not signed/encrypted**. Because the (disabled) re-import path parses them as data — not as reconstructable code objects — hostile-object-creation risk is nil; the residual concern is tamper-detection of an exported file. Follow-up: add an integrity check only if exported scorecards become trust-sensitive inputs to another system.

**Question:** Restrict XML parsers to the most restrictive configuration; disable external entities (XXE).
**Status:** Not Applicable
**Comment:** No XML parsing in the app (no lxml/etree/xml). No XXE surface.

---

## Output Encoding and Injection Prevention Requirements

**Question:** Prevent Local File Inclusion (LFI) and Remote File Inclusion (RFI) attacks.
**Status:** Applicable
**Comment:** Satisfied: no file inclusion from user input, no dynamic import, no filesystem operations, and (with upload disabled) no user filename intake at all. No LFI/RFI surface.

**Question:** Use parameterized queries / ORM / entity frameworks to protect against DB injection.
**Status:** Applicable
**Comment:** In place — parameterized Snowflake reads with bound filter values (see SQL control above). Read-only access further limits impact.

**Question:** Implement context-aware output escaping to protect against XSS.
**Status:** Applicable
**Comment:** In place: `html.escape` for the HTML context (data inside `unsafe_allow_html`), Streamlit auto-escaping for standard widgets, and `_sanitize_csv_cell` for the spreadsheet context. Context-appropriate per output target.

**Question:** Ensure output encoding is relevant for the interpreter and context, preserving charset/locale.
**Status:** Applicable
**Comment:** In place: UTF-8 is preserved across exports/imports; HTML vs CSV vs JSON outputs each use their appropriate encoding/escaping. 

**Question:** Use context-specific output encoding when parameterized mechanisms are unavailable.
**Status:** Applicable
**Comment:** Demonstrated by the CSV formula-injection sanitizer (`_sanitize_csv_cell`) — spreadsheets have no parameterization, so the app applies context-specific neutralization at write time.

**Question:** Protect against DLL Hijacking by signing executables and verifying signatures.
**Status:** Not Applicable
**Comment:** The app ships no executables/DLLs; it is pure Python run via Streamlit (SiS in production). No native binary load path to hijack.

**Question:** Protect against JavaScript, JSON, XPath, and LDAP injection attacks.
**Status:** Applicable
**Comment:** JSON output is safely encoded via `json.dumps` (no manual string assembly); there is no custom JavaScript, no XPath, and no LDAP usage, so those sub-vectors are not present. The JSON-encoding control is the applicable part.

**Question:** Protect against XML injection.
**Status:** Not Applicable
**Comment:** The app neither consumes nor produces XML. No XML-injection surface.

**Question:** Prevent OS command injection (parameterized OS queries / command-line output encoding).
**Status:** Applicable
**Comment:** Satisfied: there is **no `subprocess`/`os.system`/shell execution** anywhere, and no user input is passed to a system/command API. No OS-command-injection surface. Positive evidence for SAST.
