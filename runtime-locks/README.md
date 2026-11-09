# Runtime dependency locks (build prototype)

Hash-locked, binary-only transitive dependency resolutions of the
plugin's pinned requirements for each platform. The lock keeps the
pinned Runtime Git requirement; the wheel built during lock generation
and its SHA-256 are recorded in `runtime-wheel.json`.

The wheel itself is not committed here: it is a local build artifact of the
pinned Runtime commit, and rebuilds are not byte-identical. Keep the wheel
with the metadata (the `--wheelhouse` build does) when the recorded SHA-256
must remain verifiable.

Verification is gated on the host architecture: the lock files carry the
universal hash set, so a matching hash alone does not prove a target install.
`--verify` refuses a host whose `platform.machine()` differs from the target.
A cross-architecture wheelhouse needs the target host (or explicit
`pip download --platform` tags); `macos-x64` additionally has no macOS
x86_64 wheel for `cryptography==50.0.2`, so that target stays unverified.

This prototype does NOT make the package Desktop-only: see
docs/desktop-only-adr.md (NO-GO) for the remaining release
blockers (archive layout, per-platform selector, SBOM, clean
Desktop launch route).

These lock artifacts live at the repository root, outside the
plugin package on purpose: the marketplace package is the
source/requirements.txt delivery and must not carry desktop
bundle payloads.

Generated platforms: linux-x64, macos-arm64, macos-x64, windows-x64
Runtime wheel: hermes_plugin_qdrant_memory-0.6.0-py3-none-any.whl
Runtime wheel sha256: 9ed5dfbf00eedfebf95deb67f2b46292addda23792a17b54d75a30c48d277854
Runtime source commit: dee6777432f17523db75f6be32cf3ef15e48235c
Runtime version: 0.6.0
