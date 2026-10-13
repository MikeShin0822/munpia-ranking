# Safe automated publication

The collectors keep their existing schedules, ranking schemas, and collection
commands. Four workflows write data: `collect`, `collect-free-today`,
`collect-new-best`, and `verify-public`. All five publication steps now use
`scripts/push-data.sh` (daily collection also records a live verification).

## Serialization and safe publication

All four share `munpia-data-${{ github.head_ref || github.ref_name }}` for the
**whole workflow**, with `cancel-in-progress: false` and `queue: max`. Locking
before checkout/collection prevents a queued collector from building its history
on a stale base. Explicit branch checkout and full history enable a correct merge
base and keep manual feature-branch tests from writing to main.

GitHub's default queue retains only one pending run, replacing earlier pending
runs even with cancellation disabled. `queue: max` retains up to 100 pending runs;
overflow is still canceled by GitHub. Ordering follows when runs enter the queue,
not their schedule timestamps. The tradeoff is longer elapsed time when runs
collide; cron expressions are unchanged. The 20-minute job timeout bounds a stuck
writer. External/manual pushes do not participate in this lock.

Reference: https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency

Before each push the helper fetches the target branch, compares file changes
since the merge base, and rebases local commits onto that exact fetched history.

- Disjoint changes: rebase retains both writers' files and enables a normal
  fast-forward push. This is simpler than a merge commit for generated data.
- Any shared changed path: stop without choosing a winner, even when Git could
  merge different lines. Generated JSON includes histories, indexes and latest
  snapshots; a clean textual merge does not establish semantic correctness.
- A push race after the fetch: retry only explicit `fetch first` or
  `non-fast-forward` rejection, at most four total attempts (2/4/6-second waits).
- Authentication, branch policy, transport, fetch and real rebase errors: fail;
  do not blindly repeat, force-push, reset away local data or auto-resolve conflicts.

Before publication a self-contained Git bundle retains HEAD and its history.
On failure, the workflow uploads `.automation-diagnostics/`, including this
bundle and the last push response, for 14 days. Remote commits are never replaced.
On success the bundle is removed. A same-file collision deliberately needs review;
this solution promises preservation, not automatic semantic merging of arbitrary
concurrent snapshots.

Recovery: download the diagnostics artifact and run
`git clone unpublished.bundle recovered`. Inspect `recovered`, compare with the
current remote data, and merge the needed observations on a review branch. Do not
copy an old `latest.json` over a newer one. The artifact expires after 14 days.

## Public verification

`verify-public.py` preserves all existing report fields and UI checks, and uses
JSON parsing instead of formatting-dependent grep for data. It checks complete
1..200 ranks, the free-today visible/unavailable counts and cutoffs, matching
index/latest collection times, and the existing weekly-report invariants.

The expected KST date is captured once at the start of the run. Each attempt
requests every public resource again with bounded HTTP timeouts and a unique
cache-busting query. There are at most five attempts, with waits of 15/30/60/60
seconds. All required checks must pass in the same attempt.

When public data checks fail, fetch main once and read every diagnostic source
file from that **one immutable commit** using `git show`:

| Evidence | Classification and action |
| --- | --- |
| Same failed invariant is also invalid in source | `source_data_incomplete`: fail immediately; waiting for CDN propagation cannot repair it. Includes stale dates and source schema defects. |
| Source passes the failed public checks | `propagation_delay_suspected`: retry. This is evidence of divergence, not proof that a CDN caused it. |
| Source cannot be fetched | `source_unavailable`: retry, then fail without claiming source corruption. |
| HTTP/UI/JS check fails | `publication_or_transport_failure`: retry, then fail if unresolved. |
| All checks pass after a retry | `recovered_after_retry`: record success, retain failed-attempt details in logs. |

Persistent public divergence remains a failure after the retry budget. It is not
silently accepted as propagation delay. Source repair during the retry window is
not required: an already-incomplete source is actionable and fails immediately.
The writer lock would also prevent queued collectors from repairing it during
this verifier, so waiting in that case would be counterproductive.

Failed checks never replace the last successful `data/public-verification.json`.
Each attempt writes a diagnostic JSON with failed keys, reasons, HTTP errors,
classification, and (when available) the source commit. Failure artifacts retain
these observations independently of a successful data commit. Ranking data and
public report schemas are unchanged.

## Validation boundaries

Run `npm test`, `python -m unittest discover -s tests -v`, and
`bash -n scripts/push-data.sh`. The new PR workflow performs only these offline
checks with read-only permissions; it does not collect Munpia data or check the
live dashboard.

Tests use real temporary bare Git repositories for disjoint writes, same-file
conflicts, fetch/push races, exhaustion, server policy rejection, recovery from a
bundle, dirty worktrees and feature-branch isolation. Public checks use fixtures
for successful, malformed, stale, incomplete and recovering responses.

GitHub's queue behavior and CDN propagation are not reproduced by local tests.
They remain runtime integration behavior to observe after review/merge during
normal scheduled runs. No successful collection or public verification was
manually re-run for this change.
