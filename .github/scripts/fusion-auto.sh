#!/usr/bin/env bash
# Auto-merge of ready pull requests (decision of Audric, 2026-10-25: the Atelier's work goes in
# without a click; what commits him keeps waiting for his click).
# A pull request to main is squash-merged (branch deleted) when ALL of these hold:
#   1. head branch atelier/... or fix/... of this repository itself (never a fork, never attente/...);
#   2. no "ne-pas-fusionner" label;
#   3. every GitHub Actions check of the head commit is completed and green, including "Tests + ruff";
#   4. no protected path is touched: signing code and keys (any path containing "signing", *.pem, *.key),
#      databases (*.db, *.sqlite), pyproject.toml, uv.lock, .github/, LICENSE, CLAUDE.md
#      (section 3 e of the Atelier's instructions: these wait for Audric), and the files that
#      configure the tests and the linter (conftest.py, pytest.ini, setup.cfg, tox.ini,
#      ruff.toml, .ruff.toml, .gitignore), so that a pull request cannot weaken the CI that
#      judges it; matching ignores case and also looks at the old name of a renamed file;
#   5. no conflict with main.
# A draft that meets everything is first marked ready, then merged. The merge is pinned to
# the head commit that was checked (--match-head-commit): a commit pushed in between is not
# merged, it waits for its own CI.
# DRY_RUN=1: print the decisions, change nothing.
set -euo pipefail
REPO="${REPO:?REPO missing}"
DRY_RUN="${DRY_RUN:-0}"
merged=0

numbers=$(gh api --paginate "repos/$REPO/pulls?state=open&base=main&per_page=100" --jq '.[].number')

for n in $numbers; do
  pr=$(gh api "repos/$REPO/pulls/$n")
  head=$(jq -r '.head.ref' <<<"$pr")
  sha=$(jq -r '.head.sha' <<<"$pr")
  repo_head=$(jq -r '.head.repo.full_name' <<<"$pr")
  draft=$(jq -r '.draft' <<<"$pr")
  mergeable=$(jq -r '.mergeable' <<<"$pr")
  labels=",$(jq -r '[.labels[].name] | join(",")' <<<"$pr"),"
  title=$(jq -r '.title' <<<"$pr")
  waiting() { echo "#$n waiting: $1 ($title)"; }

  if [[ "$repo_head" != "$REPO" || ! "$head" =~ ^(atelier|fix)/ ]]; then waiting "branch $head not eligible"; continue; fi
  if [[ "$labels" == *",ne-pas-fusionner,"* ]]; then waiting "label ne-pas-fusionner"; continue; fi

  runs=$(gh api "repos/$REPO/commits/$sha/check-runs?per_page=100" --jq '[.check_runs[] | select(.app.slug == "github-actions")]')
  total=$(jq 'length' <<<"$runs")
  running=$(jq '[.[] | select(.status != "completed")] | length' <<<"$runs")
  red=$(jq '[.[] | select(.status == "completed" and .conclusion != "success" and .conclusion != "skipped")] | length' <<<"$runs")
  tests=$(jq '[.[] | select(.name == "Tests + ruff" and .conclusion == "success")] | length' <<<"$runs")
  if (( running > 0 )); then waiting "$running check(s) still running"; continue; fi
  if (( red > 0 )); then waiting "$red red check(s)"; continue; fi
  if (( total == 0 || tests == 0 )); then waiting "\"Tests + ruff\" missing or not green"; continue; fi

  changed=$(jq -r '.changed_files' <<<"$pr")
  files=$(gh api --paginate "repos/$REPO/pulls/$n/files?per_page=100" --jq '.[].filename')
  if [[ "$(grep -c . <<<"$files" || true)" != "$changed" ]]; then waiting "file list incomplete ($changed changed)"; continue; fi
  protected=$( { echo "$files"; gh api --paginate "repos/$REPO/pulls/$n/files?per_page=100" --jq '.[].previous_filename // empty'; } \
    | grep -iE '(signing|\.pem$|\.key$|\.db$|\.sqlite$|^pyproject\.toml$|^uv\.lock$|^\.github/|^LICENSE$|^CLAUDE\.md$|(^|/)conftest\.py$|^pytest\.ini$|^setup\.cfg$|^tox\.ini$|^\.?ruff\.toml$|(^|/)\.gitignore$)' || true)
  if [[ -n "$protected" ]]; then waiting "touches protected path(s): $(tr '\n' ' ' <<<"$protected")(Audric's click)"; continue; fi
  if [[ "$mergeable" != "true" ]]; then waiting "not mergeable or not computed yet (mergeable=$mergeable)"; continue; fi

  if [[ "$DRY_RUN" == "1" ]]; then echo "#$n WOULD BE MERGED ($title)"; continue; fi
  if [[ "$draft" == "true" ]]; then gh pr ready "$n" -R "$REPO" || { waiting "could not mark ready"; continue; }; fi
  if ! gh pr merge "$n" -R "$REPO" --squash --delete-branch --match-head-commit "$sha"; then waiting "merge refused by GitHub"; continue; fi
  echo "#$n merged ($title)"
  merged=$((merged + 1))
done
echo "Done: $merged pull request(s) merged."
