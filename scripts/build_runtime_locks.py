"""Build per-platform hash-locked runtime dependency files for Desktop-only work.

This is a build prototype, not a Desktop-only release: the archive layout, the
clean-Desktop launch route, the per-platform archive selector, the SBOM and the
Desktop GUI acceptance remain unresolved
(``docs/desktop-only-adr.md`` stays NO-GO). What this script does deliver:

1. One hash-locked, binary-only transitive dependency file per supported
   platform (``linux-x64``, ``macos-arm64``, ``macos-x64``, ``windows-x64``)
   resolved from the plugin's pinned ``requirements.txt``.
2. The Runtime wheel built once from the immutable pinned source commit, with
   its SHA-256 recorded (the lock keeps the Codex plugin's Git pin for online
   provenance; the desktop bundle may substitute the recorded wheel).
3. ``--verify <platform>`` proves offline installation from a prebuilt
   wheelhouse plus the pinned Runtime wheel, with hash checking enabled.

Network is required to resolve or to build the wheelhouse. All hashes that land
in files are platform-reproducible, unlike resolver output.
"""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS = ROOT / "plugins/qdrant-memory/requirements.txt"
LOCKS = ROOT / "runtime-locks"
PLATFORM_LOCKS = {
    "linux-x64": ("x86_64-unknown-linux-gnu", "3.11"),
    "macos-arm64": ("aarch64-apple-darwin", "3.11"),
    "macos-x64": ("x86_64-apple-darwin", "3.11"),
    "windows-x64": ("x86_64-pc-windows-msvc", "3.11"),
}


def run(argv, cwd, *, check=True):
    """Run a subprocess and cascade failures with the captured stderr."""
    completed = subprocess.run(argv, cwd=cwd, capture_output=True, text=True)
    if check and completed.returncode:
        raise RuntimeError(f"{' '.join(argv[:2])} failed: {completed.stderr[-800:]}")
    return completed


def build_runtime_wheel(work: Path, save_dir: Path | None = None) -> dict:
    """Clone the pinned Runtime commit and build one platform-neutral wheel.

    The wheel content is a build artifact of the pinned source; its bytes are
    not guaranteed byte-reproducible across builds (build metadata contains a
    timestamp). The recorded SHA-256 pins exactly the recorded wheel.
    """
    release = json.loads(
        (ROOT / "plugins/qdrant-memory/release.json").read_text(encoding="utf-8")
    )
    commit = release["runtime_commit"]
    source = work / "runtime-source"
    run(["git", "init", str(source)], work)
    run(
        [
            "git",
            "-C",
            str(source),
            "remote",
            "add",
            "origin",
            "https://github.com/cnkang/hermes-plugin-qdrant-memory.git",
        ],
        work,
    )
    run(["git", "-C", str(source), "fetch", "--depth", "1", "origin", commit], work)
    run(["git", "-C", str(source), "checkout", "FETCH_HEAD"], work)
    build = run(
        ["uv", "build", "--wheel", "--out-dir", str(work / "wheel"), str(source)],
        work,
        check=False,
    )
    if build.returncode:
        raise RuntimeError("uv build --wheel failed: " + build.stderr[-800:])
    wheel = next((work / "wheel").glob("hermes_plugin_qdrant_memory-*.whl"))
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    if save_dir is not None:
        save_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(wheel, save_dir / wheel.name)
        (save_dir / "runtime-wheel.json").write_text(
            json.dumps(
                {
                    "wheel": wheel.name,
                    "sha256": digest,
                    "commit": commit,
                    "runtime_version": release["runtime_version"],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    return {
        "wheel": wheel.name,
        "sha256": digest,
        "commit": commit,
        "runtime_version": release["runtime_version"],
    }


def offline_requirements(lock: Path, wheelhouse: Path, runtime_meta: dict) -> Path:
    """Replace the unhashable Git Runtime line with the recorded wheel."""
    runtime_wheel = wheelhouse / runtime_meta["wheel"]
    replacement = (
        f"{runtime_wheel.resolve().as_uri()} --hash=sha256:{runtime_meta['sha256']}"
    )
    target = wheelhouse / f"verify-{lock.stem}.txt"
    lines = []
    for line in lock.read_text(encoding="utf-8").splitlines():
        if line.startswith("hermes-plugin-qdrant-memory @ git+"):
            lines.append(replacement)
        else:
            lines.append(line)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


def verify_offline(target: str, wheelhouse: Path, runtime_meta: dict) -> dict:
    """Install the hashed lock completely offline from recorded wheels only."""
    lock = LOCKS / f"{target}.txt"
    verify_req = offline_requirements(lock, wheelhouse, runtime_meta)
    work = Path(tempfile.mkdtemp(prefix="qm-lock-verify-"))
    try:
        venv_dir = work / "venv"
        run(["uv", "venv", "--seed", "--python", "3.11", str(venv_dir)], work)
        python = venv_dir / (
            "Scripts/python.exe" if sys.platform == "win32" else "bin/python"
        )
        result = run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--require-hashes",
                "--only-binary=:all:",
                "--no-index",
                "--no-cache-dir",
                "--find-links",
                str(wheelhouse),
                "-r",
                str(verify_req.resolve()),
            ],
            work,
            check=False,
        )
        if result.returncode:
            raise RuntimeError("offline install failed: " + result.stderr[-1500:])
        console = venv_dir / (
            "Scripts/qdrant-memory.exe"
            if sys.platform == "win32"
            else "bin/qdrant-memory"
        )
        probe = run([str(console), "--help"], work, check=False)
        return {
            "target": target,
            "installed": True,
            "offline": True,
            "require_hashes": True,
            "console_probe": probe.returncode == 0,
        }
    finally:
        subprocess.run(["rm", "-rf", str(work)], check=True)


def compile_lock(target: str, _work: Path) -> Path:
    """Resolve one platform's full transitive graph with hashes.

    Source and output paths stay relative to the repository root so generated
    headers remain host-independent.
    """
    platform, python = PLATFORM_LOCKS[target]
    output = LOCKS / f"{target}.txt"
    args = [
        "uv",
        "pip",
        "compile",
        "--generate-hashes",
        "--python-version",
        python,
        "--python-platform",
        platform,
        "plugins/qdrant-memory/requirements.txt",
        "-o",
        f"runtime-locks/{target}.txt",
    ]
    result = run(args, ROOT, check=False)
    if result.returncode:
        raise RuntimeError(
            f"uv pip compile for {target} failed: {result.stderr[-1200:]}"
        )
    return output


def host_platforms() -> list:
    """Platform locks that match this host operating system."""
    if sys.platform == "darwin":
        prefix = "macos"
    elif sys.platform == "win32":
        prefix = "windows"
    else:
        prefix = "linux"
    return sorted(name for name in PLATFORM_LOCKS if name.startswith(prefix))


def hashed_requirements(lock: Path, work: Path) -> Path:
    """Requirements copy without the unhashable direct-URL Runtime line."""
    target = work / f"hashed-{lock.stem}.txt"
    lines = [
        line
        for line in lock.read_text(encoding="utf-8").splitlines()
        if not line.startswith("hermes-plugin-qdrant-memory @ git+")
        and " @ git+" not in line
    ]
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


def seeded_python(work: Path) -> Path:
    """A pip-capable interpreter for hash-checked wheel downloads."""
    env_dir = work / "pip-venv"
    run(["uv", "venv", "--seed", "--python", "3.11", str(env_dir)], work)
    return env_dir / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def build_wheelhouse(work_dir: Path) -> Path:
    """Download the hashed wheels for this host's locks plus the Runtime wheel."""
    wheelhouse = work_dir.resolve()
    wheelhouse.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="qm-lock-wheels-") as temp:
        work = Path(temp)
        python = seeded_python(work)
        for target in host_platforms():
            filtered = hashed_requirements(LOCKS / f"{target}.txt", work)
            run(
                [
                    str(python),
                    "-m",
                    "pip",
                    "download",
                    "--require-hashes",
                    "--only-binary=:all:",
                    "--no-deps",
                    "-r",
                    str(filtered.resolve()),
                    "-d",
                    str(wheelhouse),
                ],
                work,
            )
        build_runtime_wheel(work, save_dir=wheelhouse)
    return wheelhouse


def main():
    """Build the locks, build this host's wheelhouse, or verify offline install."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", choices=sorted(PLATFORM_LOCKS))
    parser.add_argument(
        "--wheelhouse",
        type=Path,
        help="with --wheelhouse: download wheels; with --verify: use this directory",
    )
    args = parser.parse_args()
    if args.verify:
        if not args.wheelhouse or not args.wheelhouse.is_dir():
            parser.error("--verify needs a --wheelhouse built with --wheelhouse")
        meta_file = args.wheelhouse / "runtime-wheel.json"
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
        print(json.dumps(verify_offline(args.verify, args.wheelhouse, meta)))
        return 0
    if args.wheelhouse:
        print(json.dumps({"wheelhouse": str(build_wheelhouse(args.wheelhouse))}))
        return 0
    with tempfile.TemporaryDirectory(prefix="qm-lock-build-") as temp:
        work = Path(temp)
        LOCKS.mkdir(parents=True, exist_ok=True)
        built = build_runtime_wheel(work)
        targets = []
        for target in sorted(PLATFORM_LOCKS):
            compile_lock(target, work)
            targets.append(target)
        readme = LOCKS / "README.md"
        readme.write_text(
            "\n".join(
                [
                    "# Runtime dependency locks (build prototype)",
                    "",
                    "Hash-locked, binary-only transitive dependency resolutions of the",
                    "plugin's pinned requirements for each platform. The lock keeps the",
                    "pinned Runtime Git requirement; the bundle-ready wheel and its",
                    "SHA-256 are recorded in `runtime-wheel.json`.",
                    "",
                    "This prototype does NOT make the package Desktop-only: see",
                    "docs/desktop-only-adr.md (NO-GO) for the remaining release",
                    "blockers (archive layout, per-platform selector, SBOM, clean",
                    "Desktop launch route).",
                    "",
                    "These lock artifacts live at the repository root, outside the",
                    "plugin package on purpose: the marketplace package is the",
                    "source/requirements.txt delivery and must not carry desktop",
                    "bundle payloads.",
                    "",
                    "Generated platforms: " + ", ".join(targets),
                    f"Runtime wheel: {built['wheel']}",
                    f"Runtime wheel sha256: {built['sha256']}",
                    f"Runtime source commit: {built['commit']}",
                    f"Runtime version: {built['runtime_version']}",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        wheel_meta = LOCKS / "runtime-wheel.json"
        wheel_meta.write_text(json.dumps(built, indent=2) + "\n", encoding="utf-8")
        print(
            json.dumps(
                {
                    "locks": [str(LOCKS / f"{t}.txt") for t in targets],
                    "runtime_wheel": built,
                },
                indent=2,
            )
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
