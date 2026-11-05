# Runtime availability

This skill supplies instructions. The shared [Qdrant memory backend](https://github.com/cnkang/hermes-plugin-qdrant-memory) supplies storage, embeddings, scope, ledger, ownership and recovery. Its repository name preserves the original Hermes plugin distribution. The standalone CLI and stdio MCP do not require Hermes.

The private compatibility examples pin Runtime 0.2.2 and MCP distribution 0.1.3,
the verified private compatibility baseline for this skill. These minimum
versions do not provide the Runtime 0.5.0 Owner controls. This skill targets
Runtime 0.6.0. Its `mcp` extra provides the standalone stdio server directly.
The optional metadata-only [MCP distribution](https://pypi.org/project/qdrant-memory-mcp/)
is versioned independently; verify its PyPI release before installing an exact
version. The installer accepts an installed Runtime that is at least the
requested version.

Older CPU profiles may use FastEmbed 0.9.0. Runtime 0.5.5 and later use the
0.9.1 pipeline with a different fingerprint. Keep the old environment, cache and
store for rollback. An authorized upgrade exports through the old Runtime and
re-embeds into a new profile/collection, verifies, then switches clients. Never
edit stored fingerprints or ready markers to force compatibility.

Explicit CPU model preparation in Runtime 0.6.0 allows fifteen minutes per
artifact within a thirty-minute total network budget, enforcing pinned
sizes/hashes and atomic cache publication. Managed launchers allow forty
minutes for setup. Authorize the initial model download explicitly; ordinary
memory operations do not download models.

## Install Runtime 0.6.0 for Owner controls and Codex portability

When Owner setup is explicitly authorized, select a new private environment and
request the version that provides the controls:

```bash
python3 /path/to/installed/qdrant-memory/scripts/install_runtime.py \
  --venv /private/path/qdrant-owner-env --version 0.6.0
/private/path/qdrant-owner-env/bin/qdrant-memory --help
```

This installs the CLI/MCP base. The HTTPS gateway also needs the optional remote
dependencies and operator-configured TLS and credentials. Follow the pinned
[Owner guide](universal-owner.md) before exposing it. Installing a Skill or an
older MCP distribution does not provide these controls automatically.

Runtime 0.5.2 and later classify an interrupted remote write as retryable. The
error envelope names the identifier to replay and, when the Owner sends one, the
delay before the next attempt. Replay the same request ID or event ID. Never use
a new identifier for a retry, because that can add a second record. A
`recovery_required` reason means the Owner kept the request for operator
recovery. Do not discard it.

## Recover from provider initialization failure

Runtime 0.5.5 keeps a provider unavailable after initialization fails and reports
redacted lifecycle codes instead of acknowledging an unpersisted turn or required
checkpoint. A `writer_busy` code means another process currently owns the local
WriterLease. Check the Hermes Desktop, Gateway and CLI processes or other
configured writers, let the active process shut down cleanly, and wait for its
in-flight work to finish. The OS releases its lease when the owning process closes
the lock handle; a lock file may remain. Never delete the file to force ownership.

WriterLease protects a profile and destination on the local host. It is not a
distributed lock across machines or independent profile paths. Coordinate all
writers yourself and never run two independent writers against the same
destination. If initialization failed with another code, inspect the redacted
error type and fix the named configuration, dependency or service problem without
publishing credentials or raw service responses.

Runtime allows initialization to be retried after failed-attempt cleanup finishes.
Hermes hosts that do not retry failed provider initialization need the affected
Desktop or Gateway process restarted after the competing writer exits. After
the failed host is stopped, run the configured profile's supported `doctor`
command and make an authorized scoped search for a known memory before relying
on new writes. Do not run CLI diagnostics against an embedded destination while
an active Hermes provider still owns its local Qdrant files. Allow the provider's
normal startup recovery to process pending ledger work; retry
FAILED operations only after correcting the cause and authorizing that retry.

## Private compatibility baseline

The older commands below retain the tested private-operation baseline. Use the
Owner installation above when shared policy, doctor or remote lifecycle features
are required.

```bash
uvx --from qdrant-memory-mcp==0.1.3 qdrant-memory-mcp --home /private/path/profile mcp
```

Configure and initialize the profile first. Both distribution choices share the
same Runtime. Existing Runtime installations need not switch distributions.
For direct CLI use, install Runtime in a dedicated Python 3.11+ environment:

```bash
python3 -m venv /private/path/qdrant-env
/private/path/qdrant-env/bin/python -m pip install \
  'hermes-plugin-qdrant-memory[mcp]==0.2.2'
/private/path/qdrant-env/bin/qdrant-memory --help
```

The original v0.1.0 release predates standalone interfaces. PyPI Runtime 0.2.0
includes them. Version 0.2.1 fixes highly similar explicit adds without an LLM.
Runtime 0.2.2 supports MCP Python SDK 1.x and 2.x (`mcp>=1.30,<3`).
No prerelease selector is required. The four tools and stdio launch arguments
are the same for both SDK majors.

If your private environment specifically requires SDK 2.x, install both
constraints together:

```bash
/private/path/qdrant-env/bin/python -m pip install \
  'hermes-plugin-qdrant-memory[mcp]==0.2.2' 'mcp>=2,<3'
```

For SDK 1.x use `mcp>=1.30,<2` instead. This selects the server process's Python
SDK. A client running in another process can use its own compatible SDK.
`npx skills` distributes instructions and the bundled installer, not Python
dependencies. Do not install dependencies or change settings merely on skill load.

## Install a missing backend

When setup is authorized and neither compatible MCP tools nor a working CLI is
available, the agent can run the installed skill's [installer](../scripts/install_runtime.py):

```bash
python3 /path/to/installed/qdrant-memory/scripts/install_runtime.py \
  --venv /private/path/qdrant-env --version 0.6.0
```

Use the actual installed skill path reported by `npx skills` (global Codex usually
uses `~/.agents/skills/qdrant-memory`). Python 3.11+ must be available.
Default installation requires PyPI access. Optional source installation also needs Git/GitHub. On Windows use
`py -3.11` or an available newer Python and the returned `Scripts` executable.
For a new Windows environment, use Python 3.11.10+, 3.12.4+, or 3.13+.
Earlier builds do not apply the private directory ACL required by the installer.
Use a parent directory controlled by your account. The installer rejects granting
macOS ACL entries and Windows write grants to other accounts before it creates
or runs the environment. It does not change the parent directory's ACL.
The installer installs an exact PyPI version with its official MCP SDK in a new
venv, then verifies package version, imports and CLI. A matching existing environment
is reused without an upgrade. An incomplete or different-version environment fails
and is retained, with a suggestion to choose a new private environment.
Choose a new path to retry rather than deleting another installation.
Use a new private environment for an authorized Runtime upgrade. Back up the
profile and destination, and retain the same scope. Reuse the collection only
when the embedding pipeline is unchanged. For FastEmbed 0.9.0 to 0.9.1, use the
new profile and collection procedure above.
For an explicitly authorized candidate/development/fallback source, use
`--version 0.6.0 --revision FULL_40_CHARACTER_SHA`. The installer verifies both
version and VCS commit. A moving `main` or short SHA is rejected. Source installs
are optional and never the production default. Never silently fall back from PyPI.
The immutable Runtime 0.6.0 release commit is
`dee6777432f17523db75f6be32cf3ef15e48235c`; CI's current-release acceptance
installs published Runtime 0.6.0 from PyPI and exercises the default installer
path. The standalone compatibility lane retains Runtime 0.2.2 at commit
`c85d2bce788b117dddd854bb124971f7de8e564c`. The published release tag is the
source of truth.
For Hermes users, the pin preserves transcript-author isolation across restarts.
Unknown historical attribution disables whole-transcript supplementary extraction
until an explicit fresh transcript reset. Attributed per-turn writes continue.

On POSIX, choose an ordinary private path. Spaces are supported. Interpreter
links preserve managed Python's shared-library lookup. Windows uses copies
without requiring symlink privileges. Shell
metacharacters and control characters are rejected before installation. pip's
generated CLI entrypoint may use a shell wrapper, so unsafe interpreter paths
must be rejected even though the installer passes subprocess arguments as lists.

Use the returned absolute `command` for CLI and MCP configuration. This does not
install Hermes, change an existing Hermes plugin, download embedding models,
initialize storage or write any agent's MCP settings. Configure the authorized
profile and verify service readiness separately below. Installing dependencies
does not grant permission to import or save memories.

Choose an operator-authorized private profile. Any non-loopback embedding
`base_url` must use HTTPS even when no `EMBEDDING_API_KEY` is configured: memory
text crosses that endpoint. Loopback HTTP (`127.0.0.1`, `localhost`, `[::1]`)
remains supported. Its `qdrant-memory.json` uses existing backend fields:

```json
{
  "scope": {"user_id": "local-user", "agent_id": "my-agent"},
  "qdrant": {"mode": "embedded", "collection": "qdrant_memory"},
  "embedding": {
    "provider": "ollama",
    "model": "qwen3-embedding:4b",
    "base_url": "http://127.0.0.1:11434",
    "dimensions": 2560
  }
}
```

Select an available embedding service and its actual dimensions. This example does not install Ollama or download models. OpenAI-compatible embeddings and server/cloud Qdrant are also supported. Keep credentials in runtime environment variables, outside skill text and URLs.

```bash
qdrant-memory --home /private/path/profile init
qdrant-memory --home /private/path/profile doctor
qdrant-memory --home /private/path/profile search --query 'review preferences'
```

Initialize only an authorized target. `--help` proves interface availability, not service readiness. Connect MCP through [agent setup](agent-setup.md), or use the supported standalone CLI. Never substitute private Python calls or direct Qdrant access.

Existing Hermes users can retain their MemoryProvider and `hermes qdrant-memory` maintenance/migration commands. Follow [Hermes setup](https://github.com/cnkang/hermes-plugin-qdrant-memory#readme) for that integration. Automatic extraction and prefetch remain Hermes lifecycle features. Standalone exposes explicit operations.

MCP and CRUD use one fixed operator-configured profile scope. MCP client names and model arguments cannot select identities. Separate users' profiles and process credentials. Operator maintenance can select broader scopes. Check every selector. Embedded storage requires exclusive access. WriterLease coordinates a profile's writers, not distributed writers across independent profiles.


## Hardened installation options

Choose a user-owned private venv and parent directory. The installer rejects a
symlink venv and, on POSIX, an existing selected directory or nearest existing
parent writable by group/other users. New venv roots use mode 0700. Existing
unsafe permissions are rejected rather than changed. Windows requires a private
inherited ACL. These checks are not an OS sandbox against concurrent changes.

Installation ignores ambient pip configuration (`PIP_CONFIG_FILE` is the null
device). Service credentials are not passed to installation subprocesses. For a
reviewed release dependency set, pass `--requirements-lock /absolute/path/lock.txt`.
The trusted lock must cover the requested Runtime with its MCP extra and every
transitive dependency using exact versions and SHA256 hashes. This enables pip
`--require-hashes --only-binary=:all:`. Missing hashes or unavailable wheels fail
closed. No fallback to a source build is attempted. This option cannot be combined
with `--revision`. Explicit immutable source installation remains a separate
operator-authorized development route. Existing environments are verified without
reinstallation, so this flag does not retroactively certify their bytes.

New installations default to Runtime 0.6.0. Runtime 0.2.2 remains the tested
private-compatibility baseline in explicit examples and CI fixture pins. Runtime
0.4.0 adds the separately configured shared owner. Use Runtime 0.5.0 or later for
protected policy, doctor and remote Owner features, and discover its schemas before
registering a shared bridge. Do not apply private-profile examples as shared
service setup or silently upgrade an existing installation.
