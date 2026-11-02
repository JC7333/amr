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


@pytest.mark.parametrize("text", [README, AGENTS, LLMS], ids=["README", "AGENTS", "llms"])
def test_docs_warn_that_uvx_amr_is_another_project(text: str) -> None:
    assert re.search(r"`uvx amr` installs a different", text)


def test_client_configurations_use_the_package() -> None:
    assert "claude mcp add amr -- uvx mandatia\n" in README
    assert '"args": ["mandatia"]' in README


# --- publication workflow --------------------------------------------------------------


def test_workflow_runs_only_on_version_tags() -> None:
    trigger = WORKFLOW[WORKFLOW.index("\non:") : WORKFLOW.index("\npermissions:")]
    assert 'tags: ["v*"]' in trigger
    assert "pull_request" not in trigger
    assert "branches" not in trigger
    assert "workflow_dispatch" not in trigger


def test_workflow_uses_trusted_publishing_without_stored_token() -> None:
    assert "pypa/gh-action-pypi-publish@release/v1" in WORKFLOW
    assert "password" not in WORKFLOW
    assert "secrets." not in WORKFLOW
    assert "PYPI_" not in WORKFLOW.upper().replace("PYPI_PUBLISH", "")


def test_only_the_publish_job_may_request_an_identity_token() -> None:
    assert WORKFLOW.count("id-token: write") == 1
    top_level = WORKFLOW[: WORKFLOW.index("\njobs:")]
    assert "permissions:\n  contents: read\n" in top_level
    publish_job = WORKFLOW[WORKFLOW.index("\n  publish:") :]
    assert "id-token: write" in publish_job
    assert "environment: pypi" in publish_job
    assert "needs: build" in publish_job


def test_workflow_checks_tag_tests_and_lints_before_building() -> None:
    build_job = WORKFLOW[WORKFLOW.index("\n  build:") : WORKFLOW.index("\n  publish:")]
    steps = [
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
    assert top <= allowed | {"server.json", "LICENSE", "pyproject.toml", "PKG-INFO", ".gitignore"}, top
    assert not [n for n in names if n.endswith((".pem", ".key", ".db", ".sqlite", ".ps1"))]
