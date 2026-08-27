from __future__ import annotations

import json
import math
import statistics
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
NEW_BEST_DIR = ROOT / "data" / "new-best"
FREE_TODAY_DIR = ROOT / "data" / "free-today"
OUT_DIR = ROOT / "tmp" / "upload-time-analysis"


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def percentile(values: list[float], value: float, higher_is_better: bool = True) -> float:
    if not values:
        return 0.5
    if len(values) == 1:
        return 0.5
    if higher_is_better:
        below = sum(v < value for v in values)
    else:
        below = sum(v > value for v in values)
    equal = sum(v == value for v in values)
    return (below + 0.5 * equal) / len(values)


def median(values: list[float | int | None]) -> float | None:
    cleaned = [float(v) for v in values if isinstance(v, (int, float))]
    return round(statistics.median(cleaned), 2) if cleaned else None


def load_dates(directory: Path) -> list[str]:
    index_path = directory / "index.json"
    if not index_path.exists():
        return []
    return json.loads(index_path.read_text(encoding="utf-8")).get("availableDates", [])


def load_snapshots(directory: Path) -> list[dict[str, Any]]:
    snapshots: dict[str, dict[str, Any]] = {}
    for date_key in load_dates(directory):
        path = directory / f"{date_key}.json"
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        for snapshot in payload.get("snapshots", []):
            identity = snapshot.get("aggregateAt") or snapshot.get("collectedAt")
            if identity:
                snapshots[identity] = snapshot
    return sorted(
        snapshots.values(),
        key=lambda item: item.get("aggregateAt") or item.get("collectedAt") or "",
    )


def event_source_key(item: dict[str, Any]) -> str:
    return item.get("url") or f"{item.get('author', '')}|{item.get('title', '')}"


def build_upload_events(snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    observations_by_work: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for snapshot in snapshots:
        aggregate = parse_dt(snapshot.get("aggregateAt"))
        if aggregate is None:
            continue
        for item in snapshot.get("rankings", []):
            hours = item.get("hours")
            if not isinstance(hours, int) or not 0 <= hours <= 30:
                continue
            rank = item.get("rank")
            if not isinstance(rank, int):
                continue
            estimated_upload = aggregate - timedelta(hours=hours)
            observations_by_work[event_source_key(item)].append({
                "estimatedUpload": estimated_upload,
                "aggregateAt": aggregate,
                "rank": rank,
                "views": item.get("views"),
                "title": item.get("title", ""),
                "author": item.get("author", ""),
                "url": item.get("url", ""),
            })

    events: list[dict[str, Any]] = []
    for work_key, observations in observations_by_work.items():
        observations.sort(key=lambda item: item["estimatedUpload"])
        clusters: list[list[dict[str, Any]]] = []
        for observation in observations:
            if not clusters:
                clusters.append([observation])
                continue
            current = clusters[-1]
            center_epoch = statistics.median(item["estimatedUpload"].timestamp() for item in current)
            center = datetime.fromtimestamp(center_epoch, tz=observation["estimatedUpload"].tzinfo)
            if abs((observation["estimatedUpload"] - center).total_seconds()) <= 2.25 * 3600:
                current.append(observation)
            else:
                clusters.append([observation])

        for cluster in clusters:
            center_epoch = statistics.median(item["estimatedUpload"].timestamp() for item in cluster)
            estimated_upload = datetime.fromtimestamp(center_epoch, tz=cluster[0]["estimatedUpload"].tzinfo)
            ordered = sorted(cluster, key=lambda item: item["aggregateAt"])
            best_rank = min(item["rank"] for item in cluster)
            peak_views = max(
                (item["views"] for item in cluster if isinstance(item.get("views"), int)),
                default=None,
            )
            first_top50 = next((item for item in ordered if item["rank"] <= 50), None)
            first_top20 = next((item for item in ordered if item["rank"] <= 20), None)
            events.append({
                "workKey": work_key,
                "title": ordered[-1]["title"],
                "estimatedUploadAt": estimated_upload.isoformat(),
                "uploadHour": estimated_upload.hour,
                "weekday": estimated_upload.weekday(),
                "isWeekend": estimated_upload.weekday() >= 5,
                "observations": len(cluster),
                "firstObservedRank": ordered[0]["rank"],
                "bestRank": best_rank,
                "peakViews": peak_views,
                "reachedTop100": best_rank <= 100,
                "reachedTop50": best_rank <= 50,
                "reachedTop20": best_rank <= 20,
                "reachedTop10": best_rank <= 10,
                "hoursToTop50": round((first_top50["aggregateAt"] - estimated_upload).total_seconds() / 3600, 2) if first_top50 else None,
                "hoursToTop20": round((first_top20["aggregateAt"] - estimated_upload).total_seconds() / 3600, 2) if first_top20 else None,
            })
    return events


def summarise_event_group(events: list[dict[str, Any]]) -> dict[str, Any]:
    count = len(events)
    if not count:
        return {"events": 0}
    return {
        "events": count,
        "top100Rate": round(sum(item["reachedTop100"] for item in events) / count, 4),
        "top50Rate": round(sum(item["reachedTop50"] for item in events) / count, 4),
        "top20Rate": round(sum(item["reachedTop20"] for item in events) / count, 4),
        "top10Rate": round(sum(item["reachedTop10"] for item in events) / count, 4),
        "medianBestRank": median([item["bestRank"] for item in events]),
        "medianFirstRank": median([item["firstObservedRank"] for item in events]),
        "medianPeakViews": median([item["peakViews"] for item in events]),
        "medianHoursToTop50": median([item["hoursToTop50"] for item in events]),
        "medianHoursToTop20": median([item["hoursToTop20"] for item in events]),
    }


def bin_label(start: int) -> str:
    return f"{start:02d}:00–{(start + 2) % 24:02d}:59"


def analyse_upload_bins(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        grouped[(event["uploadHour"] // 3) * 3].append(event)
    rows = []
    for start in range(0, 24, 3):
        summary = summarise_event_group(grouped.get(start, []))
        summary.update({"startHour": start, "label": bin_label(start)})
        rows.append(summary)

    global_top50 = sum(item["reachedTop50"] for item in events) / max(1, len(events))
    global_top20 = sum(item["reachedTop20"] for item in events) / max(1, len(events))
    rank_values = [row["medianBestRank"] for row in rows if row.get("medianBestRank") is not None]
    for row in rows:
        n = row.get("events", 0)
        if not n:
            row["adjustedTop50Rate"] = None
            row["performanceScore"] = None
            continue
        prior_weight = 30
        adjusted50 = (row["top50Rate"] * n + global_top50 * prior_weight) / (n + prior_weight)
        adjusted20 = (row["top20Rate"] * n + global_top20 * prior_weight) / (n + prior_weight)
        rank_score = percentile(rank_values, row["medianBestRank"], higher_is_better=False)
        sample_score = min(1.0, math.log1p(n) / math.log(151))
        row["adjustedTop50Rate"] = round(adjusted50, 4)
        row["performanceScore"] = round(100 * (0.48 * adjusted50 + 0.25 * adjusted20 + 0.17 * rank_score + 0.10 * sample_score), 2)
    return rows


def analyse_free_today(snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for snapshot in snapshots:
        aggregate = parse_dt(snapshot.get("aggregateAt"))
        if aggregate is None:
            continue
        grouped[(aggregate.hour // 3) * 3].append(snapshot)

    rows = []
    for start in range(0, 24, 3):
        snaps = grouped.get(start, [])
        row: dict[str, Any] = {
            "startHour": start,
            "label": bin_label(start),
            "snapshots": len(snaps),
        }
        for rank in (20, 50, 100, 200):
            row[f"medianTop{rank}Cutoff"] = median([
                snapshot.get("cutoffs", {}).get(str(rank)) for snapshot in snaps
            ])
        rows.append(row)

    for rank in (20, 50, 100, 200):
        values = [row[f"medianTop{rank}Cutoff"] for row in rows if row[f"medianTop{rank}Cutoff"] is not None]
        for row in rows:
            value = row[f"medianTop{rank}Cutoff"]
            row[f"top{rank}EasePercentile"] = round(percentile(values, value, higher_is_better=False), 4) if value is not None else None
    for row in rows:
        ease_values = [row.get(f"top{rank}EasePercentile") for rank in (20, 50, 100, 200)]
        ease_values = [value for value in ease_values if value is not None]
        row["competitionEaseScore"] = round(100 * statistics.mean(ease_values), 2) if ease_values else None
    return rows


def combine(upload_bins: list[dict[str, Any]], cutoff_bins: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cutoff_map = {row["startHour"]: row for row in cutoff_bins}
    combined = []
    for upload in upload_bins:
        cutoff = cutoff_map.get(upload["startHour"], {})
        performance = upload.get("performanceScore")
        ease = cutoff.get("competitionEaseScore")
        score = None
        if performance is not None and ease is not None:
            score = round(0.72 * performance + 0.28 * ease, 2)
        row = {**upload, **{key: value for key, value in cutoff.items() if key not in {"startHour", "label"}}}
        row["combinedScore"] = score
        combined.append(row)
    combined.sort(key=lambda row: (row.get("combinedScore") is None, -(row.get("combinedScore") or -1)))
    return combined


def weekday_summary(events: list[dict[str, Any]]) -> dict[str, Any]:
    weekday = [item for item in events if not item["isWeekend"]]
    weekend = [item for item in events if item["isWeekend"]]
    return {
        "weekday": summarise_event_group(weekday),
        "weekend": summarise_event_group(weekend),
    }


def format_pct(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.1f}%"


def format_num(value: float | None, digits: int = 0) -> str:
    if value is None:
        return "—"
    return f"{value:,.{digits}f}"


def write_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# 문피아 업로드 시간대 탐색 보고서",
        "",
        f"- 신규베스트 데이터: {report['coverage']['newBestStart']}~{report['coverage']['newBestEnd']} / 스냅샷 {report['coverage']['newBestSnapshots']}개",
        f"- 무료 투데이 데이터: {report['coverage']['freeTodayStart']}~{report['coverage']['freeTodayEnd']} / 스냅샷 {report['coverage']['freeTodaySnapshots']}개",
        f"- 추정 업로드 이벤트: {report['coverage']['estimatedUploadEvents']}개",
        "- 주의: 신규베스트 200위 안에 들어온 작품만 관측되므로 전체 업로드의 진입 확률이 아니라, 순위권 진입작 내부의 상대 성과입니다.",
        "- `hours`가 정수라 추정 업로드 시각에는 약 ±1시간 오차가 있을 수 있어 3시간 구간으로 묶었습니다.",
        "",
        "## 종합 추천 구간",
        "",
        "|순위|업로드 추정 구간|표본|Top 50|Top 20|중앙 최고순위|경쟁 완화 점수|종합 점수|",
        "|---:|---|---:|---:|---:|---:|---:|---:|",
    ]
    for index, row in enumerate(report["recommendedWindows"], start=1):
        lines.append(
            f"|{index}|{row['label']}|{row['events']}|{format_pct(row.get('top50Rate'))}|{format_pct(row.get('top20Rate'))}|{format_num(row.get('medianBestRank'), 1)}|{format_num(row.get('competitionEaseScore'), 1)}|{format_num(row.get('combinedScore'), 1)}|"
        )
    lines.extend([
        "",
        "## 전체 3시간 구간",
        "",
        "|구간|표본|Top 100|Top 50|Top 20|중앙 최고순위|Top 50 컷|Top 100 컷|종합 점수|",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for row in report["combinedBinsByTime"]:
        lines.append(
            f"|{row['label']}|{row.get('events', 0)}|{format_pct(row.get('top100Rate'))}|{format_pct(row.get('top50Rate'))}|{format_pct(row.get('top20Rate'))}|{format_num(row.get('medianBestRank'), 1)}|{format_num(row.get('medianTop50Cutoff'))}|{format_num(row.get('medianTop100Cutoff'))}|{format_num(row.get('combinedScore'), 1)}|"
        )
    lines.extend([
        "",
        "## 평일·주말 비교",
        "",
        f"- 평일: 이벤트 {report['weekdayWeekend']['weekday'].get('events', 0)}개, Top 50 {format_pct(report['weekdayWeekend']['weekday'].get('top50Rate'))}, 중앙 최고순위 {format_num(report['weekdayWeekend']['weekday'].get('medianBestRank'), 1)}",
        f"- 주말: 이벤트 {report['weekdayWeekend']['weekend'].get('events', 0)}개, Top 50 {format_pct(report['weekdayWeekend']['weekend'].get('top50Rate'))}, 중앙 최고순위 {format_num(report['weekdayWeekend']['weekend'].get('medianBestRank'), 1)}",
    ])
    return "\n".join(lines) + "\n"


def main() -> int:
    new_snapshots = load_snapshots(NEW_BEST_DIR)
    free_snapshots = load_snapshots(FREE_TODAY_DIR)
    events = build_upload_events(new_snapshots)
    upload_bins = analyse_upload_bins(events)
    cutoff_bins = analyse_free_today(free_snapshots)
    combined = combine(upload_bins, cutoff_bins)
    recommended = [row for row in combined if row.get("events", 0) >= 40 and row.get("combinedScore") is not None][:3]
    if len(recommended) < 3:
        recommended = [row for row in combined if row.get("combinedScore") is not None][:3]

    new_dates = load_dates(NEW_BEST_DIR)
    free_dates = load_dates(FREE_TODAY_DIR)
    report = {
        "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "coverage": {
            "newBestStart": new_dates[0] if new_dates else None,
            "newBestEnd": new_dates[-1] if new_dates else None,
            "newBestSnapshots": len(new_snapshots),
            "freeTodayStart": free_dates[0] if free_dates else None,
            "freeTodayEnd": free_dates[-1] if free_dates else None,
            "freeTodaySnapshots": len(free_snapshots),
            "estimatedUploadEvents": len(events),
        },
        "limitations": [
            "신규베스트 200위에 들어온 작품만 관측한 조건부 분석입니다.",
            "문피아의 경과시간이 정수이므로 추정 업로드 시각에는 약 ±1시간 오차가 있습니다.",
            "제목·작품력·기존 선호작 수·연재 요일 등 교란 변수를 통제하지 못했으므로 인과관계가 아니라 방향성입니다.",
        ],
        "recommendedWindows": recommended,
        "combinedBinsByScore": combined,
        "combinedBinsByTime": sorted(combined, key=lambda row: row["startHour"]),
        "weekdayWeekend": weekday_summary(events),
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "upload-time-analysis.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT_DIR / "upload-time-analysis.md").write_text(write_markdown(report), encoding="utf-8")
    print(json.dumps(report["coverage"], ensure_ascii=False))
    for row in recommended:
        print(row["label"], row.get("combinedScore"), row.get("events"), row.get("top50Rate"), row.get("medianBestRank"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
