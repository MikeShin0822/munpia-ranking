from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
START = date(2026, 8, 31)
END = date(2026, 9, 6)
PREVIOUS_END = START - timedelta(days=1)
PREVIOUS_START = PREVIOUS_END - timedelta(days=6)
TZ = ZoneInfo("Asia/Seoul")
CATEGORY_LABELS = {
    "free_today": "무료",
    "paid_today": "유료",
    "exclusive_today": "선독점",
    "favorites": "선호작",
    "bestseller": "베스트셀러",
}


def expected_dates(start: date, end: date) -> list[str]:
    return [(start + timedelta(days=i)).isoformat() for i in range((end - start).days + 1)]


def collect_entries(rankings: dict, start: date, end: date):
    entries: list[dict] = []
    found_dates: set[str] = set()
    status_by_date: dict[str, dict] = {}

    for snapshot in rankings.get("snapshots", []):
        snapshot_date = date.fromisoformat(snapshot["date"])
        if not start <= snapshot_date <= end:
            continue
        day_key = snapshot["date"]
        found_dates.add(day_key)
        status_by_date[day_key] = {}
        for category, payload in snapshot.get("rankings", {}).items():
            titles = payload.get("titles", [])
            status_by_date[day_key][category] = {
                "status": payload.get("status"),
                "count": len(titles),
            }
            for rank, title in enumerate(titles, start=1):
                entries.append({
                    "date": day_key,
                    "category": category,
                    "categoryLabel": CATEGORY_LABELS.get(category, category),
                    "rank": rank,
                    "title": title.strip(),
                })

    expected = expected_dates(start, end)
    missing = sorted(set(expected) - found_dates)
    complete = (
        not missing
        and all(
            item.get("status") == "complete" and item.get("count") == 30
            for categories in status_by_date.values()
            for item in categories.values()
        )
        and len(status_by_date) == len(expected)
    )
    return entries, {
        "expectedDays": len(expected),
        "collectedDays": len(found_dates),
        "missingDays": missing,
        "statusByDate": status_by_date,
        "complete": complete,
    }


def summarize(entries: list[dict]) -> dict:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for entry in entries:
        grouped[entry["title"]].append(entry)

    titles: list[dict] = []
    for title, items in grouped.items():
        category_counts = Counter(item["categoryLabel"] for item in items)
        category_best: dict[str, int] = {}
        for item in items:
            label = item["categoryLabel"]
            category_best[label] = min(category_best.get(label, 999), item["rank"])
        titles.append({
            "title": title,
            "occurrenceCount": len(items),
            "bestRank": min(item["rank"] for item in items),
            "averageRank": round(sum(item["rank"] for item in items) / len(items), 2),
            "top10OccurrenceCount": sum(1 for item in items if item["rank"] <= 10),
            "dates": sorted({item["date"] for item in items}),
            "categoryOccurrences": dict(category_counts),
            "categoryBestRanks": category_best,
        })
    titles.sort(key=lambda item: (item["bestRank"], -item["occurrenceCount"], item["title"]))
    return {
        "entryCount": len(entries),
        "uniqueTitleCount": len(titles),
        "categoryOccurrences": dict(Counter(item["categoryLabel"] for item in entries)),
        "titles": titles,
    }


def summarize_new_best(start: date, end: date) -> dict:
    grouped: dict[str, list[dict]] = defaultdict(list)
    days: list[str] = []
    snapshot_count = 0
    current = start
    while current <= end:
        path = ROOT / "data" / "new-best" / f"{current.isoformat()}.json"
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            snapshots = payload.get("snapshots", [])
            if snapshots:
                days.append(current.isoformat())
            for snapshot in snapshots:
                snapshot_count += 1
                seen_at = snapshot.get("aggregateAt") or snapshot.get("collectedAt")
                for item in snapshot.get("rankings", []):
                    key = item.get("url") or item.get("title")
                    if not key:
                        continue
                    grouped[key].append({
                        "title": item.get("title", ""),
                        "url": item.get("url", ""),
                        "rank": item.get("rank"),
                        "views": item.get("views"),
                        "seenAt": seen_at,
                    })
        current += timedelta(days=1)

    titles: list[dict] = []
    for items in grouped.values():
        ranks = [item["rank"] for item in items if isinstance(item.get("rank"), int)]
        if not ranks:
            continue
        views = [item["views"] for item in items if isinstance(item.get("views"), int)]
        times = sorted(item["seenAt"] for item in items if item.get("seenAt"))
        titles.append({
            "title": next((item["title"] for item in items if item.get("title")), ""),
            "url": next((item["url"] for item in items if item.get("url")), ""),
            "bestRank": min(ranks),
            "averageRank": round(sum(ranks) / len(ranks), 2),
            "snapshotCount": len(ranks),
            "peakViews": max(views) if views else None,
            "firstSeenAt": times[0] if times else None,
            "lastSeenAt": times[-1] if times else None,
            "reachedTop20": min(ranks) <= 20,
            "reachedTop50": min(ranks) <= 50,
            "reachedTop100": min(ranks) <= 100,
        })
    titles.sort(key=lambda item: (item["bestRank"], -item["snapshotCount"], item["title"]))
    return {
        "available": bool(titles),
        "dayCount": len(days),
        "days": days,
        "snapshotCount": snapshot_count,
        "titleCount": len(titles),
        "titles": titles,
    }


def main() -> int:
    rankings = json.loads((ROOT / "data" / "rankings.json").read_text(encoding="utf-8"))
    current_entries, current_quality = collect_entries(rankings, START, END)
    previous_entries, previous_quality = collect_entries(rankings, PREVIOUS_START, PREVIOUS_END)
    source = {
        "schemaVersion": 1,
        "generatedAt": datetime.now(TZ).replace(microsecond=0).isoformat(),
        "startDate": START.isoformat(),
        "endDate": END.isoformat(),
        "previousStartDate": PREVIOUS_START.isoformat(),
        "previousEndDate": PREVIOUS_END.isoformat(),
        "dataQuality": current_quality,
        "previousDataQuality": previous_quality,
        "current": summarize(current_entries),
        "previous": summarize(previous_entries),
        "newBest": summarize_new_best(START, END),
    }
    if not source["dataQuality"]["complete"]:
        raise SystemExit(f"Current week is incomplete: {source['dataQuality']}")
    if not source["previousDataQuality"]["complete"]:
        raise SystemExit(f"Previous week is incomplete: {source['previousDataQuality']}")

    output = ROOT / "data" / "weekly-patterns" / "_source-2026-08-31_2026-09-06.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(source, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "currentEntries": source["current"]["entryCount"],
        "currentTitles": source["current"]["uniqueTitleCount"],
        "previousTitles": source["previous"]["uniqueTitleCount"],
        "newBestDays": source["newBest"]["dayCount"],
        "newBestSnapshots": source["newBest"]["snapshotCount"],
        "newBestTitles": source["newBest"]["titleCount"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
