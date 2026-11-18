"""Validate npm audit output for the moving DSH compatibility probe."""

import json
import re
import sys
from pathlib import Path

ALLOWED_ADVISORY = "https://github.com/advisories/GHSA-fc5q-39xc-vjpf"
VULNERABLE_PICOMATCH = "4.0.7"


def _advisory_sources(name, vulnerabilities, path=()):
    if name in path:
        raise ValueError(f"cyclic npm audit dependency reference at {name}")
    finding = vulnerabilities.get(name)
    if not isinstance(finding, dict):
        raise ValueError(f"npm audit dependency reference is missing: {name}")

    via = finding.get("via")
    if not isinstance(via, list) or not via:
        raise ValueError(f"npm audit dependency has no advisory details: {name}")

    sources = set()
    next_path = (*path, name)
    for item in via:
        if isinstance(item, str):
            sources.update(_advisory_sources(item, vulnerabilities, next_path))
        elif isinstance(item, dict) and isinstance(item.get("url"), str):
            sources.add(item["url"])
        else:
            raise ValueError(f"npm audit advisory source is incomplete: {name}")
    return sources


def validate(report_path, lock_path, latest_picomatch):
    report = json.loads(Path(report_path).read_text(encoding="utf-8"))
    if not isinstance(report, dict):
        raise ValueError("npm audit did not return a JSON object")
    if report.get("error"):
        raise ValueError(f"npm audit failed: {report['error']}")

    metadata = report.get("metadata")
    counts = metadata.get("vulnerabilities") if isinstance(metadata, dict) else None
    vulnerabilities = report.get("vulnerabilities")
    if not isinstance(counts, dict) or not isinstance(vulnerabilities, dict):
        raise ValueError("npm audit did not return a complete vulnerability report")
    if any(not isinstance(item, dict) for item in vulnerabilities.values()):
        raise ValueError("npm audit returned a malformed vulnerability entry")
    print("advisories:", json.dumps(counts, sort_keys=True))

    high_findings = {
        name: item
        for name, item in vulnerabilities.items()
        if item.get("severity") == "high"
    }
    critical_count = counts.get("critical", 0)
    high_count = counts.get("high", 0)
    if not isinstance(critical_count, int) or not isinstance(high_count, int):
        raise ValueError("npm audit severity counts are malformed")
    if critical_count or any(item.get("severity") == "critical" for item in vulnerabilities.values()):
        raise ValueError("critical npm advisories are not allowed")
    if high_count != len(high_findings):
        raise ValueError("npm audit high-severity summary does not match its findings")
    if not high_findings:
        return

    sources = set()
    for name in high_findings:
        sources.update(_advisory_sources(name, vulnerabilities))
    if sources != {ALLOWED_ADVISORY}:
        unexpected = sorted(sources - {ALLOWED_ADVISORY})
        raise ValueError(f"unapproved high-severity npm advisory sources: {unexpected}")

    picomatch = vulnerabilities.get("picomatch", {})
    if "picomatch" not in high_findings:
        raise ValueError("the allowlisted picomatch advisory is no longer high severity")
    picomatch_via = picomatch.get("via")
    if not isinstance(picomatch_via, list):
        raise ValueError("the upstream picomatch advisory details are malformed")
    matching_advisories = [
        item
        for item in picomatch_via
        if isinstance(item, dict) and item.get("url") == ALLOWED_ADVISORY
    ]
    if len(matching_advisories) != 1 or matching_advisories[0].get("range") != "<=4.0.7":
        raise ValueError("the upstream picomatch advisory no longer matches the reviewed range")

    lock = json.loads(Path(lock_path).read_text(encoding="utf-8"))
    packages = lock.get("packages") if isinstance(lock, dict) else None
    if not isinstance(packages, dict):
        raise ValueError("the DSH npm lockfile has no package map")
    installed_versions = [
        package.get("version")
        for package_path, package in packages.items()
        if re.search(r"(?:^|/)node_modules/picomatch$", package_path)
        and isinstance(package, dict)
    ]
    if not installed_versions or set(installed_versions) != {VULNERABLE_PICOMATCH}:
        raise ValueError(
            f"DSH picomatch lock entries changed; expected only {VULNERABLE_PICOMATCH}, "
            f"got {installed_versions}"
        )
    if latest_picomatch != VULNERABLE_PICOMATCH:
        raise ValueError(
            f"picomatch {latest_picomatch} is now the latest npm release; "
            "remove the temporary upstream advisory exception after DSH adopts a fixed release"
        )

    print(
        "::warning::Allowing only the currently unpatched upstream picomatch advisory "
        f"{ALLOWED_ADVISORY}; latest npm release and DSH lock both remain {VULNERABLE_PICOMATCH}."
    )


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit(
            "usage: validate_dsh_next_audit.py AUDIT_JSON PACKAGE_LOCK_JSON LATEST_PICOMATCH_VERSION"
        )
    try:
        validate(sys.argv[1], sys.argv[2], sys.argv[3])
    except (OSError, json.JSONDecodeError, ValueError) as error:
        raise SystemExit(str(error)) from error
