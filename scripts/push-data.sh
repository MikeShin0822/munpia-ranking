#!/usr/bin/env bash
# Publish committed data only. Never force-push or choose a conflict winner.
set -euo pipefail
branch=${1:?Usage: push-data.sh TARGET_BRANCH}
git check-ref-format "refs/heads/$branch" >/dev/null
attempts=${PUSH_MAX_ATTEMPTS:-4}
delay=${PUSH_RETRY_DELAY:-2}
[[ $attempts =~ ^[1-4]$ && $delay =~ ^[0-9]+$ ]] || exit 2
[[ -z $(git status --porcelain --untracked-files=no) ]] || {
  echo 'Tracked changes must be committed before publishing.' >&2; exit 1;
}
mkdir -p .automation-diagnostics
# A full bundle also works when HEAD is detached, and retains rejected data.
git bundle create .automation-diagnostics/unpublished.bundle HEAD
for ((attempt=1; attempt<=attempts; attempt++)); do
  git fetch --no-tags origin "refs/heads/$branch:refs/remotes/origin/$branch"
  remote="refs/remotes/origin/$branch"
  base=$(git merge-base HEAD "$remote")
  # Even a clean textual merge of the same generated JSON can lose semantics.
  overlap=$(comm -12 \
    <(git diff --name-only "$base" HEAD | LC_ALL=C sort) \
    <(git diff --name-only "$base" "$remote" | LC_ALL=C sort))
  if [[ -n $overlap ]]; then
    echo "Refusing overlapping generated changes; remote data preserved: $overlap" >&2
    exit 1
  fi
  if ! git rebase "$remote"; then
    git rebase --abort
    echo 'Rebase conflict; unpublished commits are retained in the bundle.' >&2
    exit 1
  fi
  if git push --porcelain origin "HEAD:refs/heads/$branch" >.automation-diagnostics/push.log 2>&1; then
    cat .automation-diagnostics/push.log
    rm -f .automation-diagnostics/unpublished.bundle
    exit 0
  fi
  cat .automation-diagnostics/push.log >&2
  # Retry only the race between fetch/rebase and a non-fast-forward push.
  if ! grep -Eq '\[rejected\].*\((fetch first|non-fast-forward)\)' .automation-diagnostics/push.log; then
    exit 1
  fi
  if ((attempt < attempts)); then sleep "$((delay * attempt))"; fi
done
echo "Concurrent pushes continued after $attempts attempts; data retained in bundle." >&2
exit 1
