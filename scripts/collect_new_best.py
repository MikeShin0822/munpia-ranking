from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

SOURCE_URL = "https://www.munpia.com/best/new.novel.today?displayType=LIST"
BASE_URL = "https://www.munpia.com"
TZ = ZoneInfo("Asia/Seoul")
ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "new-best"
RAW_DIR = ROOT / "raw"
USER_AGENT = "Mozilla/5.0 (compatible; MunpiaTitleArchive/1.3; +https://github.com/MikeShin0822/munpia-ranking)"
RETRY_DELAYS = (15, 45)  # Three requests maximum; no retries after a complete response.


def clean(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def to_int(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r"-?[\d,]+", value)
    return int(match.group(0).replace(",", "")) if match else None


def clean_genre(value: str) -> str:
    return clean(value).lstrip(",/ ")


def fetch_html(*, revalidate: bool = False) -> str:
    request = urllib.request.Request(
        SOURCE_URL,
        headers={
            "User-Agent": USER_AGENT,
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.7",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    if revalidate:
        request.add_header("Cache-Control", "no-cache")
        request.add_header("Pragma", "no-cache")
    with urllib.request.urlopen(request, timeout=45) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status}")
        return response.read().decode("utf-8", errors="replace")


def detect_change(node) -> tuple[str, str]:
    if node is None:
        return "unknown", "—"
    text = clean(node.get_text(" ", strip=True))
    classes = " ".join(node.get("class", [])).lower()
    if "rank-new" in classes or "new" in classes or text.upper() == "NEW":
        return "new", "NEW"
    if "rank-up" in classes:
        return "up", text or "—"
    if "rank-down" in classes:
        return "down", text or "—"
    if "rank-same" in classes:
        return "same", text or "—"
    return "unknown", text or "—"


def genre_list(container) -> list[str]:
    genres = []
    if container is None:
        return genres
    for node in container.find_all("span"):
        label = clean_genre(node.get_text(" ", strip=True))
        if label and label not in genres:
            genres.append(label)
    return genres


def parse_top_five(soup: BeautifulSoup) -> list[dict]:
    results = []
    cards = soup.select(".novel-top5 a.novel-wrap")
    for rank, card in enumerate(cards[:5], start=1):
        title_node = card.select_one(".novel-title")
        author_node = card.select_one(".novel-author")
        genre_node = card.select_one(".novel-genre")
        change_node = card.select_one(".novel-author-wrap .rank-range")
        meta_nodes = card.select(".novel-meta")
        hours = None
        views = None
        for meta in meta_nodes:
            label = clean(meta.get_text(" ", strip=True))
            if label.startswith("시간"):
                hours = to_int(label)
            elif label.startswith("조회"):
                views = to_int(label)
        change_type, change = detect_change(change_node)
        title = clean(title_node.get_text(" ", strip=True)) if title_node else ""
        if not title:
            continue
        results.append({
            "rank": rank,
            "title": title,
            "author": clean(author_node.get_text(" ", strip=True)) if author_node else "",
            "genres": genre_list(genre_node),
            "hours": hours,
            "views": views,
            "changeType": change_type,
            "change": change,
            "url": urljoin(BASE_URL, card.get("href", "")),
        })
    return results


def parse_rank_list(soup: BeautifulSoup) -> list[dict]:
    results = []
    for row in soup.select("#best-rank-list-display > a"):
        rank = to_int(clean(row.select_one(".num").get_text(" ", strip=True))) if row.select_one(".num") else None
        if rank is None or not 1 <= rank <= 200:
            continue
        title_node = row.select_one(".title .title-wrap") or row.select_one(".title")
        author_node = row.select_one(".author")
        genre_node = row.select_one(".genre")
        time_node = row.select_one(".time")
        views_node = row.select_one(".view-count")
        change_node = row.select_one(".rank-range")
        title = clean(title_node.get_text(" ", strip=True)) if title_node else ""
        if not title:
            continue
        change_type, change = detect_change(change_node)
        results.append({
            "rank": rank,
            "title": title,
            "author": clean(author_node.get_text(" ", strip=True)) if author_node else "",
            "genres": genre_list(genre_node),
            "hours": to_int(clean(time_node.get_text(" ", strip=True))) if time_node else None,
            "views": to_int(clean(views_node.get_text(" ", strip=True))) if views_node else None,
            "changeType": change_type,
            "change": change,
            "url": urljoin(BASE_URL, row.get("href", "")),
        })
    return results


def aggregate_at(soup: BeautifulSoup, now: datetime) -> str | None:
    label = soup.select_one(".page-title__sub")
    text = clean(label.get_text(" ", strip=True)) if label else clean(soup.get_text(" ", strip=True))
    match = re.search(r"(\d{2})월\s*(\d{2})일\s*(\d{2})시\s*집계", text)
    if not match:
        return None
    month, day, hour = map(int, match.groups())
    candidate = datetime(now.year, month, day, hour, tzinfo=TZ)
    if candidate - now > timedelta(days=2):
        candidate = candidate.replace(year=now.year - 1)
    return candidate.isoformat()


def cutoffs(rankings: list[dict]) -> dict:
    by_rank = {item["rank"]: item for item in rankings}
    return {str(rank): by_rank.get(rank, {}).get("views") for rank in (10, 20, 50, 100, 200)}


def write_data(snapshot: dict, now: datetime) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    date_key = now.date().isoformat()
    day_path = DATA_DIR / f"{date_key}.json"
    if day_path.exists():
        day = json.loads(day_path.read_text(encoding="utf-8"))
    else:
        day = {"date": date_key, "snapshots": []}

    collected_at = snapshot["collectedAt"]
    day["snapshots"] = [item for item in day.get("snapshots", []) if item.get("collectedAt") != collected_at]
    day["snapshots"].append(snapshot)
    day["snapshots"].sort(key=lambda item: item.get("collectedAt", ""))
    day_path.write_text(json.dumps(day, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    (DATA_DIR / "latest.json").write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    index_path = DATA_DIR / "index.json"
    if index_path.exists():
        index = json.loads(index_path.read_text(encoding="utf-8"))
    else:
        index = {"availableDates": []}
    dates = set(index.get("availableDates", []))
    dates.add(date_key)
    index.update({
        "updatedAt": collected_at,
        "latestDate": date_key,
        "availableDates": sorted(dates),
    })
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_response(html: str, now: datetime) -> tuple[dict, dict]:
    soup = BeautifulSoup(html, "html.parser")
    top_five = parse_top_five(soup)
    rank_list = parse_rank_list(soup)
    by_rank = {item["rank"]: item for item in [*top_five, *rank_list]}
    rankings = [by_rank[rank] for rank in sorted(by_rank) if 1 <= rank <= 200]
    missing = sorted(set(range(1, 201)) - set(by_rank))
    # Reject conflicting rows instead of silently hiding them in the rank map.
    # Top-five cards and list rows may legitimately overlap, so check each separately.
    duplicates = sorted({item["rank"] for group in (top_five, rank_list)
                         for item in group
                         if sum(row["rank"] == item["rank"] for row in group) > 1})
    status = "complete" if len(rankings) == 200 and not missing and not duplicates else "partial"

    snapshot = {
        "source": SOURCE_URL,
        "collectedAt": now.isoformat(),
        "aggregateAt": aggregate_at(soup, now),
        "status": status,
        "count": len(rankings),
        "missingRanks": missing,
        "cutoffs": cutoffs(rankings),
        "rankings": rankings,
    }

    debug = {
        "topFiveCount": len(top_five),
        "rankListCount": len(rank_list),
        "totalCount": len(rankings),
        "missingRanks": missing,
        "aggregateAt": snapshot["aggregateAt"],
        "duplicateRanks": duplicates,
    }
    # Broader than the production direct-child selector: retain evidence of rows
    # that exist but were rejected (e.g. empty title) or nested under a wrapper.
    # Marker absence is a diagnostic hint, not proof of an upstream server defect.
    markers = {to_int(node.get_text(" ", strip=True))
               for node in soup.select("#best-rank-list-display .num")}
    debug.update({
        "topFiveCardCount": len(soup.select(".novel-top5 a.novel-wrap")),
        "rankListRowCount": len(soup.select("#best-rank-list-display > a")),
        "rankMarkers": sorted(rank for rank in markers if rank is not None and 1 <= rank <= 200),
        "missingWithRankMarker": [rank for rank in missing if rank in markers],
        "missingWithoutRankMarker": [rank for rank in missing if rank not in markers],
    })
    return snapshot, debug


def main() -> int:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    # Only remove diagnostics owned by this collector, including stale retries.
    for path in RAW_DIR.glob("new-best-attempt-*"):
        if path.is_file():
            path.unlink()
    for name in ("new-best.html", "new-best-debug.json"):
        (RAW_DIR / name).unlink(missing_ok=True)
    attempts = []
    for attempt in range(1, len(RETRY_DELAYS) + 2):
        if attempt > 1:
            time.sleep(RETRY_DELAYS[attempt - 2])
        now = datetime.now(TZ).replace(microsecond=0)
        try:
            html = fetch_html(revalidate=attempt > 1)
        except Exception as exc:
            # Keep the existing fail-fast policy for transport errors. This
            # retry budget specifically addresses successfully fetched partial HTML.
            debug = {"attempt": attempt, "collectedAt": now.isoformat(),
                     "fetchError": str(exc)}
            attempts.append(debug)
            save_debug(debug, attempts, attempt)
            print(f"Fetch failed: {exc}", file=sys.stderr)
            return 1

        (RAW_DIR / "new-best.html").write_text(html, encoding="utf-8")
        (RAW_DIR / f"new-best-attempt-{attempt}.html").write_text(html, encoding="utf-8")
        # Never fill holes from a previous attempt or the last successful snapshot.
        snapshot, debug = parse_response(html, now)
        debug.update({"attempt": attempt, "collectedAt": now.isoformat()})
        attempts.append(debug)
        save_debug(debug, attempts, attempt)
        print(json.dumps(debug, ensure_ascii=False), flush=True)
        if snapshot["status"] == "complete":
            write_data(snapshot, now)
            print(f"Saved {len(snapshot['rankings'])} rankings at {snapshot['collectedAt']}")
            return 0
        print(f"Expected 200 unique rankings, got {snapshot['count']}. "
              f"Missing: {snapshot['missingRanks']}; duplicates: {debug['duplicateRanks']}",
              file=sys.stderr)
        if attempt <= len(RETRY_DELAYS):
            print(f"Retrying full response in {RETRY_DELAYS[attempt - 1]} seconds", flush=True)
    return 2


def save_debug(debug: dict, attempts: list[dict], attempt: int) -> None:
    (RAW_DIR / f"new-best-attempt-{attempt}.json").write_text(
        json.dumps(debug, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (RAW_DIR / "new-best-debug.json").write_text(
        json.dumps({**debug, "attempts": attempts}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
