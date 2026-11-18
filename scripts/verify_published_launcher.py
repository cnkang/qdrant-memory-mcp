"""Verify the published launcher tarball and its match with this checkout.

npm does not promise identical tarball bytes across operating systems, so the
integrity check reads the artifact users download instead of repacking it. The
per-file comparison then keeps the repository and the published payload honest.
"""

import argparse
import base64
import hashlib
import io
import json
import tarfile
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = "https://registry.npmjs.org"


def integrity(body):
    """Return the npm SRI value for tarball bytes."""
    return "sha512-" + base64.b64encode(hashlib.sha512(body).digest()).decode("ascii")


def registry_metadata(name, version, opener=urllib.request.urlopen):
    """Return the registry document for one exact package version."""
    url = f"{REGISTRY}/{name.replace('/', '%2f')}/{version}"
    try:
        with opener(url, timeout=60) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            raise SystemExit(
                f"Launcher {name} {version} is not published. Publish the pinned "
                "tarball before this check can verify the payload."
            ) from error
        raise


def download(url, opener=urllib.request.urlopen):
    """Return the tarball bytes for a registry download URL."""
    with opener(url, timeout=180) as response:
        return response.read()


def member_bytes(archive, name):
    """Read one tarball member and reject a missing or non-regular entry."""
    extracted = archive.extractfile(name)
    if extracted is None:
        raise ValueError(f"Launcher payload is missing {name}")
    return extracted.read()


def verify(body, pin, source):
    """Check the published bytes, identity and files against the checkout."""
    actual = integrity(body)
    if actual != pin["integrity"]:
        raise ValueError(
            f"Published launcher integrity {actual} differs from launcher-source.json"
        )
    with tarfile.open(fileobj=io.BytesIO(body)) as archive:
        members = {name: archive.getmember(name) for name in archive.getnames()}
        for name, member in members.items():
            parts = Path(name).parts
            if not member.isfile() or name.startswith("/") or ".." in parts:
                raise ValueError(f"Launcher payload contains an unsafe member: {name}")
        package = json.loads(member_bytes(archive, "package/package.json"))
        runtime = json.loads(member_bytes(archive, "package/runtime.json"))
        if package["version"] != pin["version"]:
            raise ValueError(
                "Published package version differs from launcher-source.json"
            )
        if runtime["version"] != pin["runtime_version"]:
            raise ValueError("Published runtime.json differs from launcher-source.json")
        allowed = {f"package/{name}" for name in package["files"]}
        allowed |= {
            "package/package.json",
            "package/README.md",
            "package/LICENSE",
            "package/runtime.json",
        }
        unexpected = set(members) - allowed
        if unexpected:
            raise ValueError(
                f"Launcher payload contains unexpected members: {sorted(unexpected)}"
            )
        for relative in package["files"]:
            member = f"package/{relative}"
            if member not in members:
                raise ValueError(f"Launcher payload is missing {relative}")
            path = source / relative
            if not path.is_file():
                raise ValueError(f"Launcher source is missing {relative}")
            if member_bytes(archive, member) != path.read_bytes():
                raise ValueError(f"Published {relative} differs from this checkout")
        if runtime != json.loads((source / "runtime.json").read_text(encoding="utf-8")):
            raise ValueError("Published runtime.json differs from this checkout")
    return {"name": pin["name"], "version": pin["version"], "integrity": actual}


def main(argv=None):
    """Verify the pinned launcher and print a machine-readable result."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    arguments = parser.parse_args(argv)
    root = arguments.root
    pin = json.loads((root / "launcher-source.json").read_text(encoding="utf-8"))
    document = registry_metadata(pin["name"], pin["version"])
    if document["dist"]["integrity"] != pin["integrity"]:
        raise ValueError("Registry integrity differs from launcher-source.json")
    body = download(document["dist"]["tarball"])
    print(json.dumps(verify(body, pin, root / "integrations/managed")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
