## General Validation Security Requirements

**Validate redirect URLs against a whitelist of known-safe locations.**
Status: Not Applicable
Comment: No URL redirect/forward functionality; navigation is internal step changes via server-side session state, not HTTP redirects to user-supplied URLs.

**Validate all request data (parameters, cookies, headers, URLs) on a whitelist on a trusted system.**
Status: Applicable
Comment: Widget inputs are validated server-side: catalog selections are whitelisted, numerics are bounded, and free-text project filters pass through `_canonicalize_id` and are used only as bound SQL values.

**Prevent SSRF by validating externally supplied URLs against a whitelist.**
Status: Applicable
Comment: The only outbound target is the fixed Snowflake connection; no HTTP-fetching libraries and no user-supplied URLs. The implicit whitelist is the single Snowflake endpoint.

## Input Validation and output encoding requirements

**Include a cryptographic signature with any language-serialized object.**
Status: Not Applicable
Comment: No language-native serialization (no `pickle`/Java) — only JSON/CSV data formats, so there is no language-serialized object to sign.

**Use parameterized queries / stored procedures / ORM / DB-specific encoding for queries with external input.**
Status: Applicable
Comment: The only external input reaching SQL (project-filter IDs) is bound, never concatenated. Table/schema f-string interpolation is annotated with justified `# nosec B608`.

**Normalize all input to a pre-defined Unicode normalization form or reject non-normalized input.**
Status: Applicable
Comment: Gap (low impact): no explicit Unicode normalization. Free-text project IDs are whitespace-stripped and numeric-coerced by `_canonicalize_id` but not normalized; follow-up if non-ASCII identifiers become possible.

**Normalize Unicode strings before sending to other systems or storing them.**
Status: Applicable
Comment: Partial: values sent to Snowflake are canonicalized via `_canonicalize_id` (strip + integer coercion) but not Unicode-normalized. Same low-impact gap; bind-parameterization mitigates injection risk.

**Avoid language-specific serialization (e.g. Java's built-in serialization).**
Status: Applicable
Comment: Satisfied: no `pickle`/Java/native serialization; only `json.dumps`/`pd.to_csv` for output and `json.loads`/`pd.read_csv` for parsing.

**Specify a character set for each request and input source.**
Status: Applicable
Comment: UTF-8 is specified explicitly where the app controls encoding: exports `encode("utf-8")` and CSV is written/read as UTF-8.

**Encode or sanitize HTML output; use pre-existing libraries for HTML sanitization.**
Status: Applicable
Comment: Data-derived values inside `unsafe_allow_html` are escaped with stdlib `html.escape`; Streamlit auto-escapes standard widgets. Follow-up: audit the ~100 `unsafe_allow_html` sites to ensure every dynamic value stays escaped.

**Sanitize user input before passing it over IMAP, POP3, or SMTP protocols.**
Status: Not Applicable
Comment: No email/IMAP/POP3/SMTP functionality (no `smtplib`/`imaplib`/`poplib`).

**Reject requests with input that does not meet validation rules.**
Status: Applicable
Comment: Incompatible Standard DQR assignments are filtered by `src/dqr_validation.py`; stale selectbox values fall back via guarded `.index()`; custom rules with missing dependencies raise `CustomRuleNotEvaluated`.

## Input Validation Requirements

**Protect against mass parameter assignment attacks.**
Status: Not Applicable
Comment: No auto-binding of request payloads to objects; models are built field-by-field from constrained widgets. No mass-assignment surface.

**Ensure structured data is strongly typed and validated against a schema (allowed chars, length, pattern).**
Status: Applicable
Comment: Partial: domain models are typed dataclasses and `src/dqr_validation.py` validates type compatibility, but there is no declarative schema enforcing length/pattern/charset on free-text inputs. Follow-up: add length/pattern bounds if needed.

**Defend against HTTP parameter pollution attacks.**
Status: Not Applicable
Comment: The app does not parse raw HTTP query parameters (Streamlit transport); no duplicate-parameter parsing surface to pollute.

**Validate all input using positive validation (whitelisting).**
Status: Applicable
Comment: Domain/system/dimension/source selections are whitelisted against fixed catalogs; numeric inputs are range-bounded. The free-text project filter is normalized + bind-parameterized rather than strictly pattern-whitelisted.

**Allow URL redirects/forwards only to whitelisted destinations or warn.**
Status: Not Applicable
Comment: No URL redirect/forward feature exists (internal session-state navigation only).

## XML-Specific Validation and Encoding requirements

**Sanitize/encode input before inserting into XML responses, files, or databases.**
Status: Not Applicable
Comment: The app produces no XML and performs no database writes (read-only). DB-read injection is handled via parameterized queries.

**Prevent injection flaws by not sending untrusted data to interpreters without validation.**
Status: Applicable
Comment: Injection prevention covers the interpreters actually used: SQL (bind parameters), HTML (`html.escape`), and CSV (`_sanitize_csv_cell`). No XML interpreter is used.

**Disable loading DTDs when parsing XML / use a whitelist of safe DTDs.**
Status: Not Applicable
Comment: The app parses no XML (no lxml/etree/xml). No DTD/XXE surface.

**Use parameterized XPath queries or escape input in XPath.**
Status: Not Applicable
Comment: No XPath usage anywhere.

## Memory, String, and Unmanaged Code Requirements

**Dereferences a NULL pointer expected to be valid.**
Status: Not Applicable
Comment: Pure-Python app code; no pointers or manual memory. Python `None`-attribute access is guarded by code patterns and is not a memory-safety issue.

**Ensure format strings are constant and do not take hostile input.**
Status: Applicable
Comment: All `%s`/`%d` occurrences are constant logging templates (values passed as logging args) or SQL bind placeholders — never a user-controlled format template.

**Incorrectly reusing freed memory (use-after-free).**
Status: Not Applicable
Comment: Python is garbage-collected; no manual memory management in app code.

**Accesses memory outside buffer boundaries.**
Status: Not Applicable
Comment: Memory-safe Python; no direct buffer access in app code.

**Use memory-safe string operations / safe memory copy / pointer arithmetic.**
Status: Not Applicable
Comment: No unmanaged code or pointer arithmetic in app code. C-extension dependencies (numpy/pandas/pyarrow) are a dependency/SCA concern.

**Consider write/read operations that could cause memory corruption out of range.**
Status: Not Applicable
Comment: Memory-safe Python; no out-of-range memory operations in app code.

**Use sign/range/input validation to prevent integer overflows.**
Status: Not Applicable
Comment: Python integers are arbitrary-precision. Fixed-width numpy dtype overflow is a data-correctness concern, not a security boundary, and is not driven by untrusted input.

## Sanitization and Sandboxing Requirements

**Sanitize/disable/sandbox user-supplied SVG to prevent XSS.**
Status: Not Applicable
Comment: The app accepts no user-supplied SVG. Charts are app-generated by Plotly; the disabled upload accepted only JSON/CSV.

**Sanitize unstructured data (allowed characters, length).**
Status: Applicable
Comment: Partial: free-text project IDs are normalized via `_canonicalize_id`, but no explicit length/character-class cap is enforced. Low risk (bind-parameterized, not raw HTML). Follow-up: add length/charset bounds.

**Protect against SSRF by validating/sanitizing untrusted data; whitelist protocols/domains/paths/ports.**
Status: Applicable
Comment: Single fixed Snowflake egress, no user-supplied URLs, no HTTP libraries.

**Sanitize/disable/sandbox scriptable or template content (Markdown, CSS, XSL, BBCode).**
Status: Applicable
Comment: Markdown and injected CSS are all app-authored static content; user/data-derived values are `html.escape`d before insertion. No user-supplied scriptable/template content is rendered.

**Sanitize user input before passing it to mail systems (SMTP/IMAP injection).**
Status: Not Applicable
Comment: No mail functionality.

**Sanitize untrusted HTML from WYSIWYG editors.**
Status: Not Applicable
Comment: No WYSIWYG/rich-text editor; the app accepts no untrusted HTML input.

**Avoid eval()/dynamic code execution; sanitize/sandbox if unavoidable.**
Status: Applicable
Comment: Satisfied: no `eval`/`exec`/dynamic code execution anywhere; uploaded content (when active) was parsed as data only.

## Deserialization Prevention Requirements

**Use JSON.parse for parsing JSON, avoiding eval().**
Status: Applicable
Comment: JSON is parsed with `json.loads` (in the now-disabled loader) — never `eval`. There is no custom JavaScript backend.

**Avoid or protect deserialization of untrusted data (JSON/XML/YAML parsers).**
Status: Applicable
Comment: No untrusted deserialization beyond JSON/CSV parsed strictly as data (no object reconstruction); no `pickle`/`yaml.load`/XML parsing. The upload entry point is currently disabled.

**Use integrity checks or encryption for serialized objects.**
Status: Applicable
Comment: Gap (low risk): exported JSON/CSV are not signed/encrypted. The re-import path parses them as data, not reconstructable objects, so the residual concern is tamper-detection. Follow-up: add an integrity check if exports become trust-sensitive.

**Restrict XML parsers to the most restrictive configuration; disable external entities (XXE).**
Status: Not Applicable
Comment: No XML parsing in the app (no lxml/etree/xml). No XXE surface.

## Output Encoding and Injection Prevention Requirements

**Prevent Local File Inclusion (LFI) and Remote File Inclusion (RFI) attacks.**
Status: Applicable
Comment: No file inclusion from user input, no dynamic import, no filesystem operations, and (with upload disabled) no user filename intake. No LFI/RFI surface.

**Use parameterized queries / ORM / entity frameworks to protect against DB injection.**
Status: Applicable
Comment: Parameterized Snowflake reads with bound filter values. Read-only access further limits impact.

**Implement context-aware output escaping to protect against XSS.**
Status: Applicable
Comment: `html.escape` for the HTML context, Streamlit auto-escaping for standard widgets, and `_sanitize_csv_cell` for the spreadsheet context. Context-appropriate per output target.

**Ensure output encoding is relevant for the interpreter and context, preserving charset/locale.**
Status: Applicable
Comment: UTF-8 is preserved across exports/imports; HTML, CSV, and JSON outputs each use their appropriate encoding/escaping.

**Use context-specific output encoding when parameterized mechanisms are unavailable.**
Status: Applicable
Comment: Demonstrated by the CSV formula-injection sanitizer `_sanitize_csv_cell` — spreadsheets have no parameterization, so context-specific neutralization is applied at write time.

**Protect against DLL Hijacking by signing executables and verifying signatures.**
Status: Not Applicable
Comment: The app ships no executables/DLLs; it is pure Python run via Streamlit. No native binary load path to hijack.

**Protect against JavaScript, JSON, XPath, and LDAP injection attacks.**
Status: Applicable
Comment: JSON output is safely encoded via `json.dumps` (no manual string assembly); there is no custom JavaScript, XPath, or LDAP usage. The JSON-encoding control is the applicable part.

**Protect against XML injection.**
Status: Not Applicable
Comment: The app neither consumes nor produces XML. No XML-injection surface.

**Prevent OS command injection (parameterized OS queries / command-line output encoding).**
Status: Applicable
Comment: No `subprocess`/`os.system`/shell execution anywhere, and no user input is passed to a system/command API. No OS-command-injection surface.
