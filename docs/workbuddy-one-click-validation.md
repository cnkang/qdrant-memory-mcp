# WorkBuddy managed connector release checklist

Connector 0.2.0 pins the published launcher (`@cnkang/qdrant-memory-launcher`,
exact version plus npm integrity), the released Runtime wheel and the canonical
Skill at an exact commit. Marketplace ZIP import and managed-Node acceptance
remain maintainer gates. Use the
[connector guide](../integrations/workbuddy/README.md) for installation and
[cross-harness validation](dsh-validation.md) for recorded evidence. Desktop
results do not certify a different platform or a marketplace installation flow.

## Release requirements

| Requirement | Acceptance |
| --- | --- |
| Public artifacts | Released Runtime wheel and public launcher. Exact dependency, launcher-integrity and canonical Skill pins |
| Marketplace install | ZIP import, managed Node preparation and first connection without developer tools |
| Cold preparation | Verified Python, dependencies and CPU model. Bounded diagnostics and retry |
| First handshake | Within the actual WorkBuddy timeout. Protocol-only stdout |
| Readiness | Tools refuse operations until the backend is usable. No queued writes |
| CRUD and fresh session | Save/search, answer from recall in a new conversation, exact-ID update/delete |
| Restart | Full WorkBuddy quit, released storage ownership, relaunch and persistent results |
| Crash and retry | Installer interruption, backend exit and repeated startup without duplicate operations |
| Isolation | Independent WorkBuddy, DSH and Hermes profiles. No implicit imports |
| Supply chain | Fixed versions and hashes, archive safety, isolated build dependencies and secure paths |
| Credentials | No keys in command arguments, profiles, diagnostics or install subprocesses |
| Upgrade and rollback | Preserve data and ledger, refuse incompatible versions, no tag replacement |
| Native platforms | Linux x64, Windows x64 and macOS Apple Silicon CI. GUI claims require that client and OS |
| Hermes | Full native regression gate before a shared Runtime release |

## Current evidence

- Launcher `0.1.0-rc.1` and the pinned `0.1.0-rc.2` are public on the npm
  registry. At both releases, a clean `npm pack` of `integrations/managed/`
  reproduced the published tarball integrity. The release workflow refuses
  to prepare assets while the pinned version is unpublished or its public
  integrity differs from `launcher-source.json`.
- The connector ZIP is deterministic: byte-identical rebuilds, exact
  provenance (connector, MCP, Runtime, launcher integrity, Skill commit) and a
  verifiable SHA-256 checksum.
- The exact public `npx` connector command against the published `0.1.0-rc.1`
    tarball passes an automated acceptance on Linux, macOS and Windows. The cold handshake
  stays within budget. An unprepared DSH probe stays clean: no downloads, no lock and no
  fake success. The suite also covers background preparation, refused-but-not-replayed
  writes, CRUD, fresh-process persistence and resume after an aborted preparation. The pinned `0.1.0-rc.2` re-ran the same acceptance after its
  publication on 2026-10-16 and passed on Linux, macOS and Windows plus a
  local macOS run. All runs reported `passed: true`. The worst cold handshake
  was 21.5 seconds on Windows, inside the 30-second budget. The rc.1 and rc.2
  results above are historical acceptance evidence. The current `0.1.0-rc.3` pin
  passed the publication and integrity check in the release workflow. A separate
  full acceptance run for rc.3 is not recorded.
- The uvx alternative is exercised against the actual public PyPI pin once a
  release is published. Unpublished candidates record `NOT VERIFIED` for that
  check instead.   The MCP `0.1.4` release completed that check in its publication pipeline. It reported
  `Public PyPI release verified: True`. The uvx protocol test ran against the public
  package.
- The release workflow refuses to prepare assets while the launcher pin is not
  public with matching integrity.

Still open before marketplace submission:

- Import the final ZIP into the actual WorkBuddy client and confirm bilingual
  metadata, icon and Skill rendering.
- Confirm managed-Node provisioning and the first cold connection on a clean
  machine without developer tools.
- Full application quit and restart acceptance with the managed profile.
- Record client version, OS and observations for every GUI row. Keep
  screenshots, raw logs, personal configuration and synthetic test profiles
  outside Git and release archives.
