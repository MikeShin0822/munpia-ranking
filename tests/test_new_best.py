"""Synthetic HTML regression fixtures; never request Munpia or write real data."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import call, patch
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('new_best', ROOT / 'scripts/collect_new_best.py')
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)
NOW = datetime(2026, 10, 20, 23, 19, tzinfo=collector.TZ)


def fixture(missing=(), blank=(), nested=(), duplicate=None, hour=23, label='original'):
    cards = ''.join(f'<a class="novel-wrap" href="/novel/{n}">'
                    f'<span class="novel-title">{label} {n}</span>'
                    '<span class="novel-author">작가</span></a>'
                    for n in range(1, 6) if n not in missing)
    rows = []
    for n in range(6, 201):
        if n in missing:
            continue
        title = '' if n in blank else f'{label} {n}'
        row = (f'<a href="/novel/{n}"><span class="num">{n}</span>'
               f'<span class="title"><span class="title-wrap">{title}</span></span>'
               '<span class="author">작가</span><span class="genre"><span>판타지</span></span>'
               '<span class="view-count">1,234</span><span class="time">12</span></a>')
        rows.append(f'<div>{row}</div>' if n in nested else row)
        if n == duplicate:
            rows.append(row)
    return (f'<span class="page-title__sub">10월 20일 {hour:02}시 집계</span>'
            f'<div class="novel-top5">{cards}</div>'
            f'<div id="best-rank-list-display">{"".join(rows)}</div>')


class NewBestTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.raw = self.root / 'raw'
        self.data = self.root / 'data'
        self.data.mkdir()
        # Existing data must survive failures byte-for-byte, including day/index files.
        for name in ('latest.json', 'index.json', '2026-10-20.json'):
            (self.data / name).write_text('previous-success-' + name)
        self.before = {p.name: p.read_bytes() for p in self.data.iterdir()}

    def run_collector(self, responses, real_write=False):
        with patch.object(collector, 'RAW_DIR', self.raw), \
             patch.object(collector, 'DATA_DIR', self.data), \
             patch.object(collector, 'fetch_html', side_effect=responses) as fetch, \
             patch.object(collector.time, 'sleep') as sleep, \
             patch.object(collector, 'write_data', wraps=collector.write_data if real_write else None) as write, \
             contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            result = collector.main()
        return result, fetch, sleep, write

    def assert_unchanged(self):
        self.assertEqual(self.before, {p.name: p.read_bytes() for p in self.data.iterdir()})

    def test_complete_first_response_no_retry_schema_unchanged(self):
        code, fetch, sleep, write = self.run_collector([fixture()])
        self.assertEqual(code, 0)
        fetch.assert_called_once_with(revalidate=False)
        sleep.assert_not_called()
        snapshot = write.call_args.args[0]
        expected = json.loads((ROOT / 'data/new-best/latest.json').read_text())
        self.assertEqual(set(snapshot), set(expected))
        self.assertEqual(set(snapshot['rankings'][0]), set(expected['rankings'][0]))
        self.assertEqual([r['rank'] for r in snapshot['rankings']], list(range(1, 201)))
        self.assertEqual(snapshot['cutoffs']['200'], 1234)

    def test_each_reported_hole_recovers_on_fresh_response(self):
        for missing in ([92], [183], [103, 115, 151, 156, 191], [90]):
            with self.subTest(missing=missing):
                code, fetch, sleep, write = self.run_collector([fixture(missing), fixture(label='fresh')])
                self.assertEqual(code, 0)
                self.assertEqual(fetch.call_args_list, [call(revalidate=False), call(revalidate=True)])
                sleep.assert_called_once_with(15)
                write.assert_called_once()
                self.assertTrue(all(r['title'].startswith('fresh') for r in write.call_args.args[0]['rankings']))
                history = json.loads((self.raw / 'new-best-debug.json').read_text())['attempts']
                self.assertEqual(history[0]['missingWithoutRankMarker'], missing)
                self.assertEqual(history[0]['missingWithRankMarker'], [])
                self.assertEqual(history[1]['missingRanks'], [])
                self.assertEqual((self.raw / 'new-best-attempt-1.html').read_text(), fixture(missing))

    def test_different_holes_never_merged_and_all_files_preserved(self):
        code, fetch, sleep, write = self.run_collector(
            [fixture([92]), fixture([183]), fixture([103, 115, 151, 156, 191])], real_write=True)
        self.assertEqual(code, 2)
        self.assertEqual(fetch.call_count, 3)
        self.assertEqual(sleep.call_args_list, [call(15), call(45)])
        write.assert_not_called()
        self.assert_unchanged()
        self.assertEqual(len(list(self.raw.glob('new-best-attempt-*.html'))), 3)

    def test_persistent_single_and_multiple_holes_exhaust_budget(self):
        for missing in ([92], [103, 115, 151, 156, 191]):
            with self.subTest(missing=missing):
                code, fetch, _, write = self.run_collector([fixture(missing)] * 3, real_write=True)
                self.assertEqual(code, 2)
                self.assertEqual(fetch.call_count, 3)
                write.assert_not_called()
                self.assert_unchanged()

    def test_parser_rejection_and_nested_marker_differ_from_absent_rows(self):
        for variant in ({'blank': [92]}, {'nested': [92]}):
            with self.subTest(variant=variant):
                snapshot, debug = collector.parse_response(fixture(**variant), NOW)
                self.assertEqual(snapshot['status'], 'partial')
                self.assertEqual(debug['missingWithRankMarker'], [92])
                self.assertEqual(debug['missingWithoutRankMarker'], [])
                code, _, _, write = self.run_collector([fixture(**variant)] * 3, real_write=True)
                self.assertEqual(code, 2)
                write.assert_not_called()
                self.assert_unchanged()

    def test_duplicate_rank_cannot_be_hidden_by_dictionary(self):
        snapshot, debug = collector.parse_response(fixture(duplicate=92), NOW)
        self.assertEqual(snapshot['count'], 200)
        self.assertEqual(snapshot['status'], 'partial')
        self.assertEqual(debug['duplicateRanks'], [92])
        code, _, _, write = self.run_collector([fixture(duplicate=92)] * 3, real_write=True)
        self.assertEqual(code, 2)
        write.assert_not_called()
        self.assert_unchanged()

    def test_final_attempt_uses_its_own_aggregate_and_titles(self):
        code, fetch, _, write = self.run_collector(
            [fixture([92], hour=21), fixture([183], hour=22), fixture(hour=23, label='fresh')])
        self.assertEqual(code, 0)
        self.assertEqual(fetch.call_count, 3)
        snapshot = write.call_args.args[0]
        self.assertIn('T23:00:00', snapshot['aggregateAt'])
        self.assertTrue(all(r['title'].startswith('fresh') for r in snapshot['rankings']))

    def test_transport_failure_preserves_previous_success_and_attempt_evidence(self):
        for responses in ([OSError('network error')], [fixture([92]), OSError('network error')]):
            with self.subTest(attempts=len(responses)):
                code, fetch, _, write = self.run_collector(responses, real_write=True)
                self.assertEqual(code, 1)
                self.assertEqual(fetch.call_count, len(responses))
                write.assert_not_called()
                self.assert_unchanged()
                history = json.loads((self.raw / 'new-best-debug.json').read_text())['attempts']
                self.assertEqual(len(history), len(responses))
                self.assertIn('fetchError', history[-1])

    def test_stale_retry_diagnostics_removed_on_next_invocation(self):
        self.run_collector([fixture([92])] * 3)
        self.run_collector([fixture()])
        self.assertFalse((self.raw / 'new-best-attempt-2.json').exists())
        self.assertEqual(len(json.loads((self.raw / 'new-best-debug.json').read_text())['attempts']), 1)

    def test_retry_request_asks_cache_to_revalidate_and_keeps_timeout(self):
        with patch.object(collector.urllib.request, 'urlopen') as open_url:
            response = open_url.return_value.__enter__.return_value
            response.status = 200
            response.read.return_value = b'html'
            self.assertEqual(collector.fetch_html(revalidate=True), 'html')
            request = open_url.call_args.args[0]
            self.assertEqual(request.get_header('Cache-control'), 'no-cache')
            self.assertEqual(open_url.call_args.kwargs['timeout'], 45)
            self.assertEqual(request.full_url, collector.SOURCE_URL)

    def test_successful_retry_writes_complete_snapshot_to_all_outputs(self):
        for p in self.data.iterdir():
            p.unlink()
        code, _, _, write = self.run_collector([fixture([183]), fixture()], real_write=True)
        self.assertEqual(code, 0)
        write.assert_called_once()
        latest = json.loads((self.data / 'latest.json').read_text())
        self.assertEqual(latest['status'], 'complete')
        self.assertEqual(latest['missingRanks'], [])
        index = json.loads((self.data / 'index.json').read_text())
        day = json.loads((self.data / f"{index['latestDate']}.json").read_text())
        self.assertEqual(day['snapshots'], [latest])


if __name__ == '__main__':
    unittest.main()
