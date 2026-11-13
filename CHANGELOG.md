# Changelog

## Unreleased

- Release MCP distribution 0.3.3 with the public Runtime 0.6.2 pin. This fixes
  the dependency mismatch in 0.3.2; MCP schemas, tools and stored data remain
  unchanged.

- Prepare Codex plugin 0.1.4 (not published): pin MCP distribution 0.3.3,
  Runtime 0.6.2 and Skill 0.4.3 (snapshot `skills-20261113.1`). The plugin's
  `requirements.txt` now installs exact public PyPI releases instead of a
  Runtime Git commit, so installation no longer needs Git or a source build;
  `release.json` keeps the source commits as provenance.
- Move OpenAI presentation, onboarding and the Codex MCP server mapping with
  its eight-name `env_vars` allowlist from root `plugin.json` into
  `.codex-plugin/plugin.json`. A root `extensions.com.openai` object replaces
  that overlay entirely, so the package validator now rejects one.
- The real-CLI end-to-end lane parses `codex mcp get --json` and requires
  `transport.env_vars` to equal the allowlist exactly (names only, never
  values). Required Codex lanes stay on Node 22, Python 3.11 and Codex CLI
  0.167.2; a manual compatibility probe can select Node 24, Python 3.14 or
  Codex CLI 0.165.0. Both end-to-end lanes install uv from a hash-locked
  requirements file.
- Desktop runtime locks compile from the release's Runtime source commit with
  a host-independent header. The builder verifies the checked-out commit and
  wheel version, checks the Runtime wheel's SHA-256 before an offline install,
  applies one exact check to the lock's Runtime entry for both `--wheelhouse`
  and `--verify`, and refuses to overwrite a different same-name wheel in an
  existing wheelhouse.
- DSH native adapter: stop queued captures as soon as auto-capture is
  disabled; the unresolved turns replay on the next resume.

- Harden the lifecycle auto-capture preview per review: HTTPS-only non-loopback
  extraction endpoints, `--confirm` required before staged text reaches any
  remote provider, broader secret-shaped candidate refusal (bearer tokens,
  GitHub/Slack tokens, PEM blocks, `password=`), locked pending-capacity and
  admission sequences (unique temp files, prune rechecks, overwrite-at-capacity
  idempotence), session-level pairing when `turn_id` is absent, content-free
  capture diagnostics, durable extraction receipts (rejections, replacement
  outcomes, record IDs preserved across retries, errors cleared on success),
  stale-snapshot admission guard, response size cap and quarantine of
  unreadable pending events.

- Add a credential-free real-Codex-CLI end-to-end lane
  (`scripts/codex_plugin_e2e.py`, CI job `lifecycle-e2e`): isolated `CODEX_HOME`
  installs from both the repository marketplace and the exact rebuilt ZIP,
  verifies the eight overlay environment names through `codex mcp get --json`, runs
  the pinned Runtime install from the plugin requirements, and drives the
  four-tool lifecycle through the real launcher — duplicate-add idempotency,
  exact-ID update/delete, fresh-session persistence, SIGKILL recovery, scope
  isolation and post-uninstall data retention.
- Ship the optional lifecycle preview as a separate
  `integrations/codex-lifecycle` plugin (manual install only, hooks ineligible
  for the public directory): `SessionStart` recall and explicit `remember:`
  capture through the released hooks contract; no hooks in the public package.
- Generate per-platform hash-locked desktop runtime dependency locks
  (`runtime-locks/*.txt`) plus the pinned-commit Runtime wheel record, with
  offline `--require-hashes` installs verified on macOS arm64; macOS x64
  remains **NOT VERIFIED**.
- Require the `Codex plugin` workflow for tagged releases in the release
  gate, and add launcher/regression tests for a runtime venv missing the
  pinned MCP distribution plus real-MCP scope isolation.

### Codex plugin readiness (from this branch)

- Launch the DSH native Runtime with isolated-mode Python (`-I -S -X utf8`) from
  the interpreter directory, using a fixed bootstrap that adds the interpreter's
  site-packages (honoring `include-system-site-packages`) without processing
  `.pth` files or `sitecustomize`. Project content on the working tree,
  `PYTHONPATH`, or site startup cannot shadow the Runtime while the Owner token
  is present; the interpreter binary and its packages remain a trusted
  installation outside project control.
- Resolve a relative inherited `SSL_CERT_FILE` and each relative
  `SSL_CERT_DIR` entry against the DSH working directory before starting the
  Runtime from the interpreter directory.
- Exclude a DSH fork's inherited event prefix from recent-turn recovery, so a
  forked session captures only its own completed turns. Skip recall and capture
  for subagent sessions, require the exact `/mcp` Owner path, and expose
  in-process recall and capture counters on the plugin disposer for diagnostics.
- Run the DSH native adapter workflow on every main push and include it in the
  tag release gate; the host profile check now asserts the plugin id and all
  three default-off switches instead of only printing the config.

## 0.3.2

- Pin the MCP distribution to published Runtime 0.6.1 so the separately
  installed, opt-in Codex lifecycle preview can use the Owner `remote-event`
  candidate API. The four MCP tool schemas and stored memory format are
  unchanged; failed and quarantined Owner events remain operator-recovery-only.

## 0.3.1

- Pin managed launcher 0.1.0-rc.8 to its verified public npm integrity and
  refresh the PyPI/Registry release metadata and adapter pins. MCP tools,
  transport and persisted memory formats are unchanged.

## 0.3.0

- Pin Runtime 0.6.0 for Codex native v1/v2 inspection, authorized import and
  portable JSON/Markdown handoff, with descriptor-anchored file security on
  macOS/Linux and dedicated Windows local-volume/ACL validation.
- Keep handoff status HANDOFF_PENDING and native_verified=false until native
  client adoption is confirmed. Uninstall preserves memory, backups and originals.
- Refresh the canonical Skill to 0.4.0 and align the Codex candidate source pins.
  The GitHub-backed Codex source marketplace is versioned separately; this MCP
  release does not submit the plugin to the OpenAI public directory.
- Update managed launcher 0.1.0-rc.8 to the public Runtime wheel, official
  FastEmbed 0.9.1 and Pillow 13.0.0. Remove the temporary compatibility builder;
  retain hash locks, wheel-only installation and CPU acceptance.
- Prepare WorkBuddy connector 0.2.5 and DSH bundle 0.1.6 for the new launcher.
  Verify public npm availability and acceptance after separate npm authorization.
- Allow forty minutes for explicit profile/model preparation and sixty
  minutes for public acceptance readiness, with ninety-minute cold CI jobs.
  Retain the MCP handshake deadline and all model integrity checks.
- Validate the real Codex CLI through protected Ollama Cloud CI. Account-backed
  GPT/ChatGPT acceptance remains local; synthetic fixtures do not prove native
  memory adoption or Desktop UI behavior.

## 0.2.9

- Pin the metadata-only distribution to published Runtime 0.5.5 and its exact
  source revision. This selects the FastEmbed/Pillow compatibility patch.
- Update MCP Registry metadata, exact install examples and preparation contracts
  to MCP 0.2.9 and Runtime 0.5.5.
- MCP tools, schemas, transport, scope rules and persisted data are unchanged.
  The launcher and DSH bundle packages do not change, so no npm release is needed.

## 0.2.8

- Pin the metadata-only distribution to Runtime 0.5.4, the maintainability
  release that keeps Runtime 0.5.3 behavior and splits long functions into named
  helpers.
- Install the test dependencies of the quality, cross-harness, DSH-next and
  WorkBuddy workflows from hash-locked files, and add a SonarCloud scan to the
  repository quality workflow for the default branch and in-repository pull
  requests.
- Move the Pi host acceptance harness to `minimatch` 11.0.1 and the WorkBuddy
  lane to `uv` 0.13.6, past their published advisories.
- MCP tool schemas, stdio transport, scope rules and persisted data are
  unchanged.

## 0.2.7

- Pin the metadata-only distribution to Runtime 0.5.3, which includes the
  provider lifecycle fix for failed initialization and WriterLease contention.
- Update the exact MCP install pins and Registry metadata. MCP tool schemas,
  transport and persisted data remain unchanged.

## 0.2.4

- Select the published Runtime 0.5.0 package and its matching preparation and
  Owner CI revision. Keep one Runtime implementation and the existing stdio tools.
- Update Connector 0.2.2 and DSH bundle 0.1.3 to the Pillow 13 launcher 0.1.0-rc.4.
  Pin its exact npm integrity. Retain existing profiles and model caches.
- Align active English and Chinese installation instructions and support limits.

## Launcher 0.1.0-rc.4

- Install the public Runtime 0.5.0 wheel with its matching immutable source and
  artifact hashes. Keep existing profiles, host isolation and model caches.
- Require Pillow 13.0.0. Reuse the Runtime's hash-verified metadata-only FastEmbed
  compatibility builder, verify its output and retain dependency checks.
- Assert the installed versions in the real Linux, macOS and Windows cold-setup
  gates. Preserve their diagnostic logs on failure.

## 0.2.3

- Align Owner source CI with the reviewed Runtime main revision. Keep the
  public Runtime 0.4.0 dependency and managed launcher artifact pins unchanged.
- Update Connector 0.2.1 with the reviewed Skill 0.3.2 installer security fixes.
  Separate historical desktop and Cloud evidence from the current source pin.

- Bind the CI preparation source fallback to the canonical Runtime repository,
  disable it for pull requests, and assert the built wheel matches the pinned
  version.
- Run the Pi Owner adapter with `-I`, without `PYTHONPATH`, from a pinned
  working directory, and only with an absolute interpreter path, so host project
  content cannot shadow the Runtime that holds the Owner credential. Resolve a
  relative `QDRANT_MEMORY_CA_FILE` before the cwd change.
- Sync the DSH uvx overlay to MCP 0.2.3.

## DSH bundle 0.1.2

- Pin launcher `0.1.0-rc.3`, which installs Runtime 0.4.0. The payload and the
  configuration layer are otherwise unchanged.

## DSH bundle 0.1.1

- Widen the `@deepseek-ai/dsh-mcp-client` peer range to include the `0.2.1-rc.2`
  prerelease line. The published 0.1.0 range accepted only the `0.2.0-rc.x`
  line, so installing it beside the current `next` channel failed peer
  resolution. The bundle payload is otherwise unchanged.

## 0.2.2

- Pin Skill 0.3.1 at commit `d6062f0`. The packaged WorkBuddy connector now
  contains the shared-security guidance.
- Version references move to 0.2.2. The Runtime pin, the four tools and the
  private defaults do not change.

## 0.2.1

- Publish launcher `0.1.0-rc.3`, which installs Runtime 0.4.0. The previous
  launcher `0.1.0-rc.2` still installed Runtime 0.3.0.
- Remove the outdated "unreleased Runtime" text from the shared-service guide
  and point the install examples at the published PyPI release.

## 0.2.0

- Pin Runtime 0.4.0. The distribution now installs the opt-in authenticated
  shared owner and its stdio bridge. The private defaults and the four tool
  schemas do not change.
- Update official DSH test packages to 0.2.1-rc.2, resolving the MCP OAuth advisory through upstream Client/Core 2.2.0. Preserve both Bundle peer RC lines.
- Add a separate floating `next` compatibility probe while retaining exact, lockfile-based release acceptance.

- Add separate opt-in shared-service preview configurations for stdio hosts, DSH, WorkBuddy and Codex. Keep public runtime pins and managed private provisioning unchanged.

## 0.1.4

- Pin the public Runtime 0.3.0 while preserving the metadata-only Python MCP,
  existing four tools and MCP SDK 1.x/2.x compatibility.
- Ship the WorkBuddy connector through the published managed launcher and the
  managed Node runtime: no system Python, uvx or Ollama requirement. The
  connector pins the exact npm version and its integrity and declares
  WorkBuddy 5.0.0. The Python/uvx route remains a documented custom-MCP
  alternative.
- Harden launcher preparation for Windows: bounded retries replace the direct
  rename when a freshly written executable is briefly locked (real-time scan
  or a terminating child after a stopped probe). The interrupted-preparation
  acceptance exercises this path on every platform.
- Prepare the configuration-only DSH Bundle
  (`@cnkang/qdrant-memory-dsh-bundle`) for installation through the official
  plugin manager, with an explicit preparation step that keeps the temporary
  probe download-free.
- Verify the exact public `npx` commands against the published launcher
  `0.1.0-rc.1` end to end on Linux, macOS and Windows: cold handshake within
  the connector timeout, a clean unprepared probe, refused-but-not-queued
  writes, CRUD and fresh-process persistence. The pinned `0.1.0-rc.2`
  re-ran the same suite after its publication and passed on Linux, macOS
  and Windows (2026-10-16).
- Preserve profile cache settings across upgrades and reject malformed bridge
  responses safely. Reproduce the published launcher `0.1.0-rc.1` integrity
  from a clean source pack at its release and include strict package-content
  checks. The same check re-ran for the pinned `0.1.0-rc.2` after its
  publication and reproduced the published integrity (2026-10-16).

## 0.1.3

- Distribute WorkBuddy MCP + Skill Connector ZIP/checksum assets with the new
  release. Connector 0.1.0 embeds canonical Skill 0.2.6 from immutable source.
- Pin the connector launcher and Registry/PyPI metadata to MCP 0.1.3. Keep
  Runtime 0.2.2, MCP SDK 1.x/2.x support, four scoped tools and stdio arguments.
- Preserve the metadata-only wheel and protected PyPI/Registry publishing.
  Verify Draft assets before publication. Existing releases remain immutable.
- WorkBuddy requires uvx/Python, an initialized profile and an embedding service.
  ZIP import and marketplace acceptance remain separate manual checks.

## 0.1.2

- Pin Runtime 0.2.2 for MCP Python SDK 1.x and 2.x support. Keep the package
  metadata-only and preserve its executable, four scoped tools and stdio arguments.
- Exercise installed wheel and sdist protocol acceptance under both SDK majors.
- Synchronize English and Chinese versions, install examples and compatibility guidance.

## 0.1.1

- Pin Runtime 0.2.1 to fix high-similarity explicit writes without Hermes or an LLM.
- Keep the distribution metadata-only and preserve the Runtime console entrypoint.
- Align Registry package/server versions and active installation/validation guidance.
- Require Runtime PyPI publication before MCP PyPI and Registry publication.
  Immutable source wheels remain preparation-only fixtures.

## 0.1.0

- Add metadata-only packaging with a direct upstream CLI entrypoint and exact
  Runtime 0.2.0 dependency. No Runtime or Skill sources are copied.
- Prepare stdio MCP Registry metadata, wheel/sdist protocol acceptance and
  protected OIDC publishing with safe Registry retry.
