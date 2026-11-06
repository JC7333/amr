"""The PyPI package "mandatia", its publication workflow and the MCP registry entry agree."""

import importlib.util
import json
import re
import shutil
import subprocess
import tarfile
import tomllib
import zipfile
from pathlib import Path

import pytest

from amr.config import Settings

ROOT = Path(__file__).resolve().parent.parent
if not (ROOT / ".github" / "workflows" / "publish.yml").is_file():
    # Running from the source archive published on PyPI, which carries no .github files.
    pytest.skip("release files are only in the repository", allow_module_level=True)

PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
PROJECT = PYPROJECT["project"]
SERVER_JSON = json.loads((ROOT / "server.json").read_text(encoding="utf-8"))
README = (ROOT / "README.md").read_text(encoding="utf-8")
AGENTS = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
LLMS = (ROOT / "llms.txt").read_text(encoding="utf-8")
WORKFLOW = (ROOT / ".github" / "workflows" / "publish.yml").read_text(encoding="utf-8")
CHECK_SCRIPT = ROOT / ".github" / "scripts" / "check_release_version.py"
SCHEMA_URL = "https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json"


def _load_check_module():
    spec = importlib.util.spec_from_file_location("check_release_version", CHECK_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _pypi_package() -> dict:
    packages = [p for p in SERVER_JSON["packages"] if p["registryType"] == "pypi"]
    assert len(packages) == 1
    return packages[0]


# --- pyproject.toml ------------------------------------------------------------------


def test_package_is_published_as_mandatia() -> None:
    # "amr" on PyPI is an unrelated project: publishing under it is impossible.
    assert PROJECT["name"] == "mandatia"


def test_both_commands_start_the_same_server() -> None:
    assert PROJECT["scripts"] == {"amr": "amr.server:main", "mandatia": "amr.server:main"}


def test_wheel_still_ships_the_amr_module() -> None:
    assert PYPROJECT["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"] == ["src/amr"]


def test_versions_agree_everywhere() -> None:
    version = PROJECT["version"]
    assert SERVER_JSON["version"] == version
    assert _pypi_package()["version"] == version
    assert Settings.model_fields["server_version"].default == version


# --- server.json (official MCP registry) -----------------------------------------------


def test_server_json_names_the_pypi_package() -> None:
    package = _pypi_package()
    assert package["identifier"] == PROJECT["name"]
    assert package["registryBaseUrl"] == "https://pypi.org"
    assert package["transport"] == {"type": "stdio"}
    assert package["runtimeHint"] == "uvx"


def test_server_json_respects_registry_schema_limits() -> None:
    assert SERVER_JSON["$schema"] == SCHEMA_URL
    assert re.fullmatch(r"[a-zA-Z0-9.-]+/[a-zA-Z0-9._-]+", SERVER_JSON["name"])
    assert SERVER_JSON["name"].startswith("io.github.JC7333/")
    assert 1 <= len(SERVER_JSON["description"]) <= 100
    assert 1 <= len(SERVER_JSON["title"]) <= 100
    assert SERVER_JSON["repository"] == {"url": "https://github.com/JC7333/amr", "source": "github"}
    for version in (SERVER_JSON["version"], _pypi_package()["version"]):
        assert re.fullmatch(r"\d+\.\d+\.\d+", version), version


def test_auto_merge_waits_for_the_owner_on_server_json() -> None:
    script = (ROOT / ".github" / "scripts" / "fusion-auto.sh").read_text(encoding="utf-8")
    assert "|^server\\.json$|" in script


def test_readme_carries_the_mcp_name_the_registry_checks() -> None:
    # The registry accepts a PyPI package only if its description contains this line.
    assert f"<!-- mcp-name: {SERVER_JSON['name']} -->" in README
    assert PROJECT["readme"] == "README.md"


def test_server_json_environment_variables_are_real_settings() -> None:
    names = {v["name"] for v in _pypi_package()["environmentVariables"]}
    assert names == {"AMR_DB_PATH", "AMR_SIGNING_KEY_PATH", "AMR_PUBLIC_KEY_PATH"}
    for name in names:
        assert name.removeprefix("AMR_").lower() in Settings.model_fields
    assert all(v["isRequired"] is False for v in _pypi_package()["environmentVariables"])


# --- documentation ---------------------------------------------------------------------


@pytest.mark.parametrize("text", [README, AGENTS, LLMS], ids=["README", "AGENTS", "llms"])
def test_uvx_mandatia_is_the_first_install_command(text: str) -> None:
    commands = re.findall(r"^[ \t]*(uvx [^\n]*)$", text, flags=re.MULTILINE)
    assert commands[0] == "uvx mandatia"


def test_client_configurations_use_the_package() -> None:
    assert "claude mcp add amr -- uvx mandatia\n" in README
    assert '"args": ["mandatia"]' in README


@pytest.mark.parametrize("text", [README, AGENTS, LLMS], ids=["README", "AGENTS", "llms"])
def test_docs_warn_that_uvx_amr_is_another_project(text: str) -> None:
    assert re.search(r"`uvx amr` installs a different", text)


# --- publication workflow --------------------------------------------------------------


def test_workflow_runs_only_on_version_tags() -> None:
    trigger = WORKFLOW[WORKFLOW.index("\non:") + 1 : WORKFLOW.index("\npermissions:")]
    lines = [line for line in trigger.splitlines() if line.strip()]
    assert lines == ["on:", "  push:", '    tags: ["v*"]']


def test_workflow_publishes_only_commits_already_on_main() -> None:
    assert "fetch-depth: 0" in WORKFLOW
    assert 'git merge-base --is-ancestor "$GITHUB_SHA" origin/main' in WORKFLOW


def test_release_build_uses_the_lockfile_and_no_shared_cache() -> None:
    assert "uv sync --locked --extra dev" in WORKFLOW
    assert "enable-cache: false" in WORKFLOW
    assert "uv sync --extra dev" not in WORKFLOW


def test_workflow_uses_trusted_publishing_without_stored_token() -> None:
    assert "pypa/gh-action-pypi-publish@release/v1" in WORKFLOW
    assert "password" not in WORKFLOW
    assert "secrets" not in WORKFLOW
    assert "PYPI_" not in WORKFLOW.upper()


JOBS = ("build", "publish", "registry")


def _job(name: str) -> str:
    """Text of one job of publish.yml, up to the next job."""
    starts = {job: WORKFLOW.index(f"\n  {job}:") for job in JOBS}
    later = [pos for pos in starts.values() if pos > starts[name]]
    return WORKFLOW[starts[name] : min(later) if later else len(WORKFLOW)]


def test_workflow_has_exactly_the_expected_jobs() -> None:
    jobs = WORKFLOW[WORKFLOW.index("\njobs:") :]
    assert re.findall(r"^  ([a-z][a-z0-9_-]*):$", jobs, flags=re.MULTILINE) == list(JOBS)


def test_only_the_publish_and_registry_jobs_may_request_an_identity_token() -> None:
    top_level = WORKFLOW[: WORKFLOW.index("\njobs:")]
    assert "permissions:\n  contents: read\n" in top_level
    assert "id-token" not in top_level
    assert "id-token" not in _job("build")
    assert _job("publish").count("id-token: write") == 1
    assert _job("registry").count("id-token: write") == 1
    assert WORKFLOW.count("id-token: write") == 2
    assert "environment: pypi" in _job("publish")
    assert "needs: build" in _job("publish")


def test_registry_job_cannot_publish_to_pypi() -> None:
    # PyPI accepts an identity token from this workflow only in the environment "pypi":
    # the registry job runs outside any environment, so its token is useless on PyPI.
    registry = _job("registry")
    assert "environment:" not in registry
    assert "pypa/gh-action-pypi-publish" not in registry
    assert WORKFLOW.count("pypa/gh-action-pypi-publish") == 1
    assert WORKFLOW.count("environment:") == 1


def test_registry_job_lists_the_version_only_after_pypi_serves_it() -> None:
    registry = _job("registry")
    assert "needs: publish" in registry
    steps = [
        "name: mcp-publisher",
        'version="${GITHUB_REF_NAME#v}"',
        "https://pypi.org/pypi/mandatia/${version}/json",
        "publisher/mcp-publisher login github-oidc",
        "publisher/mcp-publisher publish",
    ]
    positions = [registry.index(step) for step in steps]
    assert positions == sorted(positions)


def test_registry_job_cannot_be_skipped_silently_or_hold_a_git_token() -> None:
    registry = _job("registry")
    for forbidden in ("continue-on-error", "if:", "ref:", "cosign", "curl --fail --location"):
        assert forbidden not in registry, forbidden
    assert "persist-credentials: false" in registry
    assert re.search(r"timeout-minutes: \d+\n", registry)
    assert "--max-time" in registry


def test_publisher_is_pinned_and_its_signature_checked_before_pypi() -> None:
    # A wrong pin, asset name or signer must fail in the build job, before anything reaches PyPI.
    top_level = WORKFLOW[: WORKFLOW.index("\njobs:")]
    assert re.search(r"\nenv:\n  MCP_PUBLISHER_VERSION: v\d+\.\d+\.\d+\n", top_level)
    assert "releases/latest" not in WORKFLOW
    assert WORKFLOW.count("MCP_PUBLISHER_VERSION:") == 1
    build = _job("build")
    assert re.search(r"sigstore/cosign-installer@[0-9a-f]{40} ", build)
    url = "releases/download/${MCP_PUBLISHER_VERSION}"
    assert url in build
    identity = (
        "https://github.com/modelcontextprotocol/registry/.github/workflows/release.yml"
        "@refs/tags/${MCP_PUBLISHER_VERSION}"
    )
    assert f'--certificate-identity "{identity}"' in build
    assert '--certificate-oidc-issuer "https://token.actions.githubusercontent.com"' in build
    # The verified binary is handed over as an artifact; the archive is checked before use.
    steps = ["run: uv build", "cosign verify-blob", 'tar xzf "$archive" mcp-publisher']
    steps.append("name: mcp-publisher")
    positions = [build.index(step) for step in steps]
    assert positions == sorted(positions)
    assert "set -euo pipefail" in build
    assert "name: mcp-publisher" not in _job("publish")


def test_registry_login_uses_oidc_and_no_token() -> None:
    registry = _job("registry")
    assert registry.count("mcp-publisher login") == 1
    assert "mcp-publisher login github-oidc" in registry
    for forbidden in ("--token", "MCP_GITHUB_TOKEN", "GITHUB_TOKEN", "secrets."):
        assert forbidden not in WORKFLOW, forbidden


def test_workflow_checks_tag_tests_and_lints_before_building() -> None:
    build_job = WORKFLOW[WORKFLOW.index("\n  build:") : WORKFLOW.index("\n  publish:")]
    steps = [
        "git merge-base --is-ancestor",
        'check_release_version.py "$GITHUB_REF_NAME"',
        "uv run python -m pytest -q",
        "uv run python -m ruff check src/",
        "uv build",
    ]
    positions = [build_job.index(step) for step in steps]
    assert positions == sorted(positions)


# --- release version check -------------------------------------------------------------


def test_release_check_accepts_the_matching_tag() -> None:
    assert _load_check_module().problems(f"v{PROJECT['version']}") == []


@pytest.mark.parametrize("tag", ["v9.9.9", PROJECT["version"], "", "vv0.1.0"])
def test_release_check_refuses_a_wrong_tag(tag: str) -> None:
    assert _load_check_module().problems(tag)


def _copy_release_files(tmp_path: Path, server: dict) -> Path:
    (tmp_path / "pyproject.toml").write_text(
        (ROOT / "pyproject.toml").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (tmp_path / "server.json").write_text(json.dumps(server), encoding="utf-8")
    return tmp_path


@pytest.mark.parametrize(
    "change",
    [
        lambda s: s.update(version="9.9.9"),
        lambda s: s["packages"][0].update(version="9.9.9"),
        lambda s: s["packages"][0].update(identifier="amr"),
        lambda s: s.update(packages=[]),
        lambda s: s.update(packages=s["packages"] * 2),
    ],
    ids=["server-version", "package-version", "package-name", "no-package", "two-packages"],
)
def test_release_check_refuses_a_server_json_that_disagrees(tmp_path: Path, change) -> None:
    server = json.loads(json.dumps(SERVER_JSON))
    change(server)
    root = _copy_release_files(tmp_path, server)
    assert _load_check_module().problems(f"v{PROJECT['version']}", root=root)


def test_release_check_script_exit_codes(tmp_path: Path) -> None:
    module = _load_check_module()
    assert module.main(["check", f"v{PROJECT['version']}"]) == 0
    assert module.main(["check", "v9.9.9"]) == 1
    assert module.main(["check"]) == 2


# --- the built wheel -------------------------------------------------------------------


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv is not installed")
def test_built_wheel_is_mandatia_with_both_commands(tmp_path: Path) -> None:
    result = subprocess.run(  # noqa: S603 - fixed arguments, no user input
        ["uv", "build", "--wheel", "--out-dir", str(tmp_path), str(ROOT)],  # noqa: S607
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    wheels = list(tmp_path.glob("*.whl"))
    assert [w.name for w in wheels] == [f"mandatia-{PROJECT['version']}-py3-none-any.whl"]
    with zipfile.ZipFile(wheels[0]) as wheel:
        names = wheel.namelist()
        info = f"mandatia-{PROJECT['version']}.dist-info"
        metadata = wheel.read(f"{info}/METADATA").decode()
        entry_points = wheel.read(f"{info}/entry_points.txt").decode()
    assert "amr/server.py" in names
    assert not [n for n in names if n.endswith((".pem", ".key", ".db", ".sqlite"))]
    assert "Name: mandatia\n" in metadata
    assert f"<!-- mcp-name: {SERVER_JSON['name']} -->" in metadata
    assert "amr = amr.server:main" in entry_points
    assert "mandatia = amr.server:main" in entry_points


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv is not installed")
def test_source_archive_carries_only_code_tests_and_docs(tmp_path: Path) -> None:
    result = subprocess.run(  # noqa: S603 - fixed arguments, no user input
        ["uv", "build", "--sdist", "--out-dir", str(tmp_path), str(ROOT)],  # noqa: S607
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    (archive,) = tmp_path.glob("*.tar.gz")
    with tarfile.open(archive) as sdist:
        names = [n.split("/", 1)[1] for n in sdist.getnames() if "/" in n]
    assert "src/amr/server.py" in names
    assert "LICENSE" in names
    assert "tests/test_release_packaging.py" in names
    top = {n.split("/")[0] for n in names}
    allowed = {"src", "tests", "docs", "examples", "README.md", "AGENTS.md", "llms.txt"}
    allowed |= {"server.json", "LICENSE", "pyproject.toml", "PKG-INFO", ".gitignore"}
    assert top <= allowed, top
    assert not [n for n in names if n.endswith((".pem", ".key", ".db", ".sqlite", ".ps1"))]
