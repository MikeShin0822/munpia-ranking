from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
RANKINGS_PATH = ROOT / "data" / "rankings.json"
NEW_BEST_DIR = ROOT / "data" / "new-best"
OUTPUT_DIR = ROOT / "data" / "weekly-patterns"
TZ = ZoneInfo("Asia/Seoul")

CATEGORY_LABELS = {
    "free_today": "무료",
    "paid_today": "유료",
    "exclusive_today": "선독점",
    "favorites": "선호작",
    "bestseller": "베스트셀러",
}

PATTERNS = [
    {
        "key": "fall_then_rise",
        "name": "추락 후 반전 상승형",
        "formula": "[은퇴·퇴직·해고·좌천·배제] + [새 능력/새 무대] + [재평가·각성·성공]",
        "reason": "먼저 손실과 억울함을 제시한 뒤 더 큰 보상을 예고해 지위 역전 기대를 만든다.",
        "regex": r"(?=.*(?:은퇴|퇴직|해고|좌천|버림받|무고|이혼당|나락|벤치|후보|듣보잡|풋내기|실패))(?=.*(?:각성|재평가|대박|쓸어담|씹어먹|먹여살|상속|천재|최강|탑스타|재벌|국가재앙급|극락|인수))",
    },
    {
        "key": "small_action_big_reaction",
        "name": "작은 행동에 세계가 과잉 반응형",
        "formula": "[평범하거나 작은 행동] + [했더니/뿐인데] + [거대 집단의 집착·극찬·과잉 반응]",
        "reason": "행동과 결과의 규모 차이가 커서 의외성과 즉각적인 보상 기대를 동시에 만든다.",
        "regex": r"(?=.*(?:했더니|했을 뿐인데|뿐인데|고쳐주니|봤더니|보니|읽었더니|한 번에))(?=.*(?:집착|극락|전세계|전 세계|월클|거물|첩보기관|투수|이웃|줄을|고질병|학부모|먹여살))",
    },
    {
        "key": "overseas_local_success",
        "name": "해외 로컬 무대 정복형",
        "formula": "[미국·호주·러시아 등 해외 공간] + [전문 기술/생계 활동] + [대박·인정·집착]",
        "reason": "낯선 해외 공간과 익숙한 직업을 결합해 이국성, 생활 판타지, 사회적 인정을 한 번에 약속한다.",
        "regex": r"(?=.*(?:미국|호주|러시아|아르헨티나|할리우드|포르투갈|스페인|동유럽))(?=.*(?:시골|깡촌|재벌|귀화|대박|집착|잘 고침|목수|영양사|올드카|태권도|왕따|고교|목장|환자))",
    },
    {
        "key": "ability_tower",
        "name": "초월 능력으로 탑 돌파형",
        "formula": "[초월 능력·특수 정보] + [탑/공략] + [빠른 등반·압도적 해결]",
        "reason": "성장 목표와 해결 수단이 제목 안에서 동시에 제시돼 장르와 보상 구조가 즉시 읽힌다.",
        "regex": r"(?=.*탑)(?=.*(?:등반|공략|마법사|능력|경험치|신점|은신|힐러|힐))",
    },
    {
        "key": "misunderstanding_status",
        "name": "착각이 신분을 올리는 형",
        "formula": "[평범한 행동/숨긴 정체] + [착각·오해] + [능력자·후계자·전략가로 격상]",
        "reason": "주인공이 의도하지 않은 평가 상승을 통해 코미디와 지위 상승을 함께 예고한다.",
        "regex": r"(?:착각|오해받|들키면 안됨|과대평가)",
    },
    {
        "key": "too_good_professional",
        "name": "직업을 너무 잘하는 형",
        "formula": "[직업·역할] + [행동] + [너무 잘함/너무 쉬움/압도적 유능함]",
        "reason": "복잡한 설정 설명 없이 주인공의 압도적 숙련도와 사이다 전개를 직접 약속한다.",
        "regex": r"(?:너무 잘|너무 쉽|잘 고침|너무 유능|잘 먹고 산다|마운드를 찢|연예계를 씹어먹|돈을 쓸어담)",
    },
    {
        "key": "grand_power_title",
        "name": "평범한 출발에서 거대 권력자형",
        "formula": "[원치 않거나 평범한 상태] + [되었다] + [독재자·황제·재벌·대공·지도자]",
        "reason": "출발점과 최종 신분의 격차가 커서 권력 획득과 규모 확장의 기대를 만든다.",
        "regex": r"(?:비자발적 종신 독재자|반강제적 제국주의자|황제가|지도자가 되었다|북부대공이 되었다|재벌이 되었다|무역왕|후계 1순위|저승사자가 되었다|집행자가 되었다)",
    },
    {
        "key": "historical_alt_role",
        "name": "역사·국가 배경 역할 전환형",
        "formula": "[실존 시대·국가] + [현대적 능력/낯선 역할] + [역사 개변·생존]",
        "reason": "익숙한 역사적 무대에 현대적 직업과 문제 해결 방식을 넣어 대체역사적 호기심을 자극한다.",
        "regex": r"(?:삼국지|고려|세종|단종|17세기|19세기|1957년|1984년|소비에트|러시아 황제|북한|대영제국|허난설헌)",
    },
    {
        "key": "hidden_space_resource",
        "name": "평범한 공간에 비범한 자원형",
        "formula": "[방구석·옥탑방·창고·땅굴·폐가] + [숨겨진 시설/자원] + [생존·사업·성공]",
        "reason": "일상적이고 좁은 공간 안에 거대한 가능성을 숨겨 발견과 확장 욕구를 만든다.",
        "regex": r"(?=.*(?:방구석|옥탑방|창고|땅굴|아공간|안전지대|폐가|동물원))(?=.*(?:연결|숨김|핵잠수함|사업|만들|운영|힐링|극락|보임))",
    },
    {
        "key": "max_grade_genius",
        "name": "최상급 재능·등급 선공개형",
        "formula": "[평범하거나 저평가된 인물] + [천재·전능·EX/SSS급] + [즉시 성과]",
        "reason": "주인공의 상한선을 제목에서 미리 공개해 성장 속도와 압도적 우위를 빠르게 전달한다.",
        "regex": r"(?:천재|전능|EX급|SSS급|신화급|역대급|국가재앙급|천살성|최강)",
    },
    {
        "key": "relationship_status_jump",
        "name": "관계 한 번에 신분 점프형",
        "formula": "[남편·사위·손녀·아들·후계] + [재벌·회장·권력가] + [관계로 인한 신분 변화]",
        "reason": "사적 관계가 곧 사회적 지위 변화로 이어져 로맨스와 권력 판타지를 함께 암시한다.",
        "regex": r"(?=.*(?:남편|사위|손녀|아들|후계|아빠|회장님|남동생))(?=.*(?:재벌|회장|고백|착각|들키|상속|대공|황제))",
    },
    {
        "key": "expert_new_stage",
        "name": "전문가의 의외 무대 이식형",
        "formula": "[기존 전문직·전투직] + [의외의 업계/공간] + [기존 능력으로 압도]",
        "reason": "서로 멀어 보이는 직업과 무대를 결합해 익숙한 능력이 새 환경에서 어떻게 통할지 궁금하게 만든다.",
        "regex": r"(?=.*(?:의사|신의|무당|매니저|승무원|영양사|목수|감독|작가|공무원|특수요원|탱커|헌터|마법사))(?=.*(?:미국|연예계|탑스타|월드컵|환자|국민연금|저작권료|폐가|계룡산|동물원))",
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", help="YYYY-MM-DD. 생략 시 직전 월요일")
    parser.add_argument("--end", help="YYYY-MM-DD. 생략 시 직전 일요일")
    return parser.parse_args()


def default_range(now: date) -> tuple[date, date]:
    this_monday = now - timedelta(days=now.weekday())
    end = this_monday - timedelta(days=1)
    start = end - timedelta(days=6)
    return start, end


def load_rankings() -> dict:
    return json.loads(RANKINGS_PATH.read_text(encoding="utf-8"))


def flatten(data: dict, start: date, end: date) -> list[dict]:
    entries: list[dict] = []
    for snapshot in data.get("snapshots", []):
        snapshot_date = date.fromisoformat(snapshot["date"])
        if not start <= snapshot_date <= end:
            continue
        for category, ranking in snapshot.get("rankings", {}).items():
            for rank, title in enumerate(ranking.get("titles", []), start=1):
                entries.append({
                    "date": snapshot["date"],
                    "category": category,
                    "categoryLabel": CATEGORY_LABELS.get(category, category),
                    "rank": rank,
                    "title": title.strip(),
                })
    return entries


def matches(pattern: dict, title: str) -> bool:
    return re.search(pattern["regex"], title, flags=re.IGNORECASE) is not None


def trend_label(current: int, previous: int) -> str:
    if previous == 0 and current > 0:
        return "새로 등장"
    diff = current - previous
    if diff >= 4 and current >= max(4, int(previous * 1.35)):
        return "강한 상승"
    if diff >= 1:
        return "상승"
    if diff <= -2:
        return "하락"
    return "유지"


def life_stage(current: int, previous: int, occurrences: int) -> str:
    if previous == 0 and current > 0:
        return "새로 뜨는 패턴"
    if current >= 12 and current > previous:
        return "현재 강세"
    if current >= 10 and abs(current - previous) <= 1 and occurrences >= 30:
        return "과포화 가능성"
    if current < previous - 1:
        return "약화 중"
    return "안정적 반복"


def pattern_metrics(pattern: dict, current_entries: list[dict], previous_entries: list[dict]) -> dict | None:
    current_matches = [entry for entry in current_entries if matches(pattern, entry["title"])]
    previous_matches = [entry for entry in previous_entries if matches(pattern, entry["title"])]
    current_titles = sorted({entry["title"] for entry in current_matches})
    previous_titles = {entry["title"] for entry in previous_matches}
    if len(current_titles) < 2:
        return None

    title_stats: dict[str, dict] = {}
    for title in current_titles:
        occurrences = [entry for entry in current_matches if entry["title"] == title]
        title_stats[title] = {
            "bestRank": min(item["rank"] for item in occurrences),
            "occurrences": len(occurrences),
            "averageRank": sum(item["rank"] for item in occurrences) / len(occurrences),
        }
    representatives = sorted(
        current_titles,
        key=lambda title: (
            title_stats[title]["bestRank"],
            -title_stats[title]["occurrences"],
            title,
        ),
    )[:4]

    categories = Counter(entry["categoryLabel"] for entry in current_matches)
    average_rank = sum(entry["rank"] for entry in current_matches) / len(current_matches)
    best_rank = min(entry["rank"] for entry in current_matches)
    top10_titles = len({entry["title"] for entry in current_matches if entry["rank"] <= 10})
    current_count = len(current_titles)
    previous_count = len(previous_titles)

    return {
        "key": pattern["key"],
        "name": pattern["name"],
        "formula": pattern["formula"],
        "reason": pattern["reason"],
        "uniqueTitleCount": current_count,
        "previousUniqueTitleCount": previous_count,
        "change": current_count - previous_count,
        "trend": trend_label(current_count, previous_count),
        "lifeStage": life_stage(current_count, previous_count, len(current_matches)),
        "occurrenceCount": len(current_matches),
        "sharePercent": 0,
        "averageRank": round(average_rank, 1),
        "bestRank": best_rank,
        "top10TitleCount": top10_titles,
        "top30TitleCount": current_count,
        "categories": dict(categories.most_common()),
        "representativeTitles": representatives,
        "score": round(current_count * 20 + len(current_matches) + top10_titles * 5 + max(0, current_count - previous_count) * 4, 1),
    }


def load_new_best(start: date, end: date) -> dict:
    snapshots: list[dict] = []
    if NEW_BEST_DIR.exists():
        current = start
        while current <= end:
            path = NEW_BEST_DIR / f"{current.isoformat()}.json"
            if path.exists():
                day = json.loads(path.read_text(encoding="utf-8"))
                snapshots.extend(day.get("snapshots", []))
            current += timedelta(days=1)
    if not snapshots:
        return {
            "available": False,
            "note": "해당 기간에는 신규베스트 3시간 수집이 아직 시작되지 않아 초기 성과를 계산하지 않았습니다.",
            "snapshotCount": 0,
        }
    return {
        "available": True,
        "note": f"신규베스트 스냅샷 {len(snapshots)}개를 확인했습니다.",
        "snapshotCount": len(snapshots),
    }


def build_report(start: date, end: date) -> dict:
    data = load_rankings()
    previous_end = start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=6)
    current_entries = flatten(data, start, end)
    previous_entries = flatten(data, previous_start, previous_end)
    unique_titles = {entry["title"] for entry in current_entries}

    patterns = []
    for pattern in PATTERNS:
        item = pattern_metrics(pattern, current_entries, previous_entries)
        if item:
            item["sharePercent"] = round(item["uniqueTitleCount"] / max(1, len(unique_titles)) * 100, 1)
            patterns.append(item)
    patterns.sort(key=lambda item: (-item["score"], item["averageRank"], item["name"]))
    patterns = patterns[:10]

    rising = sorted(patterns, key=lambda item: (-item["change"], -item["uniqueTitleCount"]))
    falling = sorted(patterns, key=lambda item: (item["change"], -item["uniqueTitleCount"]))
    top = patterns[0] if patterns else None
    strongest_rank = min(patterns, key=lambda item: (item["averageRank"], -item["top10TitleCount"])) if patterns else None
    category_totals = Counter(entry["categoryLabel"] for entry in current_entries)
    completed_days = len({entry["date"] for entry in current_entries})
    expected_days = (end - start).days + 1
    missing_days = [
        (start + timedelta(days=offset)).isoformat()
        for offset in range(expected_days)
        if (start + timedelta(days=offset)).isoformat() not in {entry["date"] for entry in current_entries}
    ]

    highlights = []
    if top:
        highlights.append(f"가장 넓게 반복된 구조는 ‘{top['name']}’으로 고유 제목 {top['uniqueTitleCount']}개가 포착됐습니다.")
    if rising and rising[0]["change"] > 0:
        highlights.append(f"전주 대비 가장 많이 늘어난 구조는 ‘{rising[0]['name']}’이며 고유 제목이 {rising[0]['change']:+d}개 변했습니다.")
    if strongest_rank:
        highlights.append(f"상위권 장악력이 가장 높았던 구조는 ‘{strongest_rank['name']}’으로 평균 {strongest_rank['averageRank']}위, 최고 {strongest_rank['bestRank']}위였습니다.")
    if falling and falling[0]["change"] < 0:
        highlights.append(f"상대적으로 약해진 구조는 ‘{falling[0]['name']}’으로 전주보다 {abs(falling[0]['change'])}개 줄었습니다.")
    highlights.append("무료·선호작에서는 추락 뒤 재평가, 집착, 의외의 직업 전환형이 강했고 유료·선독점·베스트셀러에서는 권력자·역사·탑 공략형이 반복됐습니다.")

    new_best = load_new_best(start, end)
    conclusion = (
        f"이번 주 문피아 제목에서는 {top['name']} 구조가 가장 넓게 반복됐고, "
        f"{rising[0]['name']} 패턴이 전주 대비 가장 뚜렷하게 증가했습니다."
        if top and rising else "이번 주 데이터를 바탕으로 주요 제목 문법을 분류했습니다."
    )

    return {
        "schemaVersion": 1,
        "generatedAt": datetime.now(TZ).replace(microsecond=0).isoformat(),
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "previousStartDate": previous_start.isoformat(),
        "previousEndDate": previous_end.isoformat(),
        "title": f"{start.strftime('%m.%d')}–{end.strftime('%m.%d')} 문피아 주간 제목 패턴",
        "headline": top["name"] if top else "제목 패턴 데이터 준비 중",
        "oneLineConclusion": conclusion,
        "methodNote": "동일 제목은 고유 제목 수에서 한 번만 계산하고, 패턴은 서로 겹칠 수 있습니다. 순위 성과는 5개 베스트 목록의 일별 스냅샷을 기준으로 합니다.",
        "dataQuality": {
            "expectedDays": expected_days,
            "collectedDays": completed_days,
            "missingDays": missing_days,
            "complete": not missing_days,
        },
        "summary": {
            "entryCount": len(current_entries),
            "uniqueTitleCount": len(unique_titles),
            "patternCount": len(patterns),
            "categoryOccurrences": dict(category_totals),
        },
        "highlights": highlights[:5],
        "patterns": patterns,
        "risingPatterns": [item["key"] for item in rising if item["change"] > 0][:4],
        "fallingPatterns": [item["key"] for item in falling if item["change"] < 0][:4],
        "watchlist": [item["name"] for item in rising[:3]],
        "newBest": new_best,
    }


def write_report(report: dict) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    key = f"{report['startDate']}_{report['endDate']}"
    report_path = OUTPUT_DIR / f"{key}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUTPUT_DIR / "latest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    index_path = OUTPUT_DIR / "index.json"
    if index_path.exists():
        index = json.loads(index_path.read_text(encoding="utf-8"))
    else:
        index = {"reports": []}
    reports = [item for item in index.get("reports", []) if item.get("key") != key]
    reports.append({
        "key": key,
        "startDate": report["startDate"],
        "endDate": report["endDate"],
        "title": report["title"],
        "generatedAt": report["generatedAt"],
    })
    reports.sort(key=lambda item: item["startDate"])
    index = {
        "updatedAt": report["generatedAt"],
        "latestKey": key,
        "reports": reports,
    }
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    if args.start and args.end:
        start = date.fromisoformat(args.start)
        end = date.fromisoformat(args.end)
    else:
        start, end = default_range(datetime.now(TZ).date())
    if start.weekday() != 0 or end.weekday() != 6 or (end - start).days != 6:
        raise SystemExit("주간 범위는 월요일부터 일요일까지 7일이어야 합니다.")
    report = build_report(start, end)
    write_report(report)
    print(json.dumps({
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "patterns": len(report["patterns"]),
        "uniqueTitles": report["summary"]["uniqueTitleCount"],
        "newBestAvailable": report["newBest"]["available"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
