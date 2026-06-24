# File and Resources — Odin Threat Modeling Assessment

**Application:** `data-quality-scorecard`

**Theme-level context (updated — upload feature disabled):**

The ML Lab snapshot **upload feature is currently DISABLED ("under maintenance")**. The
`st.file_uploader` was removed from the Run History tab and replaced with a disabled
button; the app **no longer accepts any user-uploaded files**. (Change made on branch
`chore/disable-snapshot-upload`: `ui/step_07/_run_history.py` + docs; the upcoming rework
will persist snapshots automatically so users never upload.) The parser functions
`load_snapshot_from_json` / `load_snapshot_from_csv` are **retained in `src/ml_lab.py`** and
still unit-tested, but they are **unreachable from the UI** — no code path feeds them
user-supplied bytes.

**What this means for this theme:** the upload-centric requirements are now **Not
Applicable while the feature is disabled** (with a re-evaluation flag for when it is
re-enabled). The **live file/resource surface is limited to:**

- **Downloads** — CSV/JSON generated in memory and delivered via `st.download_button`
  (`ui/step_06/_export.py`, `ui/step_07/_run_history.py:export`). Filenames are
  app-generated; CSV cells are sanitized against formula injection (`_sanitize_csv_cell`);
  data-derived HTML is `html.escape`d.
- **Outbound requests** — only the fixed Snowflake connection; no HTTP-fetching libraries;
  no user-controlled URLs.
- **No filesystem I/O** anywhere (no file writes/reads), **no `eval`/`exec`/`pickle`/
  dynamic import.**

> **SiS production note:** under Streamlit in Snowflake the disabled state is unchanged;
> when upload is re-enabled it will run inside the Snowflake sandbox (uploaded bytes never
> reach a public web root). Re-open the upload items below at that point.

---

## File Storage Requirements

**Question:** Section directive.
**Status:** Applicable
**Comment:** Directive; items assessed individually for the current (upload-disabled) state.

**Question:** Store files from untrusted sources outside the web root, with limited permissions and strong validation.
**Status:** Not Applicable
**Comment:** The app currently accepts **no files from untrusted sources** (upload disabled). There is no stored/ingested file to place outside a web root. Note: the app performs no filesystem writes in any case, so even when upload is re-enabled, files are handled in memory only. Re-evaluate the "strong validation" aspect when the snapshot feature is re-enabled (validation today is structural parse + extension — see history below).

**Question:** Scan files from untrusted sources with antivirus scanners.
**Status:** Not Applicable
**Comment:** No untrusted files are accepted while upload is disabled, so there is nothing to scan. **Follow-up flag:** re-evaluate AV/malware scanning when the upload/auto-persist feature is re-enabled (it was an open gap when upload was active).

---

## File Upload Requirements

**Question:** Section directive.
**Status:** Applicable
**Comment:** Directive; the upload feature is disabled, so the items below are Not Applicable pending rework.

**Question:** Prevent acceptance of large files that could fill storage / cause DoS.
**Status:** Not Applicable
**Comment:** No upload path is exposed (the `st.file_uploader` was removed). No large-file intake is possible. Re-evaluate (set an explicit `server.maxUploadSize`) if/when upload is re-enabled.

**Question:** Enforce file size quotas and max number of files per user.
**Status:** Not Applicable
**Comment:** No upload path exposed; no per-user file intake. Re-evaluate quotas when the feature is re-enabled.

**Question:** Check compressed files for "zip bombs".
**Status:** Not Applicable
**Comment:** No upload path, and even when active the feature accepted only `json`/`csv` (no archive formats / no decompression). No zip-bomb vector now or previously.

---

## File Download Requirements

**Question:** Section directive.
**Status:** Applicable
**Comment:** Directive; the **download** capability remains active, so these items are still in scope.

**Question:** Ensure direct requests to uploaded files are never executed as HTML/JavaScript.
**Status:** Applicable
**Comment:** No uploaded files exist to re-serve. The app's generated downloads are delivered via `st.download_button` with explicit MIME (`text/csv`, `application/json`) as attachments — never returned as an HTML/JS response. No execution path for downloaded/served content. Control satisfied.

**Question:** Configure the web tier to serve only specific file extensions; block backups/temp/compressed files.
**Status:** Not Applicable
**Comment:** The app exposes no web tier serving static files from a directory; downloads are generated in memory, and under SiS the serving tier is Snowflake/Snowsight (not app-configurable). No file directory is exposed for extension filtering to govern.

---

## SSRF Protection Requirements

**Question:** Section directive.
**Status:** Applicable
**Comment:** Directive; item assessed below.

**Question:** Whitelist of resources/systems the server can send requests to or load data/files from.
**Status:** Applicable
**Comment:** Effectively satisfied by design. The app's **only** outbound target is the **fixed Snowflake connection**; there are **no HTTP-fetching libraries** (no `requests`/`urllib`/URL loads) and **no user-controllable URL/host**. With upload disabled there is not even an in-memory file-read of user input. Under SiS there is no external egress (data access is in-platform via the active session). Positive evidence for SAST SSRF checks; the implicit "whitelist" is the single Snowflake endpoint.

---

## File Integrity Requirements

**Question:** Section directive.
**Status:** Applicable
**Comment:** Directive; item assessed below.

**Question:** Validate files from untrusted sources to ensure they match the expected type based on content.
**Status:** Not Applicable
**Comment:** No untrusted files are ingested while upload is disabled. The retained loaders (`load_snapshot_from_json` / `load_snapshot_from_csv`) are unreachable from the UI. **Follow-up flag:** when re-enabled, add content/schema validation (the prior implementation dispatched by extension + structural parse, without magic-byte sniffing).

---

## File Execution Requirements

**Question:** Section directive.
**Status:** Applicable
**Comment:** Directive; items assessed individually. With upload disabled, no user-submitted filename/metadata is accepted at all.

**Question:** Prevent path traversal — don't use user-submitted filename metadata with system/framework filesystems.
**Status:** Not Applicable
**Comment:** No user-submitted filename metadata is accepted (upload disabled), and the app performs no filesystem operations (no `open()`/`os.path`/`pathlib`). No path-traversal surface. (When upload was active the filename was never passed to a filesystem API either — see retained behaviour.)

**Question:** Validate/ignore user-submitted filename to prevent RFI/LFI.
**Status:** Not Applicable
**Comment:** No user file/filename intake and no dynamic file inclusion from user input. No RFI/LFI surface.

**Question:** Don't use untrusted file metadata with system APIs (OS command injection).
**Status:** Not Applicable
**Comment:** No file-metadata intake, and there is **no `subprocess`/`os.system`/shell execution** anywhere in the app. No OS-command-injection surface.

**Question:** Protect against reflective file download (RFD) by validating/ignoring user filenames and setting headers.
**Status:** Applicable
**Comment:** Still in scope because the **download** feature is active. Download filenames are **app-generated**, not user-controlled: `f"{code}_row_scores.csv"`, `f"{code}_scorecard.json"`, `ml_lab_history.json` (`ui/step_06/_dp_dashboard.py:53,62`, `ui/step_07/_run_history.py`), where `code` is a catalog-constrained system code. Extensions are fixed/safe, `download_button` sets the MIME + attachment disposition, and CSV cells are sanitized against formula injection. RFD risk is low; follow-up only if user-controlled text ever feeds a download filename.

**Question:** Avoid including and executing functionality from untrusted sources.
**Status:** Applicable
**Comment:** Satisfied at the app layer: there is no `eval`/`exec`/`pickle`/`yaml.load`/dynamic import, and no untrusted content is parsed or executed (upload disabled; the retained loaders are unreachable and only ever parse JSON/CSV as data). The remaining "untrusted source" angle is **third-party dependencies** — PyPI locally and the Snowflake Anaconda channel (`environment.yml`) in SiS; **report-only SCA + secret scanning now run in CI** (`.github/workflows/security.yml`), with the enterprise scan (JFrog Xray on the Anaconda set) as the residual follow-up. Tracked in the Architecture/SiS notes.

---

## File and Resources Security requirements

**Question:** Section directive.
**Status:** Applicable
**Comment:** Directive; items assessed individually for the current (upload-disabled) state.

**Question:** Serve non-public files through a web service or signed download link, not direct links.
**Status:** Not Applicable
**Comment:** The app serves no stored files and exposes no direct file links. Downloads are generated in memory on demand via `st.download_button` (not links to files on disk). No stored-file-serving model exists for this control to govern.

**Question:** Generate filenames for uploaded files instead of using external filenames.
**Status:** Not Applicable
**Comment:** No uploads are accepted (feature disabled), so no upload filenames are handled or stored. (Download filenames are app-generated regardless.) Re-evaluate when upload is re-enabled — note uploads were never persisted, so storage filenames were not created.

**Question:** Store newly uploaded files in an inaccessible location until validated.
**Status:** Not Applicable
**Comment:** No uploads are accepted. (When previously active, uploads were held in memory only and parse-validated before use — no accessible storage location existed.) Re-evaluate on re-enable.

**Question:** Use third-party malware scanners to scan uploaded files.
**Status:** Not Applicable
**Comment:** No uploads to scan while the feature is disabled. **Follow-up flag:** re-evaluate malware scanning when the upload/auto-persist feature is re-enabled (it was an open gap when upload was active).

**Question:** Validate that uploaded files match expected formats and their file extensions.
**Status:** Not Applicable
**Comment:** No uploads are accepted. The retained loaders enforce structural checks (JSON Step-6 schema; CSV requires `_row_score`) but receive no UI input today. **Follow-up flag:** when re-enabled, restore/extend format + extension validation (and consider content-type sniffing).
