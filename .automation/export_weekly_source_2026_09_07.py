from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
RANKINGS_PATH = ROOT / "data" / "rankings.json"
NEW_BEST_DIR = ROOT / "data" / "new-best"
OUTPUT = ROOT / "data" / "weekly-patterns" / "_source-2026-09-07_2026-09-13.json"
TZ = ZoneInfo("Asia/Seoul")

START = date(2026, 9, 7)
END = date(2026, 9, 13)
PREV_START = date(2026, 8, 31)
PREV_END = date(2026, 9, 6)

CATEGORY_LABELS = {
    "free_today": "무료",
    "paid_today": "유료",
    "exclusive_today": "선독점",
    "favorites": "선호작",
    "bestseller": "베스트셀러",
}


def daterange(start: date, end: date):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def week_entries(data: dict, start: date, end: date) -> list[dict]:
    entries: list[dict] = []
    for snapshot in data.get("snapshots", []):
        snapshot_date = date.fromisoformat(snapshot["date"])
        if not start <= snapshot_date <= end:
            continue
        for category, ranking in snapshot.get("rankings", {}).items():
            label = CATEGORY_LABELS.get(category, category)
            for rank, raw_title in enumerate(ranking.get("titles", []), start=1):
                title = str(raw_title).strip()
                entries.append({
                    "date": snapshot["date"],
                    "category": category,
                    "categoryLabel": label,
                    "rank": rank,
                    "title": title,
                })
    return entries


def summarize_week(entries: list[dict], start: date, end: date) -> dict:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for entry in entries:
        grouped[entry["title"]].append(entry)

    titles = []
    for title, items in grouped.items():
        category_counts = Counter(item["categoryLabel"] for item in items)
        date_counts = Counter(item["date"] for item in items)
        ranks = [item["rank"] for item in items]
        titles.append({
            "title": title,
            "occurrenceCount": len(items),
            "dayCount": len(date_counts),
            "bestRank": min(ranks),
            "averageRank": round(sum(ranks) / len(ranks), 2),
            "top10": min(ranks) <= 10,
            "categories": dict(category_counts.most_common()),
            "dates": sorted(date_counts),
        })
    titles.sort(key=lambda item: (item["bestRank"], item["averageRank"], -item["occurrenceCount"], item["title"]))

    collected_dates = sorted({entry["date"] for entry in entries})
    expected_dates = [day.isoformat() for day in daterange(start, end)]
    return {
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "entryCount": len(entries),
        "uniqueTitleCount": len(titles),
        "collectedDates": collected_dates,
        "missingDates": [day for day in expected_dates if day not in collected_dates],
        "categoryOccurrences": dict(Counter(entry["categoryLabel"] for entry in entries)),
        "titles": titles,
    }


def normalize_new_best_title(title: str) -> str:
    title = title.strip()
    if title.startswith("공모전 "):
        title = title[4:].strip()
    return title


def summarize_new_best(start: date, end: date) -> dict:
    works: dict[str, dict] = {}
    snapshots = []
    existing_days = []

    for day in daterange(start, end):
        path = NEW_BEST_DIR / f"{day.isoformat()}.json"
        if not path.exists():
            continue
        existing_days.append(day.isoformat())
        payload = load_json(path)
        for snapshot in payload.get("snapshots", []):
            if snapshot.get("status") != "complete":
                continue
            snapshots.append({
                "date": day.isoformat(),
                "aggregateAt": snapshot.get("aggregateAt"),
                "collectedAt": snapshot.get("collectedAt"),
                "count": snapshot.get("count"),
            })
            for item in snapshot.get("rankings", []):
                title = normalize_new_best_title(str(item.get("title", "")))
                if not title:
                    continue
                url = str(item.get("url") or "")
                key = url or title
                rank = int(item.get("rank") or 999)
                views = int(item.get("views") or 0)
                work = works.setdefault(key, {
                    "title": title,
                    "url": url,
                    "author": item.get("author"),
                    "genres": item.get("genres") or [],
                    "bestRank": rank,
                    "bestViews": views,
                    "appearanceCount": 0,
                    "firstSeen": snapshot.get("aggregateAt") or snapshot.get("collectedAt"),
                    "lastSeen": snapshot.get("aggregateAt") or snapshot.get("collectedAt"),
                })
                work["bestRank"] = min(work["bestRank"], rank)
                work["bestViews"] = max(work["bestViews"], views)
                work["appearanceCount"] += 1
                seen = snapshot.get("aggregateAt") or snapshot.get("collectedAt")
                if seen:
                    work["lastSeen"] = seen
                if not work.get("genres") and item.get("genres"):
                    work["genres"] = item.get("genres")

    title_list = []
    for work in works.values():
        work = dict(work)
        work["top20"] = work["bestRank"] <= 20
        work["top50"] = work["bestRank"] <= 50
        work["top100"] = work["bestRank"] <= 100
        title_list.append(work)
    title_list.sort(key=lambda item: (item["bestRank"], -item["bestViews"], item["title"]))

    return {
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "dayCount": len(existing_days),
        "availableDates": existing_days,
        "missingDates": [day.isoformat() for day in daterange(start, end) if day.isoformat() not in existing_days],
        "snapshotCount": len(snapshots),
        "titleCount": len(title_list),
        "top20Count": sum(1 for item in title_list if item["top20"]),
        "top50Count": sum(1 for item in title_list if item["top50"]),
        "top100Count": sum(1 for item in title_list if item["top100"]),
        "snapshots": snapshots,
        "titles": title_list,
    }


def main() -> None:
    rankings = load_json(RANKINGS_PATH)
    current = summarize_week(week_entries(rankings, START, END), START, END)
    previous = summarize_week(week_entries(rankings, PREV_START, PREV_END), PREV_START, PREV_END)
    current_titles = {item["title"] for item in current["titles"]}
    previous_titles = {item["title"] for item in previous["titles"]}

    payload = {
        "generatedAt": datetime.now(TZ).replace(microsecond=0).isoformat(),
        "current": current,
        "previous": previous,
        "comparison": {
            "newTitles": sorted(current_titles - previous_titles),
            "exitedTitles": sorted(previous_titles - current_titles),
            "sharedTitleCount": len(current_titles & previous_titles),
        },
        "newBest": summarize_new_best(START, END),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(OUTPUT.relative_to(ROOT)),
        "currentDays": len(current["collectedDates"]),
        "currentEntries": current["entryCount"],
        "currentTitles": current["uniqueTitleCount"],
        "previousTitles": previous["uniqueTitleCount"],
        "newBestDays": payload["newBest"]["dayCount"],
        "newBestSnapshots": payload["newBest"]["snapshotCount"],
        "newBestTitles": payload["newBest"]["titleCount"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
