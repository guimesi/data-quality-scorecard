## File Storage Requirements

**Section directive.**
Status: Applicable
Comment: Directive; items assessed individually for the current (upload-disabled) state.

**Store files from untrusted sources outside the web root, with limited permissions and strong validation.**
Status: Not Applicable
Comment: App accepts no files from untrusted sources (upload disabled) and performs no filesystem writes. Re-evaluate strong validation when the snapshot feature is re-enabled.

**Scan files from untrusted sources with antivirus scanners.**
Status: Not Applicable
Comment: No untrusted files are accepted while upload is disabled, so nothing to scan. Follow-up: re-evaluate AV/malware scanning when upload is re-enabled (it was an open gap when active).

## File Upload Requirements

**Section directive.**
Status: Applicable
Comment: Directive; upload feature is disabled, so the items below are Not Applicable pending rework.

**Prevent acceptance of large files that could fill storage / cause DoS.**
Status: Not Applicable
Comment: No upload path exposed (`st.file_uploader` removed). Re-evaluate (set explicit `server.maxUploadSize`) if/when upload is re-enabled.

**Enforce file size quotas and max number of files per user.**
Status: Not Applicable
Comment: No upload path exposed; no per-user file intake. Re-evaluate quotas when the feature is re-enabled.

**Check compressed files for "zip bombs".**
Status: Not Applicable
Comment: No upload path, and even when active only `json`/`csv` were accepted (no archives/decompression). No zip-bomb vector now or previously.

## File Download Requirements

**Section directive.**
Status: Applicable
Comment: Directive; the download capability remains active, so these items are still in scope.

**Ensure direct requests to uploaded files are never executed as HTML/JavaScript.**
Status: Applicable
Comment: No uploaded files exist to re-serve. Generated downloads are delivered via `st.download_button` with explicit MIME as attachments, never as HTML/JS responses. Control satisfied.

**Configure the web tier to serve only specific file extensions; block backups/temp/compressed files.**
Status: Not Applicable
Comment: No web tier serves static files from a directory; downloads are generated in memory and the serving tier is not app-configurable. No file directory exists for extension filtering to govern.

## SSRF Protection Requirements

**Section directive.**
Status: Applicable
Comment: Directive; item assessed below.

**Whitelist of resources/systems the server can send requests to or load data/files from.**
Status: Applicable
Comment: Satisfied by design: the only outbound target is the fixed Snowflake connection, with no HTTP-fetching libraries and no user-controllable URL/host. The implicit whitelist is that single endpoint.

## File Integrity Requirements

**Section directive.**
Status: Applicable
Comment: Directive; item assessed below.

**Validate files from untrusted sources to ensure they match the expected type based on content.**
Status: Not Applicable
Comment: No untrusted files are ingested while upload is disabled; the retained loaders are unreachable from the UI. Follow-up: when re-enabled, add content/schema validation (prior impl lacked magic-byte sniffing).

## File Execution Requirements

**Section directive.**
Status: Applicable
Comment: Directive; with upload disabled, no user-submitted filename/metadata is accepted at all.

**Prevent path traversal — don't use user-submitted filename metadata with system/framework filesystems.**
Status: Not Applicable
Comment: No user-submitted filename metadata is accepted, and the app performs no filesystem operations. No path-traversal surface.

**Validate/ignore user-submitted filename to prevent RFI/LFI.**
Status: Not Applicable
Comment: No user file/filename intake and no dynamic file inclusion from user input. No RFI/LFI surface.

**Don't use untrusted file metadata with system APIs (OS command injection).**
Status: Not Applicable
Comment: No file-metadata intake, and there is no `subprocess`/`os.system`/shell execution anywhere. No OS-command-injection surface.

**Protect against reflective file download (RFD) by validating/ignoring user filenames and setting headers.**
Status: Applicable
Comment: Download feature is active but filenames are app-generated from a catalog-constrained code, with fixed extensions, MIME/attachment disposition, and CSV cells sanitized. RFD risk low; follow up only if user-controlled text ever feeds a download filename.

**Avoid including and executing functionality from untrusted sources.**
Status: Applicable
Comment: No `eval`/`exec`/`pickle`/`yaml.load`/dynamic import, and no untrusted content is parsed or executed. Residual angle is third-party dependencies; report-only SCA + secret scanning run in CI, with enterprise scan as the follow-up.

## File and Resources Security requirements

**Section directive.**
Status: Applicable
Comment: Directive; items assessed individually for the current (upload-disabled) state.

**Serve non-public files through a web service or signed download link, not direct links.**
Status: Not Applicable
Comment: App serves no stored files and exposes no direct file links; downloads are generated in memory on demand via `st.download_button`. No stored-file-serving model exists for this control to govern.

**Generate filenames for uploaded files instead of using external filenames.**
Status: Not Applicable
Comment: No uploads are accepted, so no upload filenames are handled or stored (download filenames are app-generated regardless). Re-evaluate when upload is re-enabled.

**Store newly uploaded files in an inaccessible location until validated.**
Status: Not Applicable
Comment: No uploads are accepted; when previously active, uploads were held in memory only and parse-validated, with no accessible storage location. Re-evaluate on re-enable.

**Use third-party malware scanners to scan uploaded files.**
Status: Not Applicable
Comment: No uploads to scan while the feature is disabled. Follow-up: re-evaluate malware scanning when upload is re-enabled (it was an open gap when active).

**Validate that uploaded files match expected formats and their file extensions.**
Status: Not Applicable
Comment: No uploads are accepted. Retained loaders enforce structural checks but receive no UI input today. Follow-up: when re-enabled, restore/extend format + extension validation and consider content-type sniffing.
