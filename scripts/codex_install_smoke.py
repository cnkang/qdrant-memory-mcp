"""Credential-free real Codex installation, discovery and uninstall smoke check."""

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ID = "qdrant-memory@cnkang"
PLUGIN_VERSION = json.loads(
    (ROOT / "plugins/qdrant-memory/plugin.json").read_text(encoding="utf-8")
)["version"]


def check(condition, message):
    if not condition:
        raise RuntimeError(message)


def installed_openai_extension(cache):
    """Resolve Codex settings using the manifest precedence used by the host."""
    root_manifest = json.loads((cache / "plugin.json").read_text(encoding="utf-8"))
    root_extensions = root_manifest.get("extensions", {})
    check(isinstance(root_extensions, dict), "Installed plugin extensions are invalid")
    extension = root_extensions.get("com.openai")
    if extension is None:
        overlay_path = cache / ".codex-plugin/plugin.json"
        check(overlay_path.is_file(), "Codex compatibility overlay is missing")
        overlay = json.loads(overlay_path.read_text(encoding="utf-8"))
        overlay_extensions = overlay.get("extensions", {})
        check(
            isinstance(overlay_extensions, dict),
            "Codex compatibility extensions are invalid",
        )
        extension = overlay_extensions.get("com.openai")
    check(isinstance(extension, dict), "Installed Codex OpenAI extension is missing")
    return extension


def main():
    """Install the plugin in an isolated Codex home and verify its lifecycle."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", type=Path, required=True)
    args = parser.parse_args()
    home = args.home.resolve()
    home.mkdir(mode=0o700, parents=True, exist_ok=False)
    env = {**os.environ, "CODEX_HOME": str(home)}
    codex = shutil.which("codex", path=env.get("PATH"))
    if codex is None:
        raise RuntimeError("Codex CLI is not installed on PATH")

    def run(*argv):
        return subprocess.check_output(
            [codex, *argv], env=env, cwd=ROOT, text=True, timeout=60
        )

    run("plugin", "marketplace", "add", str(ROOT), "--json")
    installed = json.loads(run("plugin", "add", PLUGIN_ID, "--json"))
    check(installed["version"] == PLUGIN_VERSION, "Installed plugin version mismatch")
    cache = Path(installed["installedPath"])
    check((cache / "skills/setup/SKILL.md").is_file(), "Setup skill is missing")
    check(
        installed_openai_extension(cache).get("onboardingSkill")
        == "./skills/setup/SKILL.md",
        "Onboarding skill declaration mismatch",
    )
    config = home / "config.toml"
    content = config.read_text()
    check(
        content.count("enabled = true") == 1, "Expected exactly one enabled test plugin"
    )
    config.write_text(content.replace("enabled = true", "enabled = false"))
    disabled = json.loads(run("plugin", "list", "--json"))
    check(
        not next(p for p in disabled["installed"] if p["pluginId"] == PLUGIN_ID)[
            "enabled"
        ],
        "Test plugin remains enabled",
    )
    run("plugin", "remove", PLUGIN_ID)
    check(not cache.exists(), "Uninstall retained the plugin cache")
    print(
        json.dumps(
            {
                "status": "PASS",
                "cli": run("--version").strip(),
                "install": True,
                "setup_file_present": True,
                "disable": True,
                "uninstall": True,
                "model_tool_calls": "NOT_VERIFIED_WITHOUT_AUTH",
            }
        )
    )


if __name__ == "__main__":
    main()
