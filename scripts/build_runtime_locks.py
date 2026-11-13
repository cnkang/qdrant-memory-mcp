"""Build per-platform hash-locked runtime dependency files for Desktop-only work.

This is a build prototype, not a Desktop-only release: the archive layout, the
clean-Desktop launch route, the per-platform archive selector, the SBOM and the
Desktop GUI acceptance remain unresolved
(``docs/desktop-only-adr.md`` stays NO-GO). What this script does deliver:

1. One hash-locked, binary-only transitive dependency file per supported
   platform (``linux-x64``, ``macos-arm64``, ``macos-x64``, ``windows-x64``)
   resolved from the plugin's pinned requirements, with Runtime resolved from
   the immutable source commit named by ``release.json``.
2. The Runtime wheel built from that source commit, with its SHA-256 recorded.
   Offline verification substitutes this local wheel for the Git requirement.
3. ``--verify <platform>`` proves offline installation from a prebuilt
   wheelhouse plus the pinned Runtime wheel, with hash checking enabled.

Network is required to resolve dependencies or build a wheelhouse. Dependency
hashes come from the locked package artifacts; the Runtime hash pins one local
wheel build, whose bytes are not reproducible across build timestamps.
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
RELEASE_FILE = ROOT / "plugins/qdrant-memory/release.json"
LOCKS = ROOT / "runtime-locks"
RUNTIME_WHEEL_FILENAME = "runtime-wheel.json"
RUNTIME_DISTRIBUTION = "hermes-plugin-qdrant-memory"
RUNTIME_REPOSITORY = (
    "https://github.com/cnkang/hermes-plugin-qdrant-memory.git"
)
RUNTIME_DIRECT_URL_SEPARATOR = " @ git+"
_RUNTIME_REQUIREMENT_RE = re.compile(
    r"\s*hermes[-_.]plugin[-_.]qdrant[-_.]memory"
    r"(?P<extras>\[[A-Z0-9,_.-]+\])?\s*==\s*"
    r"(?P<version>[0-9A-Z.!+_-]+)\s*(?:#.*)?",
    re.IGNORECASE | re.ASCII,
)
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
    r"--only-binary=:all:|--no-deps|--no-index|--no-cache-dir|--find-links|--help|"
    r"--offline|--no-header|--no-python-downloads"
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


def load_release() -> dict:
    """Read and validate the release fields used by source-built locks."""
    release = json.loads(RELEASE_FILE.read_text(encoding="utf-8"))
    validate_runtime_commit(release.get("runtime_commit"))
    if release.get("runtime_repository") != RUNTIME_REPOSITORY.removesuffix(".git"):
        raise ValueError("release runtime_repository does not match the approved source")
    version = release.get("runtime_version")
    if not isinstance(version, str) or re.fullmatch(r"[0-9A-Za-z.!+_-]+", version) is None:
        raise ValueError("runtime_version must be a valid pinned version")
    return release


def _requirement_name(line: str) -> str | None:
    """Return a normalized package name for one top-level requirement line."""
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or stripped.startswith("-"):
        return None
    match = re.match(r"([A-Za-z0-9][A-Za-z0-9._-]*)", stripped)
    if match is None:
        return None
    return re.sub(r"[-_.]+", "-", match.group(1)).lower()


def _runtime_requirement_for_desktop_lock(work: Path) -> Path:
    """Pin the Desktop prototype to the release's immutable Runtime source."""
    release = load_release()
    lines = REQUIREMENTS.read_text(encoding="utf-8").splitlines()
    indexes = [
        index
        for index, line in enumerate(lines)
        if _requirement_name(line) == RUNTIME_DISTRIBUTION
    ]
    if len(indexes) != 1:
        raise ValueError("requirements.txt must contain exactly one Runtime pin")
    index = indexes[0]
    match = _RUNTIME_REQUIREMENT_RE.fullmatch(lines[index])
    if match is None or match.group("version") != release["runtime_version"]:
        raise ValueError(
            "requirements.txt Runtime version must match release.json before compiling locks"
        )
    runtime_requirement = (
        f"{RUNTIME_DISTRIBUTION}{match.group('extras') or ''}"
        f"{RUNTIME_DIRECT_URL_SEPARATOR}"
        f"{RUNTIME_REPOSITORY}@{release['runtime_commit']}"
    )
    lines[index] = runtime_requirement
    target = work / "desktop-runtime-lock-requirements.txt"
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


def _validate_runtime_metadata(runtime_meta: object) -> tuple[str, str]:
    """Validate source provenance, wheel version, and hash against release.json."""
    if not isinstance(runtime_meta, dict):
        raise ValueError("runtime-wheel.json must contain a JSON object")
    release = load_release()
    commit = validate_runtime_commit(runtime_meta.get("commit"))
    if (
        commit != release["runtime_commit"]
        or runtime_meta.get("runtime_version") != release["runtime_version"]
    ):
        raise ValueError("wheelhouse runtime metadata does not match the pinned release")
    wheel_name = validate_runtime_wheel(runtime_meta.get("wheel"))
    expected_prefix = (
        "hermes_plugin_qdrant_memory-" + release["runtime_version"] + "-"
    )
    if not wheel_name.startswith(expected_prefix):
        raise ValueError("runtime wheel filename does not match the pinned release version")
    return wheel_name, validate_sha256(runtime_meta.get("sha256"))


def build_runtime_wheel(work: Path, save_dir: Path | None = None) -> dict:
    """Clone the pinned Runtime commit and build one platform-neutral wheel.

    The wheel content is a build artifact of the pinned source; its bytes are
    not guaranteed byte-reproducible across builds (build metadata contains a
    timestamp). The recorded SHA-256 pins exactly the recorded wheel.
    """
    release = load_release()
    commit = release["runtime_commit"]
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
            RUNTIME_REPOSITORY,
        ],
        work,
    )
    run("git", ["-C", str(source), "fetch", "--depth", "1", "origin", commit], work)
    run("git", ["-C", str(source), "checkout", "FETCH_HEAD"], work)
    checkout = run("git", ["-C", str(source), "rev-parse", "HEAD"], work)
    if checkout.stdout.strip() != commit:
        raise RuntimeError("checked out Runtime source does not match the pinned commit")
    build = run(
        "uv",
        ["build", "--wheel", "--out-dir", str(work / "wheel"), str(source)],
        work,
        check=False,
    )
    if build.returncode:
        raise RuntimeError("uv build --wheel failed: " + build.stderr[-800:])
    wheels = list((work / "wheel").glob("hermes_plugin_qdrant_memory-*.whl"))
    if len(wheels) != 1:
        raise RuntimeError("Runtime source build must produce exactly one wheel")
    wheel = wheels[0]
    if not wheel.name.startswith(
        "hermes_plugin_qdrant_memory-" + release["runtime_version"] + "-"
    ):
        raise RuntimeError("Runtime source build produced a wheel for the wrong version")
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    if save_dir is not None:
        save_dir.mkdir(parents=True, exist_ok=True)
        saved_wheel = save_dir / wheel.name
        if saved_wheel.exists():
            existing_digest = hashlib.sha256(saved_wheel.read_bytes()).hexdigest()
            if existing_digest != digest:
                raise FileExistsError(
                    "refusing to overwrite a different wheel with the same filename"
                )
        else:
            shutil.copy2(wheel, saved_wheel)
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


def _split_requirement_blocks(lock: Path) -> tuple[list[str], list[list[str]]]:
    """Separate leading options from requirement blocks in a compiled lock."""
    blocks = []
    prefix = []
    current = None
    for line in lock.read_text(encoding="utf-8").splitlines():
        if line and not line[0].isspace() and not line.startswith("#"):
            if current is not None:
                blocks.append(current)
            current = [line]
        elif current is None:
            prefix.append(line)
        else:
            current.append(line)
    if current is not None:
        blocks.append(current)
    return prefix, blocks


def _runtime_requirement_blocks(blocks: list[list[str]]) -> list[list[str]]:
    """Select the blocks whose first line names the Runtime distribution."""
    return [
        block
        for block in blocks
        if _requirement_name(block[0]) == RUNTIME_DISTRIBUTION
    ]


def _expected_runtime_source(release: dict) -> str:
    return f"git+{RUNTIME_REPOSITORY}@{release['runtime_commit']}"


def _has_expected_runtime_source(entry: str, expected_source: str) -> bool:
    return RUNTIME_DIRECT_URL_SEPARATOR in entry and entry.endswith(expected_source)


def _validate_offline_runtime_entry(entry: str, release: dict) -> None:
    """Accept only the pinned source URL or exact published Runtime version."""
    expected_source = _expected_runtime_source(release)
    if RUNTIME_DIRECT_URL_SEPARATOR in entry:
        if not entry.endswith(expected_source):
            raise ValueError("runtime lock source does not match the pinned commit")
        return
    match = re.match(
        r"^hermes[-_.]plugin[-_.]qdrant[-_.]memory(?:\[[^\]]+\])?\s*==\s*([^\s\\]+)",
        entry,
        re.IGNORECASE | re.ASCII,
    )
    if match is None or match.group(1) != release["runtime_version"]:
        raise ValueError("runtime lock version does not match the pinned release")


def offline_requirements(
    platform: str, wheelhouse: Path, runtime_meta: dict, target_dir: Path
) -> Path:
    """Write the offline requirements file into the run's private directory."""
    if platform not in PLATFORM_LOCKS:
        raise ValueError(f"Unsupported runtime lock platform: {platform}")
    lock = LOCKS / f"{platform}.txt"
    if not lock.is_file():
        raise FileNotFoundError(f"Runtime lock not found: {lock}")
    wheel_name, digest = _validate_runtime_metadata(runtime_meta)
    runtime_wheel = wheelhouse / wheel_name
    if not runtime_wheel.is_file():
        raise FileNotFoundError(f"Runtime wheel not found: {runtime_wheel}")
    actual_digest = hashlib.sha256(runtime_wheel.read_bytes()).hexdigest()
    if actual_digest != digest:
        raise ValueError("runtime wheel SHA-256 does not match runtime-wheel.json")
    replacement = f"{runtime_wheel.resolve().as_uri()} --hash=sha256:{digest}"
    target = target_dir / VERIFY_REQUIREMENTS_FILENAME
    prefix, blocks = _split_requirement_blocks(lock)
    runtime_blocks = _runtime_requirement_blocks(blocks)
    if len(runtime_blocks) != 1:
        raise ValueError("runtime lock must contain exactly one Runtime requirement")
    release = load_release()
    runtime_block = runtime_blocks[0]
    _validate_offline_runtime_entry(runtime_block[0].strip(), release)

    output = list(prefix)
    for block in blocks:
        if block is runtime_block:
            output.append(replacement)
        else:
            output.extend(block)
    target.write_text("\n".join(output) + "\n", encoding="utf-8")
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
    _validate_runtime_metadata(runtime_meta)
    work = Path(tempfile.mkdtemp(prefix="qm-lock-verify-"))
    try:
        verify_req = offline_requirements(target, wheelhouse, runtime_meta, work)
        venv_dir = work / "venv"
        run(
            "uv",
            ["venv", "--offline", "--no-python-downloads", "--python", "3.11", str(venv_dir)],
            work,
        )
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


def compile_lock(target: str, work: Path) -> Path:
    """Resolve one platform graph, then normalize generated lock metadata."""
    if target not in PLATFORM_LOCKS:
        raise ValueError(f"Unsupported runtime lock platform: {target}")
    platform, python = PLATFORM_LOCKS[target]
    output = LOCKS / f"{target}.txt"
    requirements = _runtime_requirement_for_desktop_lock(work)
    args = [
        "pip",
        "compile",
        "--no-header",
        "--generate-hashes",
        "--python-version",
        python,
        "--python-platform",
        platform,
        str(requirements),
        "-o",
        str(output),
    ]
    result = run("uv", args, ROOT, check=False)
    if result.returncode:
        raise RuntimeError(
            f"uv pip compile for {target} failed: {result.stderr[-1200:]}"
        )
    if not output.is_file():
        raise RuntimeError(f"uv pip compile for {target} did not create its lock file")
    release = load_release()
    canonical_header = "\n".join(
        [
            "# Generated by scripts/build_runtime_locks.py; do not edit.",
            "# Source requirements: plugins/qdrant-memory/requirements.txt",
            f"# Target: {target} ({platform}; Python {python})",
            f"# Runtime source commit: {release['runtime_commit']}",
            "",
            "",
        ]
    )
    generated = output.read_text(encoding="utf-8").replace(
        str(requirements), "plugins/qdrant-memory/requirements.txt"
    )
    output.write_text(
        canonical_header + generated, encoding="utf-8"
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
    release = load_release()
    expected_source = _expected_runtime_source(release)
    prefix, blocks = _split_requirement_blocks(lock)

    runtime_count = 0
    output = list(prefix)
    for block in blocks:
        first = block[0].strip()
        if _requirement_name(first) == RUNTIME_DISTRIBUTION:
            runtime_count += 1
            if not _has_expected_runtime_source(first, expected_source):
                raise ValueError("runtime lock source does not match the pinned commit")
            continue
        if RUNTIME_DIRECT_URL_SEPARATOR in first:
            raise ValueError("only the pinned Runtime source may be excluded from wheel download")
        output.extend(block)
    if runtime_count != 1:
        raise ValueError("runtime lock must contain exactly one Runtime source requirement")
    target.write_text("\n".join(output) + "\n", encoding="utf-8")
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
                    "Hash-locked, binary-only transitive dependency resolutions for the",
                    "plugin's public requirements on each platform. For this Desktop-only",
                    "prototype, the lock replaces the public Runtime wheel pin with the",
                    "immutable Runtime source commit; that wheel is built separately and",
                    "its SHA-256 is recorded in `runtime-wheel.json`.",
                    "",
                    "The Runtime source package is excluded from the hash-locked PyPI wheel",
                    "download, so a wheelhouse never downloads a same-name wheel and then",
                    "overwrites it. The Runtime wheel itself is not committed here: it is a",
                    "local build artifact of the pinned source commit, and rebuilds are not",
                    "byte-identical. Keep the wheel with its metadata (the `--wheelhouse`",
                    "build does) when the recorded SHA-256 must remain verifiable.",
                    "",
                    "Verification is gated on the host architecture: the lock files carry the",
                    "universal hash set, so a matching hash alone does not prove a target install.",
                    "`--verify` refuses a host whose `platform.machine()` differs from the target.",
                    "A cross-architecture wheelhouse needs the target host (or explicit",
                    "`pip download --platform` tags); `macos-x64` additionally has no macOS",
                    "x86_64 wheel for `cryptography==50.0.2`, so that target stays unverified.",
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
