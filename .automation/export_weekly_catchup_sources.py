from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
RANKINGS_PATH = ROOT / "data" / "rankings.json"
NEW_BEST_DIR = ROOT / "data" / "new-best"
OUTPUT_PATH = ROOT / "data" / "weekly-patterns" / "_catchup-source-2026-09-14_2026-10-13.json"
TZ = ZoneInfo("Asia/Seoul")

CATEGORY_LABELS = {
    "free_today": "무료",
    "paid_today": "유료",
    "exclusive_today": "선독점",
    "favorites": "선호작",
    "bestseller": "베스트셀러",
}

PERIODS = [
    {
        "key": "2026-09-14_2026-09-20",
        "start": "2026-09-14",
        "end": "2026-09-20",
        "previousStart": "2026-09-07",
        "previousEnd": "2026-09-13",
        "periodType": "weekly",
    },
    {
        "key": "2026-09-21_2026-09-27",
        "start": "2026-09-21",
        "end": "2026-09-27",
        "previousStart": "2026-09-14",
        "previousEnd": "2026-09-20",
        "periodType": "weekly",
    },
    {
        "key": "2026-09-28_2026-10-04",
        "start": "2026-09-28",
        "end": "2026-10-04",
        "previousStart": "2026-09-21",
        "previousEnd": "2026-09-27",
        "periodType": "weekly",
    },
    {
        "key": "2026-10-05_2026-10-13",
        "start": "2026-10-05",
        "end": "2026-10-13",
        "previousStart": "2026-09-28",
        "previousEnd": "2026-10-04",
        "periodType": "extended_9_day",
    },
]


def dates_between(start: date, end: date):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def title_stats(entries: list[dict]) -> list[dict]:
    grouped: dict[str, dict] = {}
    for entry in entries:
        title = entry["title"].strip()
        item = grouped.setdefault(
            title,
            {
                "title": title,
                "occurrenceCount": 0,
                "rankSum": 0,
                "bestRank": 999,
                "categories": Counter(),
                "dates": set(),
            },
        )
        item["occurrenceCount"] += 1
        item["rankSum"] += entry["rank"]
        item["bestRank"] = min(item["bestRank"], entry["rank"])
        item["categories"][entry["categoryLabel"]] += 1
        item["dates"].add(entry["date"])

    rows = []
    for item in grouped.values():
        rows.append(
            {
                "title": item["title"],
                "occurrenceCount": item["occurrenceCount"],
                "averageRank": round(item["rankSum"] / item["occurrenceCount"], 2),
                "bestRank": item["bestRank"],
                "top10": item["bestRank"] <= 10,
                "categories": dict(item["categories"].most_common()),
                "dates": sorted(item["dates"]),
            }
        )
    rows.sort(key=lambda row: (row["bestRank"], -row["occurrenceCount"], row["title"]))
    return rows


def collect_ranking_entries(rankings: dict, start: date, end: date) -> tuple[list[dict], dict]:
    by_date = {snapshot.get("date"): snapshot for snapshot in rankings.get("snapshots", [])}
    entries: list[dict] = []
    daily_status = []
    missing_days = []

    for day in dates_between(start, end):
        day_key = day.isoformat()
        snapshot = by_date.get(day_key)
        if not snapshot:
            missing_days.append(day_key)
            daily_status.append({"date": day_key, "available": False, "categories": {}})
            continue

        category_status = {}
        for category, label in CATEGORY_LABELS.items():
            ranking = snapshot.get("rankings", {}).get(category, {})
            titles = ranking.get("titles", []) or []
            status = ranking.get("status")
            category_status[label] = {
                "status": status,
                "count": len(titles),
                "error": ranking.get("error"),
            }
            for rank, title in enumerate(titles, start=1):
                entries.append(
                    {
                        "date": day_key,
                        "category": category,
                        "categoryLabel": label,
                        "rank": rank,
                        "title": str(title).strip(),
                    }
                )
        daily_status.append({"date": day_key, "available": True, "categories": category_status})

    expected_days = (end - start).days + 1
    complete_days = sum(
        1
        for row in daily_status
        if row["available"]
        and all(item.get("status") == "complete" and item.get("count") == 30 for item in row["categories"].values())
    )
    return entries, {
        "expectedDays": expected_days,
        "availableDays": expected_days - len(missing_days),
        "completeDays": complete_days,
        "missingDays": missing_days,
        "dailyStatus": daily_status,
    }


def collect_new_best(start: date, end: date) -> dict:
    works: dict[str, dict] = {}
    missing_days = []
    snapshot_count = 0

    for day in dates_between(start, end):
        day_key = day.isoformat()
        path = NEW_BEST_DIR / f"{day_key}.json"
        if not path.exists():
            missing_days.append(day_key)
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        for snapshot in payload.get("snapshots", []):
            if snapshot.get("status") != "complete":
                continue
            snapshot_count += 1
            for row in snapshot.get("rankings", []):
                title = str(row.get("title") or "").strip()
                if not title:
                    continue
                key = str(row.get("url") or title)
                item = works.setdefault(
                    key,
                    {
                        "title": title,
                        "author": row.get("author"),
                        "genres": set(),
                        "bestRank": 999,
                        "rankSum": 0,
                        "rankCount": 0,
                        "maxViews": 0,
                        "firstSeen": snapshot.get("aggregateAt") or snapshot.get("collectedAt"),
                        "lastSeen": snapshot.get("aggregateAt") or snapshot.get("collectedAt"),
                        "url": row.get("url"),
                    },
                )
                item["genres"].update(row.get("genres") or [])
                rank = int(row.get("rank") or 999)
                item["bestRank"] = min(item["bestRank"], rank)
                item["rankSum"] += rank
                item["rankCount"] += 1
                item["maxViews"] = max(item["maxViews"], int(row.get("views") or 0))
                seen = snapshot.get("aggregateAt") or snapshot.get("collectedAt")
                if seen:
                    item["firstSeen"] = min(item["firstSeen"], seen) if item["firstSeen"] else seen
                    item["lastSeen"] = max(item["lastSeen"], seen) if item["lastSeen"] else seen

    rows = []
    for item in works.values():
        rows.append(
            {
                "title": item["title"],
                "author": item["author"],
                "genres": sorted(item["genres"]),
                "bestRank": item["bestRank"],
                "averageRank": round(item["rankSum"] / item["rankCount"], 2),
                "snapshotAppearances": item["rankCount"],
                "maxViews": item["maxViews"],
                "top20": item["bestRank"] <= 20,
                "top50": item["bestRank"] <= 50,
                "top100": item["bestRank"] <= 100,
                "firstSeen": item["firstSeen"],
                "lastSeen": item["lastSeen"],
                "url": item["url"],
            }
        )
    rows.sort(key=lambda row: (row["bestRank"], -row["maxViews"], row["title"]))
    return {
        "expectedDays": (end - start).days + 1,
        "availableDays": (end - start).days + 1 - len(missing_days),
        "missingDays": missing_days,
        "snapshotCount": snapshot_count,
        "titleCount": len(rows),
        "works": rows,
    }


def build_period(rankings: dict, config: dict) -> dict:
    start = date.fromisoformat(config["start"])
    end = date.fromisoformat(config["end"])
    prev_start = date.fromisoformat(config["previousStart"])
    prev_end = date.fromisoformat(config["previousEnd"])

    current_entries, current_quality = collect_ranking_entries(rankings, start, end)
    previous_entries, previous_quality = collect_ranking_entries(rankings, prev_start, prev_end)
    current_titles = title_stats(current_entries)
    previous_titles = title_stats(previous_entries)
    current_set = {row["title"] for row in current_titles}
    previous_set = {row["title"] for row in previous_titles}

    return {
        **config,
        "generatedAt": datetime.now(TZ).replace(microsecond=0).isoformat(),
        "current": {
            "quality": current_quality,
            "entryCount": len(current_entries),
            "uniqueTitleCount": len(current_titles),
            "titles": current_titles,
        },
        "previous": {
            "quality": previous_quality,
            "entryCount": len(previous_entries),
            "uniqueTitleCount": len(previous_titles),
            "titles": previous_titles,
        },
        "newTitles": sorted(current_set - previous_set),
        "exitedTitles": sorted(previous_set - current_set),
        "newBest": collect_new_best(start, end),
    }


def main() -> int:
    rankings = json.loads(RANKINGS_PATH.read_text(encoding="utf-8"))
    payload = {
        "schemaVersion": 1,
        "generatedAt": datetime.now(TZ).replace(microsecond=0).isoformat(),
        "periods": [build_period(rankings, config) for config in PERIODS],
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(OUTPUT_PATH.relative_to(ROOT)),
        "periods": [
            {
                "key": p["key"],
                "completeDays": p["current"]["quality"]["completeDays"],
                "expectedDays": p["current"]["quality"]["expectedDays"],
                "uniqueTitles": p["current"]["uniqueTitleCount"],
                "newBestDays": p["newBest"]["availableDays"],
                "newBestSnapshots": p["newBest"]["snapshotCount"],
            }
            for p in payload["periods"]
        ],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
