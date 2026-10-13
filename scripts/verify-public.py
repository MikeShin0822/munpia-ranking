#!/usr/bin/env python3
"""Bounded public checks; repository data is the diagnostic source of truth.

Does not collect data. Reports preserve the public-verification.json contract;
per-attempt failures and classification live only in diagnostic artifacts.
"""
import argparse
import concurrent.futures
import http.client
import json
import subprocess
import time
import urllib.error
import urllib.request
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

SITE = 'https://mikeshin0822.github.io/munpia-ranking/'
RAW = 'https://raw.githubusercontent.com/MikeShin0822/munpia-ranking/main/'
DATA = {'ranking': 'data/rankings.json'}
for prefix, folder in [('newBest', 'new-best'), ('freeToday', 'free-today'),
                       ('weeklyPattern', 'weekly-patterns')]:
    DATA[prefix + 'Index'] = f'data/{folder}/index.json'
    DATA[prefix + 'Latest'] = f'data/{folder}/latest.json'
URLS = {'site': SITE, **{k: RAW + v for k, v in DATA.items()}}
for prefix, folder in [('newBest', 'new-best'), ('freeToday', 'free-today'),
                       ('weeklyPattern', 'weekly-patterns')]:
    for ext in ['js', 'css']:
        URLS[prefix + ext.title()] = SITE + folder + '.' + ext
DATA_CHECKS = ['rankingDataReadable', 'newBestDataComplete',
               'freeTodayDataComplete', 'weeklyPatternDataComplete']


def parse(resource):
    if resource['status'] != 200:
        raise ValueError(f"HTTP {resource['status']}")
    return json.loads(resource['text'])


def check_data(resources, expected):
    checks, reasons = {}, {}
    def check(key, validate):
        try:
            validate()
            checks[key] = True
        except (ValueError, KeyError, TypeError, AssertionError, IndexError, AttributeError) as exc:
            checks[key] = False
            reasons[key] = str(exc) or 'schema invariant failed'
    def rankings():
        doc = parse(resources['ranking'])
        assert isinstance(doc['snapshots'], list) and doc['snapshots'], 'snapshots missing or empty'
    def daily(prefix):
        index, latest = (parse(resources[prefix + suffix]) for suffix in ['Index', 'Latest'])
        assert latest['status'] == 'complete', 'status is not complete'
        assert latest['count'] == 200, 'count must be 200'
        assert len(latest['rankings']) == 200, 'rankings length must be 200'
        assert [item['rank'] for item in latest['rankings']] == list(range(1, 201)), 'ranks must be 1..200'
        assert latest.get('missingRanks', []) == [], 'missing ranks'
        assert index['latestDate'] == expected, f"index date {index['latestDate']} != {expected}"
        collected = datetime.fromisoformat(latest['collectedAt'])
        assert collected.tzinfo is not None, 'collectedAt needs a timezone'
        assert collected.astimezone(ZoneInfo('Asia/Seoul')).date().isoformat() == expected, 'latest date mismatch'
        assert datetime.fromisoformat(index['updatedAt']) == collected, 'index/latest generation mismatch'
        if prefix == 'freeToday':
            visible, unavailable = latest['visibleCount'], latest['unavailableCount']
            assert isinstance(visible, int) and isinstance(unavailable, int), 'invalid visibility counts'
            assert 180 <= visible <= 200 and 0 <= unavailable <= 20, 'visibility outside collector limits'
            assert visible + unavailable == 200, 'visibility counts do not total 200'
            assert set(latest['cutoffs']) == {'10', '20', '50', '100', '200'}, 'cutoffs incomplete'
    def weekly():
        index, latest = (parse(resources['weeklyPattern' + suffix]) for suffix in ['Index', 'Latest'])
        start, end = date.fromisoformat(latest['startDate']), date.fromisoformat(latest['endDate'])
        quality = latest['dataQuality']
        key = f"{latest['startDate']}_{latest['endDate']}"
        assert index['latestKey'] == key, 'weekly index/latest mismatch'
        assert any(item['key'] == key for item in index.get('reports', [])), 'weekly report missing'
        assert len(index.get('reports', [])) >= 2, 'weekly history missing'
        assert quality['complete'] is True and quality.get('missingDays', []) == [], 'weekly incomplete'
        assert quality['expectedDays'] == (end - start).days + 1 == quality['collectedDays'], 'weekly day counts mismatch'
        assert start.weekday() == 0, 'weekly start is not Monday'
        period = latest.get('periodType', 'weekly')
        assert (period == 'weekly' and quality['expectedDays'] == 7 and end.weekday() == 6) or (period == 'extended_9_day' and quality['expectedDays'] == 9), 'unsupported weekly period'
        assert latest.get('analysisMethod') == 'llm_semantic_with_quantitative_support', 'weekly analysis method mismatch'
        assert len(latest.get('patterns', [])) >= 8, 'weekly patterns incomplete'
    check('rankingDataReadable', rankings)
    check('newBestDataComplete', lambda: daily('newBest'))
    check('freeTodayDataComplete', lambda: daily('freeToday'))
    check('weeklyPatternDataComplete', weekly)
    return checks, reasons


def evaluate(resources, expected):
    report = {'checkedAt': datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),
              'expectedDate': expected, 'siteUrl': SITE, 'siteStatus': resources['site']['status'],
              'siteContentOk': '문피아 제목 레이더' in resources['site']['text'],
              'dataUrl': RAW + DATA['ranking'], 'dataStatus': resources['ranking']['status']}
    checks, reasons = check_data(resources, expected)
    report.update(checks)
    html = resources['site']['text']
    report['newBestTabPublished'] = all(s in html for s in ['data-view="new-best"', 'NEW BEST RADAR'])
    report['newBestMoversPublished'] = all(s in html for s in ['id="new-best-rising"', 'id="new-best-falling"', '급상승 · 급하락'])
    report['newBestCutoffChartPublished'] = all(s in html for s in ['id="cutoff-chart"', '조회수 컷 일중 변화'])
    for prefix, folder, label in [('newBest', 'new-best', ''), ('freeToday', 'free-today', 'FREE TODAY RADAR'),
                                   ('weeklyPattern', 'weekly-patterns', 'WEEKLY TITLE GRAMMAR')]:
        for suffix in ['Js', 'Css', 'Index', 'Latest']:
            report[prefix + suffix + 'Status'] = resources[prefix + suffix]['status']
        js = resources[prefix + 'Js']['text']
        syntax = subprocess.run(['node', '--input-type=module', '--check'], input=js, text=True,
                                capture_output=True, timeout=20)
        report[prefix + 'JsSyntaxOk'] = syntax.returncode == 0
        if prefix != 'newBest':
            report[prefix + 'TabPublished'] = all(s in js for s in [f"button.dataset.view = '{folder}'", label, folder + '-view'])
    failures = [key for key, value in report.items()
                if (isinstance(value, bool) and not value) or (key.endswith('Status') and value != 200)]
    return report, failures, reasons


def fetch(url, token):
    request = urllib.request.Request(url + ('&' if '?' in url else '?') + 'verify=' + token,
                                     headers={'Cache-Control': 'no-cache', 'User-Agent': 'Munpia-public-verifier'})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return {'status': response.status, 'text': response.read().decode('utf-8')}
    except urllib.error.HTTPError as exc:
        return {'status': exc.code, 'text': '', 'error': str(exc)}
    except (OSError, UnicodeError, http.client.HTTPException) as exc:
        return {'status': 0, 'text': '', 'error': str(exc)}


def fetch_public(attempt):
    token = f'{time.time_ns()}-{attempt}'
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        values = list(pool.map(lambda url: fetch(url, token), URLS.values()))
    return dict(zip(URLS, values))


def source_data():
    # Pin every source file to one freshly fetched main commit, never mix versions.
    subprocess.run(['git', 'fetch', '--no-tags', 'origin',
                    'refs/heads/main:refs/remotes/origin/main'], check=True, capture_output=True, timeout=45)
    sha = subprocess.check_output(['git', 'rev-parse', 'refs/remotes/origin/main'], text=True).strip()
    resources = {}
    for key, path in DATA.items():
        result = subprocess.run(['git', 'show', f'{sha}:{path}'], capture_output=True, text=True, timeout=20)
        resources[key] = {'status': 200 if result.returncode == 0 else 404, 'text': result.stdout}
    return sha, resources


def verify(expected, public=fetch_public, source=source_data, sleep=time.sleep,
           diagnostic_dir=Path('.automation-diagnostics'), output=Path('data/public-verification.json'),
           delays=(15, 30, 60, 60)):
    diagnostic_dir.mkdir(parents=True, exist_ok=True)
    history = []
    for attempt in range(1, len(delays) + 2):
        resources = public(attempt)
        report, failures, reasons = evaluate(resources, expected)
        record = {'attempt': attempt, 'checkedAt': report['checkedAt'], 'failures': failures,
                  'reasons': reasons, 'httpErrors': {k: v['error'] for k, v in resources.items() if 'error' in v}}
        if not failures:
            record['classification'] = 'passed' if attempt == 1 else 'recovered_after_retry'
        else:
            record['classification'] = 'publication_or_transport_failure'
            bad_data = set(failures) & set(DATA_CHECKS)
            if bad_data:
                try:
                    sha, canonical = source()
                    source_checks, source_reasons = check_data(canonical, expected)
                    record.update(sourceCommit=sha, sourceReasons=source_reasons)
                    if any(not source_checks[key] for key in bad_data):
                        record['classification'] = 'source_data_incomplete'
                    else:
                        record['classification'] = 'propagation_delay_suspected'
                except (subprocess.SubprocessError, OSError) as exc:
                    record['classification'] = 'source_unavailable'
                    record['sourceError'] = str(exc)
        history.append(record)
        (diagnostic_dir / f'public-attempt-{attempt}.json').write_text(
            json.dumps({'report': report, **record}, ensure_ascii=False, indent=2) + '\n')
        (diagnostic_dir / 'public-attempts.json').write_text(json.dumps(history, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps(record, ensure_ascii=False), flush=True)
        if not failures:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
            return True
        # Incomplete canonical data is not made valid by waiting for a CDN.
        # A mismatch is only *suspected* delay; exhausted retries remain failures.
        if record['classification'] == 'source_data_incomplete' or attempt > len(delays):
            return False
        sleep(delays[attempt - 1])
    return False


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--expected-date', default=datetime.now(ZoneInfo('Asia/Seoul')).date().isoformat())
    args = parser.parse_args()
    date.fromisoformat(args.expected_date)
    raise SystemExit(0 if verify(args.expected_date) else 1)
