"""Credential-free real Codex installation, discovery and uninstall smoke check."""

import argparse
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", type=Path, required=True)
    args = parser.parse_args()
    home = args.home.resolve()
    home.mkdir(mode=0o700, parents=True, exist_ok=False)
    env = {**os.environ, "CODEX_HOME": str(home)}

    def run(*argv):
        return subprocess.check_output(
            ["codex", *argv], env=env, cwd=ROOT, text=True, timeout=60
        )

    run("plugin", "marketplace", "add", str(ROOT), "--json")
    installed = json.loads(
        run("plugin", "add", "qdrant-memory@cnkang-memory", "--json")
    )
    assert installed["version"] == "0.1.0"
    cache = Path(installed["installedPath"])
    assert (cache / "skills/setup/SKILL.md").is_file()
    assert (
        json.loads((cache / "plugin.json").read_text())["extensions"]["com.openai"][
            "onboardingSkill"
        ]
        == "./skills/setup/SKILL.md"
    )
    config = home / "config.toml"
    content = config.read_text()
    assert content.count("enabled = true") == 1
    config.write_text(content.replace("enabled = true", "enabled = false"))
    disabled = json.loads(run("plugin", "list", "--json"))
    assert not next(
        p
        for p in disabled["installed"]
        if p["pluginId"] == "qdrant-memory@cnkang-memory"
    )["enabled"]
    run("plugin", "remove", "qdrant-memory@cnkang-memory")
    assert not cache.exists()
    print(
        json.dumps(
            {
                "status": "PASS",
                "cli": run("--version").strip(),
                "install": True,
                "setup_discovered": True,
                "disable": True,
                "uninstall": True,
                "model_tool_calls": "NOT_VERIFIED_WITHOUT_AUTH",
            }
        )
    )


if __name__ == "__main__":
    main()
