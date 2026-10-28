"""Report whether this candidate can be tested through its exact public pins."""

import argparse
import importlib.util
import json
import os
import re
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("workbuddy_pypi_query", ROOT / "scripts/pypi_release.py")
query = importlib.util.module_from_spec(spec)
spec.loader.exec_module(query)
release = query.release

EXTRA_EQUALS = re.compile(r"\bextra\s*==\s*[\"']([^\"']+)[\"']")


def extra_gated(entry, groups):
    """Report whether every branch of the marker requires one declared extra."""
    _, separator, marker = entry.partition(";")
    if not separator:
        return False
    # An `or` branch that does not require a declared extra applies to plain
    # installs, so the whole requirement is unconditional for our purpose.
    # This splits on top-level ` or ` only: a nested parenthesised `or` is
    # rejected rather than parsed, which keeps the guard fail-closed without
    # taking a third-party dependency in this job.
    for branch in re.split(r"\s+or\s+", marker):
        declared = EXTRA_EQUALS.findall(branch)
        if not declared or any(group not in groups for group in declared):
            return False
    return True


def available(root):
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    data = release(project, False)
    if data is None:
        return False
    info = data["info"]
    # This check runs without third-party packages, so it compares the declared
    # runtime pins textually: every unconditional entry must be one of them and
    # every other entry must be guarded by an extra marker.
    declared = project["dependencies"]
    groups = set(project.get("optional-dependencies", {}))
    published = info.get("requires_dist") or []
    missing = [dependency for dependency in declared if dependency not in published]
    unexpected = [
        entry
        for entry in published
        if entry not in declared and not extra_gated(entry, groups)
    ]
    if (
        info.get("name") != project["name"]
        or info.get("version") != project["version"]
        or missing
        or unexpected
        or "<!-- mcp-name: io.github.cnkang/qdrant-memory -->" not in info.get("description", "")
    ):
        raise ValueError("Conflicting public MCP version, ownership or Runtime dependency")
    return True


def registry_entry(base, pin):
    """Fetch one registry document for the exact pinned version; None when absent."""
    url = f"{base}/{pin['name']}/{pin['version']}"
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise


def mirror_entry(base, pin):
    """Best-effort fallback lookup: absence and transient failures are informational."""
    try:
        entry = registry_entry(base, pin)
    except (urllib.error.HTTPError, urllib.error.URLError, OSError) as exc:
        print(f"Registry {base} is unreachable ({type(exc).__name__}); its fallback entry was not verified")
        return None
    if entry is None:
        print(f"Registry {base} does not serve the pinned version; its fallback entry is inert")
    return entry


def launcher(root):
    """Check the pinned npm launcher identity, published integrity and mirror agreement."""
    pin = json.loads((root / "launcher-source.json").read_text(encoding="utf-8"))
    mcp = json.loads((root / "integrations/workbuddy/mcp.json").read_text(encoding="utf-8"))
    canonical, *mirrors = mcp["mcpServers"]["qdrant-memory"]["npmRegistries"]
    if canonical != "https://registry.npmjs.org":
        raise ValueError("The first npm registry must be the canonical registry")
    data = registry_entry(canonical, pin)
    if data is None:
        for base in mirrors:
            if mirror_entry(base, pin) is not None:
                raise ValueError(f"Registry {base} serves a launcher version that the canonical registry does not publish")
        return False
    if data.get("name") != pin["name"] or data.get("version") != pin["version"]:
        raise ValueError("Conflicting public launcher identity")
    if data.get("dist", {}).get("integrity") != pin["integrity"]:
        raise ValueError("Public launcher integrity differs from the checked-in pin")
    for base in mirrors:
        mirror = mirror_entry(base, pin)
        if mirror is not None and (mirror.get("name") != pin["name"] or mirror.get("version") != pin["version"] \
                or mirror.get("dist", {}).get("integrity") != pin["integrity"]):
            raise ValueError(f"Registry {base} serves a conflicting launcher payload")
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-launcher", action="store_true")
    args = parser.parse_args()
    exists = available(ROOT)
    launcher_ok = launcher(ROOT)
    if output := os.environ.get("GITHUB_OUTPUT"):
        with open(output, "a", encoding="utf-8") as stream:
            stream.write(f"exists={str(exists).lower()}\n")
            stream.write(f"launcher={str(launcher_ok).lower()}\n")
    print("Exact public uvx acceptance required" if exists else "Public uvx acceptance: NOT VERIFIED (candidate not yet published; protected publish workflow must verify after PyPI approval)")
    print("Pinned public launcher verified" if launcher_ok else "Public launcher pin: NOT VERIFIED (the release must not ship before this pin is published)")
    if args.require_launcher and not launcher_ok:
        raise SystemExit("Pinned public launcher is not published; release assets must not be prepared")


if __name__ == "__main__":
    main()
