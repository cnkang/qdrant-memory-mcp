# Runtime dependency locks (build prototype)

Hash-locked, binary-only transitive dependency resolutions for the
plugin's public requirements on each platform. For this Desktop-only
prototype, the lock replaces the public Runtime wheel pin with the
immutable Runtime source commit; that wheel is built separately and
its SHA-256 is recorded in `runtime-wheel.json`.

The Runtime source package is excluded from the hash-locked PyPI wheel
download, so a wheelhouse never downloads a same-name wheel and then
overwrites it. The Runtime wheel itself is not committed here: it is a
local build artifact of the pinned source commit, and rebuilds are not
byte-identical. Keep the wheel with its metadata (the `--wheelhouse`
build does) when the recorded SHA-256 must remain verifiable.

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
Runtime wheel: hermes_plugin_qdrant_memory-0.6.2-py3-none-any.whl
Runtime wheel sha256: 1102eead4bce75004928b6d7a38880ebf7700f9d1a420e0d4b2a6f69f4a3714b
Runtime source commit: 913fa705922b5bfeb29d52f102cfc6385a4d0436
Runtime version: 0.6.2
