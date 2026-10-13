"""Verify immutable Registry metadata and safely retry a failed publication."""

import json
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def published(server):
    name = urllib.parse.quote(server["name"], safe="")
    version = urllib.parse.quote(server["version"], safe="")
    url = f"https://registry.modelcontextprotocol.io/v0.1/servers/{name}/versions/{version}"
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            data = json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return False
        raise
    actual = data["server"]
    for key, value in server.items():
        assert actual.get(key) == value, f"Conflicting Registry metadata: {key}"
    assert data["_meta"]["io.modelcontextprotocol.registry/official"]["status"] == "active"
    return True


def main():
    server = json.loads(Path("server.json").read_text())
    if not published(server):
        subprocess.run([".publisher/mcp-publisher", "login", "github-oidc"], check=True)
        subprocess.run([".publisher/mcp-publisher", "publish"], check=True)
    for _ in range(12):
        if published(server):
            print(f"Registry verified: {server['name']} {server['version']}")
            return
        time.sleep(5)
    raise RuntimeError("Registry result not publicly available")


if __name__ == "__main__":
    main()
