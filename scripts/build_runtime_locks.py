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
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS = ROOT / "plugins/qdrant-memory/requirements.txt"
LOCKS = ROOT / "runtime-locks"
RUNTIME_WHEEL_FILENAME = "runtime-wheel.json"
PLATFORM_LOCKS = {
    "linux-x64": ("x86_64-unknown-linux-gnu", "3.11"),
    "macos-arm64": ("aarch64-apple-darwin", "3.11"),
    "macos-x64": ("x86_64-apple-darwin", "3.11"),
    "windows-x64": ("x86_64-pc-windows-msvc", "3.11"),
}
TARGET_MACHINES = {
    "linux-x64": "x86_64",
    "macos-arm64": "arm64",
    "macos-x64": "x86_64",
    "windows-x64": "AMD64",
}
_SAFE_SUBPROCESS_ARGUMENT = re.compile(
    r"^(?:"
    r"-C|-P|-m|-o|-r|-d|--depth|--wheel|--out-dir|--python-version|"
    r"--python-platform|--generate-hashes|--seed|--python|--require-hashes|"
    r"--only-binary=:all:|--no-deps|--no-index|--no-cache-dir|--find-links|--help"
    r"|[^-\x00-\x1f\x7f][^\x00-\x1f\x7f]*"
    r")$"
)
_PATH_COMMANDS = frozenset({"git", "uv"})
_LOCAL_EXECUTABLES = frozenset(
    {"python", "python.exe", "qdrant-memory", "qdrant-memory.exe"}
)


def approved_executable(executable: object, root: Path) -> str:
    """Return a pre-approved executable, never a caller-supplied command line.

    Path lookups are limited to ``git`` and ``uv``. Absolute paths are accepted
    only for the interpreter and console scripts inside ``root``, the private
    directory of one build or verification run, so a caller cannot select an
    arbitrary program. The path is normalized lexically, not resolved, because
    a virtual environment interpreter is a symlink to the base interpreter.
    """
    if not isinstance(executable, str) or not executable:
        raise ValueError("subprocess executable must be a non-empty string")
    if executable in _PATH_COMMANDS:
        return executable
    candidate = Path(os.path.abspath(executable))
    allowed_root = Path(os.path.abspath(root))
    if (
        not candidate.is_absolute()
        or candidate.name not in _LOCAL_EXECUTABLES
        or allowed_root not in candidate.parents
    ):
        raise ValueError("subprocess executable is not an approved command")
    return str(candidate)


def run(
    executable: str,
    arguments: list[str],
    cwd: Path,
    *,
    root: Path | None = None,
    check=True,
):
    """Run one approved executable with validated, non-option arguments.

    The executable stays apart from the argument list on purpose: data that
    flows in from the command line can only reach argument values, never the
    program that gets executed.
    """
    command = approved_executable(executable, cwd if root is None else root)
    if not isinstance(arguments, list):
        raise ValueError("subprocess arguments must be an argument list")
    safe_arguments = []
    for argument in arguments:
        if not isinstance(argument, str):
            raise ValueError("subprocess arguments must be strings")
        if _SAFE_SUBPROCESS_ARGUMENT.fullmatch(argument) is None:
            raise ValueError(
                "subprocess arguments contain an unapproved option or control character"
            )
        safe_arguments.append(argument)

    completed = subprocess.run(
        [command, *safe_arguments], cwd=cwd, capture_output=True, text=True
    )
    if check and completed.returncode:
        raise RuntimeError(
            f"{command} {' '.join(safe_arguments[:3])} failed: {completed.stderr[-800:]}"
        )
    return completed


def validate_runtime_commit(commit: object) -> str:
    """Accept only a full Git object ID before using it as a fetch argument."""
    if not isinstance(commit, str) or re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise ValueError("runtime_commit must be a full lowercase 40-character Git SHA")
    return commit


def build_runtime_wheel(work: Path, save_dir: Path | None = None) -> dict:
    """Clone the pinned Runtime commit and build one platform-neutral wheel.

    The wheel content is a build artifact of the pinned source; its bytes are
    not guaranteed byte-reproducible across builds (build metadata contains a
    timestamp). The recorded SHA-256 pins exactly the recorded wheel.
    """
    release = json.loads(
        (ROOT / "plugins/qdrant-memory/release.json").read_text(encoding="utf-8")
    )
    commit = validate_runtime_commit(release["runtime_commit"])
    source = work / "runtime-source"
    run("git", ["init", str(source)], work)
    run(
        "git",
        [
            "-C",
            str(source),
            "remote",
            "add",
            "origin",
            "https://github.com/cnkang/hermes-plugin-qdrant-memory.git",
        ],
        work,
    )
    run("git", ["-C", str(source), "fetch", "--depth", "1", "origin", commit], work)
    run("git", ["-C", str(source), "checkout", "FETCH_HEAD"], work)
    build = run(
        "uv",
        ["build", "--wheel", "--out-dir", str(work / "wheel"), str(source)],
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
        (save_dir / RUNTIME_WHEEL_FILENAME).write_text(
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


VERIFY_REQUIREMENTS_FILENAME = "verify-requirements.txt"


def validate_runtime_wheel(name: object) -> str:
    """Accept only a plain wheel filename recorded by this builder."""
    if not isinstance(name, str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]*\.whl", name) is None:
        raise ValueError("runtime wheel must be a plain .whl filename")
    return name


def validate_sha256(digest: object) -> str:
    """Accept only a lowercase SHA-256 hex digest."""
    if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        raise ValueError("runtime wheel sha256 must be 64 lowercase hex characters")
    return digest


def offline_requirements(
    platform: str, wheelhouse: Path, runtime_meta: dict, target_dir: Path
) -> Path:
    """Write the offline requirements file into the run's private directory."""
    if platform not in PLATFORM_LOCKS:
        raise ValueError(f"Unsupported runtime lock platform: {platform}")
    lock = LOCKS / f"{platform}.txt"
    if not lock.is_file():
        raise FileNotFoundError(f"Runtime lock not found: {lock}")
    runtime_wheel = wheelhouse / validate_runtime_wheel(runtime_meta.get("wheel"))
    if not runtime_wheel.is_file():
        raise FileNotFoundError(f"Runtime wheel not found: {runtime_wheel}")
    digest = validate_sha256(runtime_meta.get("sha256"))
    replacement = f"{runtime_wheel.resolve().as_uri()} --hash=sha256:{digest}"
    target = target_dir / VERIFY_REQUIREMENTS_FILENAME
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
    if target not in PLATFORM_LOCKS:
        raise ValueError(f"Unsupported runtime lock platform: {target}")
    expected = TARGET_MACHINES[target]
    actual = platform.machine()
    if actual != expected:
        raise RuntimeError(
            f"--verify {target} requires host architecture {expected}; this host reports {actual}"
        )
    if not isinstance(runtime_meta, dict):
        raise ValueError("runtime-wheel.json must contain a JSON object")
    release = json.loads(
        (ROOT / "plugins/qdrant-memory/release.json").read_text(encoding="utf-8")
    )
    if (
        runtime_meta.get("commit") != release["runtime_commit"]
        or runtime_meta.get("runtime_version") != release["runtime_version"]
    ):
        raise ValueError("wheelhouse runtime metadata does not match the pinned release")
    work = Path(tempfile.mkdtemp(prefix="qm-lock-verify-"))
    try:
        verify_req = offline_requirements(target, wheelhouse, runtime_meta, work)
        venv_dir = work / "venv"
        run("uv", ["venv", "--python", "3.11", str(venv_dir)], work)
        python = venv_dir / (
            "Scripts/python.exe" if sys.platform == "win32" else "bin/python"
        )
        # ensurepip ships pip inside the interpreter, so seeding stays offline.
        run(str(python), ["-m", "ensurepip"], work)
        result = run(
            str(python),
            [
                "-P",
                "-m",
                "pip",
                "install",
                "--require-hashes",
                "--only-binary=:all:",
                "--no-index",
                "--no-cache-dir",
                "--find-links",
                ".",
                "-r",
                str(verify_req),
            ],
            wheelhouse,
            root=work,
            check=False,
        )
        if result.returncode:
            raise RuntimeError("offline install failed: " + result.stderr[-1500:])
        console = venv_dir / (
            "Scripts/qdrant-memory.exe"
            if sys.platform == "win32"
            else "bin/qdrant-memory"
        )
        probe = run(str(console), ["--help"], work)
        return {
            "target": target,
            "installed": True,
            "offline": True,
            "require_hashes": True,
            "console_probe": probe.returncode == 0,
        }
    finally:
        shutil.rmtree(work, ignore_errors=True)


def compile_lock(target: str, _work: Path) -> Path:
    """Resolve one platform's full transitive graph with hashes.

    Source and output paths stay relative to the repository root so generated
    headers remain host-independent.
    """
    platform, python = PLATFORM_LOCKS[target]
    output = LOCKS / f"{target}.txt"
    args = [
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
    result = run("uv", args, ROOT, check=False)
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


def hashed_requirements(platform: str, work: Path) -> Path:
    """Requirements copy without the unhashable direct-URL Runtime line."""
    if platform not in PLATFORM_LOCKS:
        raise ValueError(f"Unsupported runtime lock platform: {platform}")
    lock = LOCKS / f"{platform}.txt"
    target = work / f"hashed-{platform}.txt"
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
    run("uv", ["venv", "--seed", "--python", "3.11", str(env_dir)], work)
    return env_dir / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def build_wheelhouse(work_dir: Path) -> Path:
    """Download the hashed wheels for this host's locks plus the Runtime wheel."""
    wheelhouse = work_dir.resolve()
    wheelhouse.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="qm-lock-wheels-") as temp:
        work = Path(temp)
        python = seeded_python(work)
        for target in host_platforms():
            filtered = hashed_requirements(target, work)
            run(
                str(python),
                [
                    "-P",
                    "-m",
                    "pip",
                    "download",
                    "--require-hashes",
                    "--only-binary=:all:",
                    "--no-deps",
                    "-r",
                    str(filtered.resolve()),
                    "-d",
                    ".",
                ],
                wheelhouse,
                root=work,
            )
        build_runtime_wheel(work, save_dir=wheelhouse)
    return wheelhouse


def build_lock_files() -> None:
    """Build the pinned Runtime wheel and all platform lock artifacts."""
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
        wheel_meta = LOCKS / RUNTIME_WHEEL_FILENAME
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

def main() -> None:
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
        wheelhouse = args.wheelhouse.resolve()
        meta_file = wheelhouse / RUNTIME_WHEEL_FILENAME
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
        print(json.dumps(verify_offline(args.verify, wheelhouse, meta)))
    elif args.wheelhouse:
        print(json.dumps({"wheelhouse": str(build_wheelhouse(args.wheelhouse))}))
    else:
        build_lock_files()


if __name__ == "__main__":
    main()
