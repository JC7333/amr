# Releases: PyPI package `mandatia` and the official MCP registry

AMR is distributed on PyPI under the name `mandatia` (the name `amr` belongs to an
unrelated project). The Python module stays `amr`; the package installs two commands
that start the same server: `mandatia` and `amr`. Once the first release is on PyPI, an
agent installs and starts it with:

```bash
uvx mandatia
```

Nothing below runs by itself: each step is a deliberate action of the repository owner.

## What the repository contains

| File | Role |
|---|---|
| `pyproject.toml` | Package name `mandatia`, version, the two commands |
| `.github/workflows/publish.yml` | On a pushed tag `vX.Y.Z`: checks the tag, runs the tests and ruff, builds, publishes to PyPI, then lists the version in the official MCP registry |
| `.github/scripts/check_release_version.py` | Refuses a tag that is not `v` + the version of `pyproject.toml`, or a `server.json` that announces another version or package |
| `server.json` | The entry of the official MCP registry (`registry.modelcontextprotocol.io`), name `io.github.JC7333/mandatia` |
| `README.md`, first lines | `<!-- mcp-name: io.github.JC7333/mandatia -->`: the MCP registry reads this line in the PyPI description to accept that the package belongs to this server |

No PyPI token is stored anywhere. PyPI trusts the workflow through trusted publishing
(OpenID Connect): only the `publish` and `registry` jobs request an identity token, and PyPI
accepts it only from the workflow `publish.yml` running in the GitHub environment `pypi`,
which only the `publish` job uses. The
workflow refuses a tag whose commit is not already on main.

## First release, once

Order matters: the documentation tells agents to run `uvx mandatia` only after the name
is taken by the first upload (a pending publisher does not reserve the name on PyPI).
That change is a separate pull request, merged after step 5.

1. **PyPI account.** Create an account on https://pypi.org (two-factor authentication is
   mandatory there).
2. **Declare the trusted publisher before the project exists** ("pending publisher"):
   pypi.org, Your account, Publishing, "Add a new pending publisher", GitHub tab:
   - PyPI project name: `mandatia`
   - Owner: `JC7333`
   - Repository name: `amr`
   - Workflow name: `publish.yml`
   - Environment name: `pypi`
3. **Lock publication to your click** (before any tag): GitHub, repository JC7333/amr,
   Settings, Environments, New environment `pypi`; tick "Required reviewers" and add
   yourself; under "Deployment branches and tags", choose "Selected branches and tags"
   and add the tag rule `v*`. Then Settings, Rules, Rulesets, New tag ruleset: target
   `v*`, rules "Restrict creations", "Restrict updates" and "Restrict deletions",
   bypass list: you only.
4. **Merge** the pull request that adds these files.
5. **Tag the version** written in `pyproject.toml` (first release: `0.1.0`, 2026-11-05), on main:
   GitHub, Releases, "Draft a new release", "Choose a tag", type `v0.1.0`, target `main`,
   "Publish release". The workflow "Publish to PyPI" checks and builds, then waits for
   your approval ("Review deployments", Approve). When it is green,
   https://pypi.org/project/mandatia/ exists and `uvx mandatia` works anywhere.
6. **Merge** the pull request that makes `uvx mandatia` the first command of the
   documentation.

## Official MCP registry

Automatic since 0.1.1: after the job "Publish to PyPI", the job "List in the official MCP
registry" of `publish.yml` waits until PyPI serves the new version (the registry checks
that the package exists and that its description carries the `mcp-name` line), then runs
`mcp-publisher login github-oidc` and `mcp-publisher publish`. No token: the registry
trusts GitHub's identity token for the owner `JC7333`, which gives the namespace
`io.github.JC7333`. The job runs outside the environment `pypi`, so its token cannot
publish to PyPI. `mcp-publisher` is pinned (`MCP_PUBLISHER_VERSION`) and its signature is
checked with cosign before use. Publishing there is public and lists AMR in the
directory MCP clients read.

Check: https://registry.modelcontextprotocol.io/v0/servers?search=mandatia

By hand, only if the job fails: install `mcp-publisher`
(https://github.com/modelcontextprotocol/registry, "Publishing"), then in a copy of the
repository on the tagged commit `mcp-publisher login github` (GitHub sign-in as JC7333)
and `mcp-publisher publish`.

## Directories that read the code

Some MCP directories list a server's tools by reading its source code, and only see
functions declared with a decorator (`@mcp.tool`). AMR registers its tools in a loop
(`src/amr/server.py`, so that `AMR_TOOL_PROFILE` can choose them), and these directories
show no tool. They accept the `tools/list` response pasted by hand instead. Print it
with:

```bash
uv run python -m amr.tools_list --profile full        # from a copy of the repository
uvx --from mandatia python -m amr.tools_list --profile full   # from the version on PyPI
```

The output is the JSON a real MCP client receives from `tools/list` for that profile
(`full`, `principal`, `agent` or `receiver`; default: `AMR_TOOL_PROFILE`, else `full`);
a test starts the server over stdio and checks they are identical. Nothing is started,
written or sent. After a release that adds, removes or changes a tool, paste the
`--profile full` output of the published version wherever a directory asks for it.

## Next releases

Raise `version` in `pyproject.toml`, in `server.json` (twice: top level and the
package) and `server_version` in `src/amr/config.py` in the same pull request (a test
checks they agree); after the merge, tag `vX.Y.Z` as in step 5: the same approval
publishes on PyPI, then lists the version in the MCP registry; if a tool changed, paste
the new `tools/list` output in the directories that read the code (section above). A version published on PyPI can never be replaced, only
followed by a new one. Machines that already ran `uvx mandatia` keep their cached version
until `uvx mandatia@latest` (or `uv cache clean`).

## Rolling back

Before the first tag: "Revert" on the pull request page; nothing was published. After a
publication: PyPI lets the owner "yank" a version (hidden from new installs, still
downloadable by exact version); a registry entry is corrected by publishing a new
version. Neither deletes what was published.
