# Desktop-only threat model and evidence

Status: engineering review draft, 2026-11-06. This describes the current
source candidate and known protections; it is not a security certification.

## Assets and trust boundaries

- User memories, Profile configuration, Qdrant collections, SQLite operation
  ledger, WriterLease state and export files.
- Qdrant URL/API key, embedding API key, Shared Owner URL/token and Codex
  profile-selection settings.
- Codex native-memory source files, migration manifests and imported content.
- Plugin archive, MCP server, Runtime/wheel artifacts and the optional CPU
  model files.
- Untrusted inputs: prompts, MCP tool arguments, retrieved memory text,
  imported files, archive paths, dependency registries and model downloads.

The agent can request the four ordinary memory tools. The plugin process owns
the configured profile and Runtime. Qdrant and embedding services are either
local or explicitly configured external endpoints. Plugin installation and
runtime data use separate roots. The source package has no session-capture
hook.

## Threats and current controls

| Threat | Current control / evidence | Remaining release work |
|---|---|---|
| Prompt injection embedded in a recalled memory | Retrieved text is data; skills do not grant it authority. There is no automatic session capture or lifecycle hook. | Add an explicit adversarial retrieval case to the exact candidate review run. |
| MCP parameter injection or oversized input | Four fixed tool schemas; additional properties rejected; Runtime validates tool arguments and bounds before store access. Exact-ID mutations resolve the ID inside caller scope first. | Run the candidate's negative MCP tests against the exact Desktop bundle. |
| Scope escape or ID enumeration | Scope is fixed by operator configuration, not caller arguments. Update/delete require an exact ID found within scope. | Record real cross-scope attempts and non-disclosure result in the reviewer evidence. |
| Malicious import path, symlink, reparse point or archive traversal | Runtime migration and package builders use no-follow and path checks; archive tests reject unsafe source members and replacement races. | Run Windows Reparse Point and hostile ZIP tests on Windows; current Desktop ZIP is not built. |
| Secret exposure in process args, logs or archive | Shared Owner token is passed by environment name; launcher sanitizes errors; Codex CLI masks env values. Current source builder hashes immutable files. | Audit Creator-normalized package and the final candidate ZIP with secret scanners; no Creator upload means this boundary is not verified. |
| Local/Cloud data-flow confusion or silent Cloud fallback | CPU embedding is explicit; model absence raises an error; Ollama/OpenAI-compatible providers require explicit configuration. No silent provider switch. | Validate first-run UI/skill language and log redaction in the actual Desktop client. |
| Model substitution or partial cache | Runtime pins HTTPS repository/revision, exact artifact sizes and SHA-256; writes to a private staging directory and publishes atomically under a lock. Online download/hash verification and offline cached CPU inference passed on macOS arm64. | Confirm interrupted-transfer, timeout, low-disk recovery and unsupported-CPU behavior. Runtime currently has no explicit preflight free-space threshold. |
| Dependency or Runtime replacement | Release manifest pins Runtime source commit and MCP distribution. Launcher verifies installed MCP version and same-environment executable binding. | Desktop-only package still lacks complete platform wheel lock, bundled Python, SBOM and per-binary hashes. |
| Concurrent writers, interruption or shutdown data loss | Runtime has SQLite ledger, recovery and WriterLease. Windows drain issue #115 keeps retries disabled and reports worker/ledger diagnostics. | Root cause and failure-path durability are unverified; do not claim release readiness. |
| Upgrade/uninstall damages data | Existing Marketplace uninstall tests report data preservation; user data is stored outside the plugin source tree. | Repeat install/upgrade/rollback/disable/uninstall with the final Desktop ZIP and a fresh isolated profile on each supported OS. |

## Safe defaults and limits

- Local embedded Qdrant and CPU embedding are recommended for a new isolated
  Profile; no cloud fallback is performed.
- Cloud Qdrant, Ollama, OpenAI-compatible endpoints and Shared Owner require
  explicit configuration and credential supply.
- Memory text is untrusted content. It must not be treated as instructions.
- Destructive operations use the existing scoped exact-ID delete tool; no
  maintenance or bulk-delete tool is exposed.
- Codex native memory import is read-only. Export means
  `HANDOFF_PENDING`, not native adoption. The plugin does not edit Codex's
  generated databases.
- No telemetry or automatic session capture is declared by the source package.

## Release decision

The current source design has meaningful local protections, but Desktop-only
release security remains **NOT VERIFIED** until Creator normalization, the
complete package, Windows and macOS clean-install coverage, dependency/SBOM
inspection, and the #115 drain recovery gate are complete.
