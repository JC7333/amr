# Releases: PyPI package `mandatia` and the official MCP registry

AMR is distributed on PyPI under the name `mandatia` (the name `amr` belongs to an
unrelated project). The Python module stays `amr`; the package installs two commands
that start the same server: `mandatia` and `amr`. An agent installs and starts it with:

```bash
uvx mandatia
```

Nothing below runs by itself: each step is a deliberate action of the repository owner.

## What the repository contains

| File | Role |
|---|---|
| `pyproject.toml` | Package name `mandatia`, version, the two commands |
| `.github/workflows/publish.yml` | On a pushed tag `vX.Y.Z`: checks the tag, runs the tests and ruff, builds, publishes to PyPI |
| `.github/scripts/check_release_version.py` | Refuses a tag that is not `v` + the version of `pyproject.toml`, or a `server.json` that announces another version or package |
| `server.json` | The entry of the official MCP registry (`registry.modelcontextprotocol.io`), name `io.github.JC7333/mandatia` |
| `README.md`, first lines | `<!-- mcp-name: io.github.JC7333/mandatia -->`: the MCP registry reads this line in the PyPI description to accept that the package belongs to this server |

No PyPI token is stored anywhere. PyPI trusts the workflow through trusted publishing
(OpenID Connect): the `publish` job alone gets `id-token: write`, and only inside the
GitHub environment `pypi`.

## First release, once

1. **PyPI account.** Create an account on https://pypi.org (two-factor authentication is
   mandatory there).
2. **Declare the trusted publisher before the project exists** ("pending publisher"):
   pypi.org, Your account, Publishing, "Add a new pending publisher", GitHub tab:
   - PyPI project name: `mandatia`
   - Owner: `JC7333`
   - Repository name: `amr`
   - Workflow name: `publish.yml`
   - Environment name: `pypi`
3. **Merge** the pull request that adds these files.
4. **Tag the version** written in `pyproject.toml` (today `0.1.0`), on main:
   GitHub, Releases, "Draft a new release", "Choose a tag", type `v0.1.0`, target `main`,
   "Publish release". The workflow "Publish to PyPI" starts; when it is green,
   https://pypi.org/project/mandatia/ exists and `uvx mandatia` works anywhere.
5. **Optional, recommended:** GitHub, Settings, Environments, `pypi`, "Required
   reviewers": add yourself, so that each publication waits for your click.

## Official MCP registry

Done after step 4 (the registry checks that the PyPI package exists and that its
description carries the `mcp-name` line). Publishing there is public and lists AMR in
the directory MCP clients read.

1. Install the registry's command line tool `mcp-publisher` (instructions:
   https://github.com/modelcontextprotocol/registry, "Publishing").
2. In a copy of the repository on main: `mcp-publisher login github` (opens a GitHub
   sign-in as JC7333, which owns the namespace `io.github.JC7333`), then
   `mcp-publisher publish`.
3. Check: https://registry.modelcontextprotocol.io/v0/servers?search=mandatia

## Next releases

Raise `version` in `pyproject.toml`, in `server.json` (twice: top level and the
package) and `server_version` in `src/amr/config.py` in the same pull request (a test
checks they agree); after the merge, tag `vX.Y.Z` as in step 4, then
`mcp-publisher publish` again. A version published on PyPI can never be replaced, only
followed by a new one.

## Rolling back

Before the first tag: "Revert" on the pull request page; nothing was published. After a
publication: PyPI lets the owner "yank" a version (hidden from new installs, still
downloadable by exact version); a registry entry is corrected by publishing a new
version. Neither deletes what was published.
