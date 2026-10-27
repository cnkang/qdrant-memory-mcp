"""Security audit of the DSH acceptance harness lockfile (development-only).

These checks inspect the test/acceptance lockfile under
``integrations/dsh/package-lock.json``. They are development-only because
that lockfile is intentionally excluded from end-user artifacts (sdist/wheel).
"""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def at_least(version, floor):
    """A prerelease of the fix version does not count as the fix."""
    numbers, _, prerelease = version.partition("-")
    parts = tuple(int(part) for part in numbers.split("."))
    return parts > floor or (parts == floor and not prerelease)


def test_dsh_lock_excludes_oauth_vulnerable_sdk_versions():
    """Reject vulnerable SDK copies, including nested transitive resolutions."""
    lock = json.loads((ROOT / "integrations/dsh/package-lock.json").read_text(encoding="utf-8"))
    clients = []
    for path, package in lock["packages"].items():
        if path.endswith(("node_modules/@modelcontextprotocol/client", "node_modules/@modelcontextprotocol/core")):
            floor = (2, 3, 0) if path.endswith("/client") else (2, 2, 0)
            assert at_least(
                package["version"], floor
            ), f"{path} retains an OAuth or cross-origin redirect advisory baseline"
            if path.endswith("/client"):
                clients.append(path)
        elif path.endswith("node_modules/@modelcontextprotocol/sdk"):
            assert at_least(
                package["version"], (1, 32, 0)
            ), f"{path} retains the affected 1.x SDK"
    assert clients, "The actual DSH MCP client resolution must be audited"


def test_dsh_lock_excludes_vulnerable_http_and_schema_versions():
    """Reject affected undici and Zod copies throughout the resolved tree."""
    lock = json.loads((ROOT / "integrations/dsh/package-lock.json").read_text(encoding="utf-8"))
    seen = {"undici": [], "zod": []}
    for path, package in lock["packages"].items():
        for name, floor, advisory in (
            ("undici", (8, 12, 2), "GHSA-xjj6-f33q-929c"),
            ("zod", (4, 6, 6), "GHSA-mrhx-c7xc-m3w5"),
        ):
            if path.endswith(f"node_modules/{name}"):
                assert at_least(package["version"], floor), f"{path} retains {advisory}"
                seen[name].append(path)
    assert seen["undici"], "The resolved HTTP client must be audited"
    assert seen["zod"], "The resolved schema validator must be audited"


def test_dsh_lock_excludes_vulnerable_zip_parser_versions():
    """Reject every affected fflate copy, including the Office dependency."""
    lock = json.loads((ROOT / "integrations/dsh/package-lock.json").read_text(encoding="utf-8"))
    copies = []
    for path, package in lock["packages"].items():
        if path.endswith("node_modules/fflate"):
            assert at_least(package["version"], (0, 8, 3)), f"{path} retains GHSA-px8p-9vwx-vf98"
            copies.append(path)
    assert copies, "The actual DSH Office ZIP dependency must be audited"
