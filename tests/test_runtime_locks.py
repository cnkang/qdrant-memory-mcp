"""Guard the desktop-only runtime lock prototype artifacts."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCKS = ROOT / "runtime-locks"
TARGETS = ("linux-x64", "macos-arm64", "macos-x64", "windows-x64")


def test_lock_files_exist_for_all_platforms():
    for target in TARGETS:
        assert (LOCKS / f"{target}.txt").is_file(), target
    assert (LOCKS / "runtime-wheel.json").is_file()
    assert (LOCKS / "README.md").is_file()


def test_every_requirement_is_hashed_or_pinned_runtime():
    """Direct pins carry hashes; only the pinned Runtime direct URL may not."""
    for target in TARGETS:
        text = (LOCKS / f"{target}.txt").read_text(encoding="utf-8")
        lines = text.splitlines()
        blocks = []
        current: list = []
        for line in lines:
            current.append(line)
            if not line.endswith("\\"):
                blocks.append(current)
                current = []
        if current:
            blocks.append(current)
        failures = []
        for block in blocks:
            first = block[0]
            if not first or first.startswith("#") or first.startswith(" ") or first.startswith("\t"):
                continue
            if " @ git+https://github.com/cnkang/hermes-plugin-qdrant-memory.git@" in first:
                assert re.search(r"@([0-9a-f]{40})\\?$", first), first
                continue
            if not any("--hash=sha256:" in line for line in block):
                failures.append(first)
        assert failures == [], (target, failures)


def test_locks_keep_plugin_pins():
    """The lock must resolve the plugin's exact MCP distribution and commit."""
    release = json.loads(
        (ROOT / "plugins/qdrant-memory/release.json").read_text(encoding="utf-8")
    )
    for target in TARGETS:
        text = (LOCKS / f"{target}.txt").read_text(encoding="utf-8")
        assert f"qdrant-memory-mcp=={release['mcp_distribution_version']}" in text
        assert "@" in text and release["runtime_commit"] in text
        assert "-arm64" in text or target != "macos-arm64"
        if target == "windows-x64":
            assert "x86_64-pc-windows-msvc" in text


def test_runtime_wheel_record_is_evidence_shaped():
    meta = json.loads((LOCKS / "runtime-wheel.json").read_text(encoding="utf-8"))
    release = json.loads(
        (ROOT / "plugins/qdrant-memory/release.json").read_text(encoding="utf-8")
    )
    assert meta["commit"] == release["runtime_commit"]
    assert re.fullmatch(r"[0-9a-f]{64}", meta["sha256"])
    assert meta["wheel"].endswith(".whl")
    assert meta["runtime_version"] == release["runtime_version"]


def test_lock_readme_records_no_go_status():
    text = (LOCKS / "README.md").read_text(encoding="utf-8")
    assert "NO-GO" in text
    assert "SBOM" in text
    assert "bundle payloads." in text
