# WorkBuddy managed installation release checklist

The managed source candidate is executable, but it is not a released marketplace
connector. Use the [installation guide](../integrations/managed/README.md) for
custom-connection testing and [cross-harness validation](dsh-validation.md) for
recorded evidence. Desktop results do not certify a different platform or a
marketplace installation flow.

## Release requirements

| Requirement | Acceptance |
| --- | --- |
| Public artifacts | Released Runtime/setup APIs and launcher. Exact dependency and canonical Skill pins |
| Marketplace install | ZIP import, managed Node preparation and first connection without developer tools |
| Cold preparation | Verified Python, dependencies and CPU model. Bounded diagnostics and retry |
| First handshake | Within actual WorkBuddy timeout. Protocol-only stdout |
| Readiness | Tools refuse operations until the backend is usable. No queued writes |
| CRUD and fresh session | Save/search, answer from recall in a new conversation, exact-ID update/delete |
| Restart | Full WorkBuddy quit, released storage ownership, relaunch and persistent results |
| Crash and retry | Installer interruption, backend exit and repeated startup without duplicate operations |
| Isolation | Independent WorkBuddy, DSH and Hermes profiles. No implicit imports |
| Supply chain | Fixed versions/hashes, archive safety, isolated build dependencies and secure paths |
| Credentials | No keys in command arguments, profiles, diagnostics or install subprocesses |
| Upgrade and rollback | Preserve data/ledger, refuse incompatible versions, no tag replacement |
| Native platforms | Linux x64, Windows x64 and macOS Apple Silicon CI. GUI claims require that client/OS |
| Hermes | Full native regression gate before a shared Runtime release |

The local CPU preset and existing Python/Cloud path are distinct products.
Do not infer Cloud Token-form acceptance from local CPU tests. Failed/skipped
checks remain open. Passing protocol tests does not establish marketplace UX.

CI runs the shared bridge, published connector configuration, deterministic
packaging and three-platform managed preparation. The canonical Skill builder
rejects unstaged resources, unsafe files and mismatched immutable pins. Release
jobs retain the existing public-install and immutable-tag guards.

Keep screenshots, raw logs, personal configuration and synthetic test profiles
outside Git and release archives. Record only redacted, reproducible outcomes.
