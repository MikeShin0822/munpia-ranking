"""Offline regression tests. No Munpia requests, public checks or GitHub writes."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('verify_public', ROOT / 'scripts/verify-public.py')
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


class PublicVerificationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.resources = {}
        self.expected = '2026-10-13'
        daily = {'status': 'complete', 'count': 200, 'rankings': [{'rank': n} for n in range(1, 201)],
                 'collectedAt': self.expected + 'T11:00:00+09:00', 'visibleCount': 198,
                 'unavailableCount': 2, 'cutoffs': dict.fromkeys(['10', '20', '50', '100', '200'], 1)}
        index = {'latestDate': self.expected, 'updatedAt': daily['collectedAt']}
        weekly = {'startDate': '2026-10-05', 'endDate': '2026-10-11',
                  'dataQuality': {'complete': True, 'expectedDays': 7, 'collectedDays': 7},
                  'analysisMethod': 'llm_semantic_with_quantitative_support', 'patterns': [{}] * 8}
        docs = {'ranking': {'snapshots': [{}]}, 'newBestIndex': index, 'newBestLatest': daily,
                'freeTodayIndex': index, 'freeTodayLatest': daily, 'weeklyPatternLatest': weekly,
                'weeklyPatternIndex': {'latestKey': '2026-10-05_2026-10-11',
                                       'reports': [{'key': '2026-10-05_2026-10-11'}, {'key': 'previous'}]}}
        for key, doc in docs.items():
            self.resources[key] = {'status': 200, 'text': json.dumps(doc)}
        self.resources['site'] = {'status': 200, 'text': '문피아 제목 레이더 data-view="new-best" NEW BEST RADAR id="new-best-rising" id="new-best-falling" 급상승 · 급하락 id="cutoff-chart" 조회수 컷 일중 변화'}
        for prefix, folder, label in [('newBest', 'new-best', ''), ('freeToday', 'free-today', 'FREE TODAY RADAR'), ('weeklyPattern', 'weekly-patterns', 'WEEKLY TITLE GRAMMAR')]:
            self.resources[prefix + 'Js'] = {'status': 200, 'text': f"// button.dataset.view = '{folder}' {label} {folder}-view"}
            self.resources[prefix + 'Css'] = {'status': 200, 'text': ''}
        self.waits = []

    def change(self, resources, key, **changes):
        doc = json.loads(resources[key]['text']); doc.update(changes)
        resources[key]['text'] = json.dumps(doc)

    def run_verify(self, responses, canonical=None):
        calls = []
        def public(attempt):
            calls.append(attempt)
            return responses[min(attempt - 1, len(responses) - 1)]
        source = canonical if callable(canonical) else lambda: ('test-sha', canonical or self.resources)
        ok = verifier.verify(self.expected, public, source, self.waits.append,
                             self.directory, self.directory / 'result.json', delays=(0, 0))
        return ok, calls, json.loads((self.directory / 'public-attempts.json').read_text())

    def test_complete_first_pass_and_legacy_report_keys(self):
        ok, calls, history = self.run_verify([self.resources])
        self.assertTrue(ok); self.assertEqual(calls, [1]); self.assertEqual(self.waits, [])
        report = json.loads((self.directory / 'result.json').read_text())
        old = json.loads((ROOT / 'data/public-verification.json').read_text())
        self.assertEqual(set(report), set(old))

    def test_stale_public_recovers_without_accepting_initial_failure(self):
        stale = copy.deepcopy(self.resources)
        self.change(stale, 'freeTodayIndex', latestDate='2026-10-12')
        ok, calls, history = self.run_verify([stale, self.resources])
        self.assertTrue(ok); self.assertEqual(calls, [1, 2])
        self.assertEqual(history[0]['classification'], 'propagation_delay_suspected')
        self.assertEqual(history[1]['classification'], 'recovered_after_retry')

    def test_incomplete_source_fails_immediately_and_preserves_last_success(self):
        incomplete = copy.deepcopy(self.resources)
        self.change(incomplete, 'freeTodayLatest', count=199)
        output = self.directory / 'result.json'; output.write_text('previous-success')
        ok, calls, history = self.run_verify([incomplete], incomplete)
        self.assertFalse(ok); self.assertEqual(calls, [1]); self.assertEqual(self.waits, [])
        self.assertEqual(history[0]['classification'], 'source_data_incomplete')
        self.assertEqual(output.read_text(), 'previous-success')

    def test_persistent_public_mismatch_exhausts_retries(self):
        invalid = copy.deepcopy(self.resources)
        self.change(invalid, 'freeTodayLatest', count=199)
        ok, calls, history = self.run_verify([invalid])
        self.assertFalse(ok); self.assertEqual(calls, [1, 2, 3]); self.assertEqual(len(self.waits), 2)
        self.assertFalse((self.directory / 'result.json').exists())

    def test_http_error_and_malformed_json_recover(self):
        bad_http = copy.deepcopy(self.resources); bad_http['freeTodayLatest'] = {'status': 503, 'text': ''}
        bad_json = copy.deepcopy(self.resources); bad_json['freeTodayLatest']['text'] = '{'
        ok, calls, _ = self.run_verify([bad_http, bad_json, self.resources])
        self.assertTrue(ok); self.assertEqual(len(calls), 3)

    def test_rank_holes_and_generation_mismatch_are_rejected(self):
        for changes in [{'rankings': [{'rank': 1}] * 200}, {'visibleCount': 197},
                        {'collectedAt': '2026-10-13T12:00:00+09:00'}]:
            with self.subTest(changes=list(changes)):
                bad = copy.deepcopy(self.resources); self.change(bad, 'freeTodayLatest', **changes)
                checks, _ = verifier.check_data(bad, self.expected)
                self.assertFalse(checks['freeTodayDataComplete'])

    def test_wrong_json_root_is_a_validation_failure(self):
        bad = copy.deepcopy(self.resources)
        bad['weeklyPatternLatest']['text'] = '[]'
        checks, _ = verifier.check_data(bad, self.expected)
        self.assertFalse(checks['weeklyPatternDataComplete'])

    def test_source_unavailable_is_not_reported_as_data_loss(self):
        bad = copy.deepcopy(self.resources); bad['freeTodayLatest']['status'] = 0
        def unavailable():
            raise subprocess.CalledProcessError(1, 'git fetch')
        ok, calls, history = self.run_verify([bad], unavailable)
        self.assertFalse(ok); self.assertEqual(len(calls), 3)
        self.assertEqual(history[-1]['classification'], 'source_unavailable')

    def test_invalid_js_is_not_accepted_after_retries(self):
        bad = copy.deepcopy(self.resources); bad['freeTodayJs']['text'] += '\nconst = ;'
        ok, _, history = self.run_verify([bad])
        self.assertFalse(ok); self.assertIn('freeTodayJsSyntaxOk', history[-1]['failures'])


class GitPublishTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.git = shutil.which('git')
        self.remote = self.root / 'remote.git'
        self.a, self.b = self.root / 'a', self.root / 'b'
        self.run_git(self.root, 'init', '--bare', '--initial-branch=main', str(self.remote))
        self.run_git(self.root, 'clone', str(self.remote), str(self.a))
        self.configure(self.a)
        self.commit(self.a, 'shared.json', 'base')
        self.run_git(self.a, 'push', 'origin', 'main')
        self.run_git(self.root, 'clone', str(self.remote), str(self.b)); self.configure(self.b)

    def run_git(self, cwd, *args):
        return subprocess.run([self.git, '-C', str(cwd), *args], check=True, capture_output=True, text=True).stdout.strip()

    def configure(self, cwd):
        self.run_git(cwd, 'config', 'user.name', 'test')
        self.run_git(cwd, 'config', 'user.email', 'test@example.invalid')

    def commit(self, cwd, path, text):
        (cwd / path).write_text(text)
        self.run_git(cwd, 'add', path); self.run_git(cwd, 'commit', '-m', path)

    def publish(self, branch='main', env=None):
        return subprocess.run(['bash', str(ROOT / 'scripts/push-data.sh'), branch], cwd=self.a,
                              env={**os.environ, 'PUSH_RETRY_DELAY': '0', **(env or {})}, capture_output=True, text=True)

    def remote_content(self, path, branch='main'):
        return self.run_git(self.remote, 'show', f'{branch}:{path}')

    def test_unrelated_remote_data_preserved(self):
        self.commit(self.a, 'ours.json', 'ours')
        self.commit(self.b, 'theirs.json', 'theirs'); self.run_git(self.b, 'push', 'origin', 'main')
        result = self.publish(); self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.remote_content('ours.json'), 'ours')
        self.assertEqual(self.remote_content('theirs.json'), 'theirs')

    def test_same_file_conflict_keeps_remote_and_recoverable_local(self):
        self.commit(self.a, 'shared.json', 'ours')
        self.commit(self.b, 'shared.json', 'theirs'); self.run_git(self.b, 'push', 'origin', 'main')
        result = self.publish(); self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.remote_content('shared.json'), 'theirs')
        self.assertEqual((self.a / 'shared.json').read_text(), 'ours')
        bundle = self.a / '.automation-diagnostics/unpublished.bundle'
        self.run_git(self.a, 'bundle', 'verify', str(bundle))
        recovered = self.root / 'recovered'
        self.run_git(self.root, 'clone', str(bundle), str(recovered))
        self.assertEqual((recovered / 'shared.json').read_text(), 'ours')

    def race_environment(self, always=False):
        wrappers = self.root / 'bin'; wrappers.mkdir()
        # A real competing commit is pushed just before our actual push.
        wrapper = wrappers / 'git'
        wrapper.write_text('''#!/usr/bin/env bash
if [[ $1 == push ]]; then
  count=0; [[ ! -f "$RACE_COUNT" ]] || count=$(cat "$RACE_COUNT")
  echo $((count+1)) > "$RACE_COUNT"
  if [[ $count == 0 || $RACE_ALWAYS == 1 ]]; then
    echo "$count" > "$RACE_REPO/race.json"
    "$REAL_GIT" -C "$RACE_REPO" add race.json
    "$REAL_GIT" -C "$RACE_REPO" commit -m race >/dev/null
    "$REAL_GIT" -C "$RACE_REPO" push origin main >/dev/null 2>&1
  fi
fi
exec "$REAL_GIT" "$@"
'''); wrapper.chmod(0o755)
        return {'PATH': str(wrappers) + ':' + os.environ['PATH'], 'REAL_GIT': self.git,
                'RACE_REPO': str(self.b), 'RACE_COUNT': str(self.root / 'count'), 'RACE_ALWAYS': '1' if always else '0'}

    def test_race_between_fetch_and_push_retries_successfully(self):
        self.commit(self.a, 'ours.json', 'ours')
        result = self.publish(env=self.race_environment())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.root / 'count').read_text().strip(), '2')
        self.assertEqual(self.remote_content('ours.json'), 'ours')
        self.assertEqual(self.remote_content('race.json'), '0')

    def test_continuous_race_stops_after_four_attempts(self):
        self.commit(self.a, 'ours.json', 'ours')
        result = self.publish(env=self.race_environment(always=True))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.root / 'count').read_text().strip(), '4')
        self.assertEqual(self.remote_content('race.json'), '3')
        self.assertTrue((self.a / '.automation-diagnostics/unpublished.bundle').exists())

    def test_server_policy_rejection_is_not_retried(self):
        hook = self.remote / 'hooks/pre-receive'
        hook.write_text('#!/bin/sh\necho reject >> "' + str(self.root / 'rejects') + '"\nexit 1\n'); hook.chmod(0o755)
        self.commit(self.a, 'ours.json', 'ours')
        result = self.publish(); self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.root / 'rejects').read_text(), 'reject\n')

    def test_feature_branch_does_not_write_main(self):
        before = self.run_git(self.remote, 'rev-parse', 'main')
        self.run_git(self.a, 'switch', '-c', 'fix/test'); self.run_git(self.a, 'push', 'origin', 'fix/test')
        self.commit(self.a, 'ours.json', 'ours')
        result = self.publish('fix/test'); self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.run_git(self.remote, 'rev-parse', 'main'), before)
        self.assertEqual(self.remote_content('ours.json', 'fix/test'), 'ours')

    def test_dirty_tracked_tree_is_rejected(self):
        (self.a / 'shared.json').write_text('uncommitted')
        self.assertNotEqual(self.publish().returncode, 0)
        self.assertEqual(self.remote_content('shared.json'), 'base')


if __name__ == '__main__':
    unittest.main()
