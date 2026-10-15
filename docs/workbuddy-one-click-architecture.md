# WorkBuddy managed installation design

Status: proposed. The current connector requires an existing Python/uvx
environment and an initialized profile. It is not a zero-configuration product.

## Compatibility objective

Keep the Python Runtime as the sole implementation of memory operations.
Preserve the four MCP tools, their schemas, fixed scope, deterministic IDs,
collection identity checks, WriterLease, durable ledger and recovery rules.
Existing Hermes, Python MCP, Codex, OpenCode and Pi configuration must retain
its behavior. New managed installation features must be opt-in.

## WorkBuddy capabilities

The [official connector specification](https://open.workbuddy.cn/docs/connector)
documents the following capabilities. Documentation support does not establish
successful installation in a particular WorkBuddy client.

| Capability | Documented behavior | Consequence |
| --- | --- | --- |
| MCP runtime | stdio supports managed Node.js, from WorkBuddy 5.0.0 | A Python MCP cannot request managed Python directly |
| npm registry | `npmRegistry` and ordered `npmRegistries` apply with the Node runtime | Mirror selection does not replace artifact integrity checks |
| Environment | `env` accepts credential placeholders; `staticEnv` supplies fixed values | Secrets belong in credential fields, never static values |
| Pre-authentication | Top-level `preAuth: "cli"` invokes the adjacent CLI authentication flow | It is not a documented general-purpose provisioning hook |
| CLI runtime | Managed Python and isolated pip installation, from 5.0.0 | CLI installation can avoid a preinstalled Python |
| CLI lifecycle | Installation, authentication, read-only status and logout | Current memory CLI needs an adapter before this is a complete integration |
| Token form | `auth_mode: "token"`, text/password fields, `required`, `defaultValue` | Optional fields and defaults are documented; dynamic selectors are not |
| Credential injection | Case-sensitive `${VAR}` references in stdio `env` | Form keys and placeholders must match exactly |
| Credential storage | Token credentials remain on the user's computer | Do not copy credentials into generated profiles or launch arguments |
| Connection timeout | MCP connection defaults to 30 seconds; requests should respond within 30 seconds | Downloads cannot simply block initialization indefinitely |
| CLI timeouts | init: 5 minutes; auth/status: 10 seconds; logout: 30 seconds | Long model preparation cannot be hidden inside authentication/status |
| Installation lifecycle | CLI installation is documented | A separate MCP provisioning/upgrade hook is not documented |
| Packaging | One integration approach and one MCP server per connector | Keep local and Cloud variants independently valid |

CLI authentication expects an HTTPS authentication URL. Status must be
side-effect free and survive process restarts. Neither should be repurposed as
a model downloader. The specification says WorkBuddy does not migrate or clean
CLI-owned credential files. Full uninstall, update and disconnect behavior for
all program/data directories still requires client verification.

## Architecture comparison

All timings below are requirements or estimates, not measured installation
results. Total download and installed sizes must be measured per platform.

| Property | A: managed Node bridge to Python | B: native Node Runtime | C: managed Python CLI + Skill | D: hosted remote MCP |
| --- | --- | --- | --- | --- |
| First installation | Node, verified Python/bootstrap, wheels, model, private profile | Node, new storage engine, model, profile | Python, pip dependencies, model, private profile | Service account and remote authorization |
| User input | None for local; URL/key for Cloud | Same as A | None for local if no-auth lifecycle works; Cloud configuration unresolved | Service credentials; possibly database credentials |
| External account | Not for local | Not for local | Not for local | Usually required |
| Preinstalled tools | None intended | None intended | None according to CLI runtime documentation | None locally |
| Cold start | Downloads dominate; requires staged readiness | Model download still dominates | Installation must fit five minutes | Service provisioning and network |
| Warm start | Target connection below 30 seconds; measure | Target below 30 seconds; measure | Status below 10 seconds; measure | Network-dependent |
| Download/storage | Python + wheels + model; hundreds of MB or more | Node dependencies + model | Python + wheels + model; similar to A | Small local footprint; server storage required |
| Platforms | Platform-specific Python and ONNX artifacts; unverified | ONNX/storage support needs independent verification | Managed Python is documented; real clients still unverified | Browser/network compatible; local backends are difficult |
| Security cost | Bootstrap verification, extraction safety and process ownership | New implementation of all storage invariants | Installation and CLI lifecycle verification | Tenant isolation, credential custody and service operations |
| Maintenance | Moderate to high; bounded adapter over shared core | Highest code duplication | Lower core cost; different interaction contract | Ongoing service operations |
| Runtime reuse | Full memory core | Limited without a Python backend | Full memory core | Full memory core on server |
| Existing data | No automatic reuse or migration | Cross-implementation contract tests required | No automatic reuse or migration | Explicit migration/connection required |

Recommendation: develop reusable Python setup and local embedding capabilities,
then evaluate A as the preferred MCP installation route. A is **not selected
for production** until cold installation and process-lifecycle tests pass on
the advertised platforms. Do not start a second memory implementation or a
credential-hosting service to bypass installation problems.

C is the fallback candidate for a separate local connector, conditional on a
real no-auth connection test and installation timing. It does not establish a
Cloud Token workflow. B and D are not recommended for this release.

### First usable path: an explicitly selected Ollama model

Keep the existing Ollama path usable while managed installation is evaluated.
An operator who already has Ollama and an embedding model should not need a
second model download. Guided setup should accept an explicit profile, endpoint
and model, probe embedding support/dimensions, then initialize only the newly
authorized storage. It must not scan or change existing agent profiles, select
an arbitrary installed model, or change an existing collection's fingerprint.

When Ollama is unavailable, distinguish missing executable, stopped/unreachable
service and missing/unsupported model where reliable probes allow it. Provide
the official OS installation link, service-start instructions or the exact
model pull command as appropriate. Downloads/installations require an explicit
user action; do not silently install Ollama or switch to a cloud provider.
Keep these diagnostics generic so other agents can use the same setup path.

The current manual steps are documented in the [Ollama quickstart](quickstart.md)
and [Chinese quickstart](quickstart.zh-CN.md). Guided setup is proposed, not
implemented. Requiring Ollama remains a guided configuration path, not local
zero-configuration acceptance. The optional CPU provider remains a separate
way to remove that prerequisite after its own validation.

### The cold-start decision gate

A transparent stdio launcher cannot complete MCP initialization while Python
and the model are unavailable. Managed Node alone does not solve that problem.
No generic pre-install hook has been established for the MCP route.

An experiment may evaluate a small Node MCP transport adapter that initializes
promptly while preparing the backend asynchronously. It must use tool schemas
generated from the pinned Python implementation, preserve protocol semantics,
and return bounded, non-success setup responses until the backend is ready.
It must never queue a memory write before readiness or report a successful save
without Runtime confirmation. Protocol initialization is not storage readiness.
This is more complex than transparent stream forwarding and needs explicit
protocol, cancellation, shutdown and cross-platform testing before adoption.

If this adapter cannot provide a clear ordinary-user workflow within actual
WorkBuddy time limits, keep A blocked and validate C independently. Increasing
timeouts or misusing pre-authentication is not an acceptable substitute.

## Shared implementation boundaries

1. **Runtime:** an optional CPU embedding provider and explicit managed-profile
   setup API. Neither changes existing defaults nor introduces WorkBuddy
   dependencies into Hermes or the Python MCP path.
2. **Managed launcher:** verified dependency preparation, process ownership,
   stable client-specific paths and readiness. No direct Qdrant writes and no
   duplicate ledger, scope or recovery implementation.
3. **WorkBuddy packaging:** platform runtime declaration, local/Cloud presets,
   Token form mapping, bilingual metadata and canonical Skill resources.
4. **Canonical Skill:** shared explicit search/save/update/delete guidance,
   accurate search-result IDs, sensitive-data rules and safe backend failures.
   WorkBuddy does not acquire Hermes automatic extraction or prefetch.

## Local embedding candidate

[FastEmbed's supported model list](https://qdrant.github.io/fastembed/examples/Supported_Models/)
includes `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, with
384 dimensions, Apache-2.0 licensing and an approximate model size of 0.220 GB.
This is a candidate, not a validated default. Tokenizer and other dependencies
increase total disk/network use; Chinese/English retrieval quality needs testing.

Pin the provider package, model artifact revision, tokenizer and file hashes.
Use CPU ONNX inference without remote model code. Include artifact identity,
pooling, normalization and query/document preprocessing in the new provider's
fingerprint. Existing provider fingerprints must remain byte-for-byte stable.
Do not infer compatibility from dimensions alone.

Prepare files in a temporary directory, verify every required file, then publish
a completion marker atomically. A failed download remains unready and retryable.
Do not delete another version's model cache. Warm startup should work offline
after preparation. Local text must not be sent to remote embedding services.

Package wheel availability is only a prerequisite. Check macOS Apple Silicon,
macOS Intel, Windows x64, Linux x64 and any advertised ARM64 variant separately;
do not claim a platform merely because Python itself runs there.

[uv](https://docs.astral.sh/uv/guides/install-python/) can prepare managed Python
using Astral's python-build-standalone distributions. A bridge must still pin
and verify both bootstrap and Python artifacts; piping a remote installer into
a shell is not part of this design. Use versioned private environments without
administrator privileges or system package installation.

## Profiles, credentials and lifecycle

Use separate application-managed program, model cache and data roots. Proposed
managed roots follow each OS's conventions: Application Support/Caches on macOS,
LOCALAPPDATA on Windows, and XDG data/cache directories on Linux. Within them:

| Directory | Purpose | Update behavior |
| --- | --- | --- |
| `programs/<version>/<platform>/` | Python, installed wheels and launcher state | Install beside the previous version; switch after verification |
| `models/<artifact-id>/` | Verified model/tokenizer files | Shared read-only cache; retain old versions |
| `profiles/<client>/<mode>/` | Non-secret configuration and setup ownership marker | Stable across upgrades; never inherit another client profile |
| Profile-local backend and ledger paths | Existing Runtime storage layout | Preserve names and semantics; never reset during setup |
| `downloads/<transaction>/` | Unverified temporary downloads | Never execute before verification |

These are proposed managed paths, not replacements for existing user profiles.
WorkBuddy local and Cloud profiles are distinct. Other clients can explicitly
opt into the same generic setup API with separate client identities. Existing
Hermes and standalone profiles are neither discovered nor imported implicitly.

Setup must acquire its own provisioning lock and the Runtime's applicable
WriterLease before storage initialization. Never remove another process's lock.
Write configuration atomically, record the intended ownership before backend
creation, and allow retry only for that same intended target. Existing or
partially initialized unrelated profiles require operator action. Never invoke
reset, delete, collection replacement or implicit migration.

For Cloud, use a separate Token connector with HTTPS URL, password API key, and
an explicit new-storage authorization field. A local CPU embedding default can
avoid a second credential; an optional remote embedding preset requires its
own complete credential mapping. Validate endpoint, dimensions, fingerprint,
collection identity and scope before reporting readiness. A connection or
schema error must leave existing collections untouched. Explain the exact new
collection being authorized; submitting credentials alone is not consent to
initialize an arbitrary existing collection. Prefer collection-scoped keys.

WorkBuddy retains Token credentials. Profiles contain only environment-variable
references; the necessary backend receives secrets through its environment.
Downloader and installer subprocesses must not inherit service keys. Redact
errors and keep all non-protocol output off MCP stdout.

Upgrade and rollback switch program versions while retaining data. Each version
must reject an incompatible profile safely. An old program must never rewrite a
newer ledger to make rollback succeed. Disconnect/uninstall adapters must not
delete profiles, collections, ledgers or models. Data erasure remains an explicit
operator action outside the four conversational memory tools.

## Release conditions

Publish shared Runtime additions first, then pin them in MCP/launcher releases,
then build connectors from fixed code and canonical Skill revisions. Keep
deterministic ZIPs, hashes and existing release guards. Never change published
tags. No new package or marketplace publication follows from this proposal.

Before release, complete the checks in
[the validation checklist](workbuddy-one-click-validation.md). Marketplace ZIP
import, backend readiness and real CRUD/restart acceptance are separate results.
Do not advertise one-click installation until all required stages pass.
