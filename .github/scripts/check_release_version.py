"""Refuse a release whose tag does not match the version written in the repository.

    python .github/scripts/check_release_version.py v0.1.0

Exit code 0 only if the tag is "v" + the version of pyproject.toml, and server.json
(MCP registry entry) announces the same version and the same PyPI package name.
Standard library only: it runs before any dependency is installed.
"""

import json
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def problems(tag: str, root: Path = ROOT) -> list[str]:
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    server = json.loads((root / "server.json").read_text(encoding="utf-8"))
    name, version = project["name"], project["version"]
    found = []
    if tag != f"v{version}":
        found.append(f"tag {tag!r} is not 'v' + pyproject version {version!r}")
    if server.get("version") != version:
        found.append(f"server.json version {server.get('version')!r} != {version!r}")
    pypi = [p for p in server.get("packages", []) if p.get("registryType") == "pypi"]
    if len(pypi) != 1:
        found.append("server.json must list exactly one pypi package")
    else:
        if pypi[0].get("identifier") != name:
            found.append(f"server.json package {pypi[0].get('identifier')!r} != {name!r}")
        if pypi[0].get("version") != version:
            found.append(f"server.json package version {pypi[0].get('version')!r} != {version!r}")
    return found


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: check_release_version.py <tag>")
        return 2
    found = problems(argv[1])
    for problem in found:
        print(f"release refused: {problem}")
    if not found:
        print(f"release {argv[1]} matches pyproject.toml and server.json")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
