# Security policy

## Reporting a vulnerability

Do not post credentials, private prompts or exploit payloads in public issues. Use [GitHub private vulnerability reporting](https://github.com/tanveer-arch/promptdrift/security/advisories/new) if enabled for this repository. If unavailable, ask the maintainer for a private reporting channel without disclosing the vulnerability publicly. This volunteer project does not promise a response-time SLA.

Security fixes target the latest published release and the development branch. There is no promised long-term-support branch. The monitoring changes in 0.4.0 are unreleased; this document is not a third-party security audit.

## Boundaries

- **Providers receive prompts.** OpenAI-compatible/Ollama adapters send rendered text to the configured endpoint. Use HTTPS outside trusted loopback/local networks. Treat `base_url`, config files, templates and dependencies as trusted operator inputs; do not run arbitrary PR configuration with provider credentials.
- **Keys come from environment variables.** YAML selects the variable name, not the credential. Safe provider errors do not include HTTP bodies. Do not put credentials in URLs, model names, IDs, assertion labels or other metadata.
- **Monitoring reports are minimized.** `monitor` JSON/history exclude raw prompts, responses, contract values and exception bodies. They still contain case/model names, timestamps, paths and diagnosis facts. Review metadata before uploading publicly.
- **Legacy exports contain raw evidence.** `test/check/diff --json` and HTML reports can include rendered prompts, provider output, expected values and evaluator details. Treat them as sensitive. Legacy local stored reports suppress these payloads by default; `baseline.store_raw_output: true` explicitly retains them.
- **Capture is a separate opt-in boundary.** Review `CaptureConfig`, sampling, redaction and storage policy before recording traffic. Pattern-based redaction cannot guarantee PII removal. Never assume a learned scenario is safe to commit merely because it came from capture.
- **Hashes are not encryption/anonymization.** Baselines contain hashes and metadata rather than raw answers. Small/predictable strings can be guessed; repository access controls still matter.
- **Storage is local, not encrypted.** OS filesystem permissions and CI artifact permissions/retention are your responsibility. Monitoring retains 1,000 local reports. `purge` clears the legacy store, not project monitor databases/archives; deletion is not secure erasure.
- **Templates are sandboxed, not a resource quota.** Jinja's sandbox and strict undefined variables reduce capability exposure, but untrusted templates/regexes/large schemas can consume CPU or memory. Run untrusted workloads in isolated processes/containers without secrets.
- **JSON schema validation is offline.** Nonlocal `$ref`/`$dynamicRef`/`$recursiveRef` are rejected and the evaluation registry cannot retrieve remote resources. Review schemas nevertheless; this is not protection against every resource-exhaustion case.

## GitHub Actions

The composite Action rejects `pull_request_target` execution, passes inputs as environment variables/argument lists rather than interpolated shell code, and suppresses raw stderr/error payloads. Credential-value redaction in the Action is defense in depth, not arbitrary PII detection. Check-mode artifacts may still contain application content.

PR comments are limited to same-repository pull requests. Optional failure issues are limited to scheduled/manual monitor runs, use fixed marker scopes and require `issues: write`. Use the documented concurrency group to avoid simultaneous initial issue creation. A GitHub token or provider key must never be exposed to untrusted PR code—even same-repository contributors need appropriate trust controls.

Pin reviewed Action revisions and package versions. The Action's optional installation executes the configured package's build/install code; only the workflow maintainer should control that input. Keep paid schedules opt-in and apply job timeouts and artifact-retention policies.

## Reportable concerns

Credential leaks, unexpected private-data retention, unsafe CI publication, sandbox escapes, remote schema retrieval and exploitable dependency flaws are in scope. Provider-side vulnerabilities and an LLM's own susceptibility to prompt injection are outside this repository's implementation boundary, though PromptDrift can help author behavioral checks for an application's requirements.
