from __future__ import annotations

import json
import re
import sys
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

SOURCE_URL = "https://www.munpia.com/best/today?displayType=GRID"
BASE_URL = "https://www.munpia.com"
TZ = ZoneInfo("Asia/Seoul")
ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "free-today"
RAW_DIR = ROOT / "raw"
USER_AGENT = "Mozilla/5.0 (compatible; MunpiaTitleArchive/1.4; +https://github.com/MikeShin0822/munpia-ranking)"


def clean(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def to_int(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r"-?[\d,]+", value)
    return int(match.group(0).replace(",", "")) if match else None


def clean_genre(value: str) -> str:
    return clean(value).lstrip(",/ ")


def fetch_html() -> str:
    request = urllib.request.Request(
        SOURCE_URL,
        headers={
            "User-Agent": USER_AGENT,
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.7",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
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
    genres: list[str] = []
    if container is None:
        return genres
    for node in container.find_all("span"):
        label = clean_genre(node.get_text(" ", strip=True))
        if label and label not in genres:
            genres.append(label)
    return genres


def parse_top_five(soup: BeautifulSoup) -> list[dict]:
    results: list[dict] = []
    cards = soup.select(".novel-top5 a.novel-wrap")
    for rank, card in enumerate(cards[:5], start=1):
        title_node = card.select_one(".novel-title")
        author_node = card.select_one(".novel-author")
        genre_node = card.select_one(".novel-genre")
        change_node = card.select_one(".novel-author-wrap .rank-range")
        hours = None
        views = None
        for meta in card.select(".novel-meta"):
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
            "unavailable": False,
        })
    return results


def parse_rank_list(soup: BeautifulSoup) -> list[dict]:
    results: list[dict] = []
    for row in soup.select("#best-rank-list-display > a"):
        rank_node = row.select_one(".num")
        rank = to_int(clean(rank_node.get_text(" ", strip=True))) if rank_node else None
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
            "unavailable": False,
        })
    return results


def unavailable_row(rank: int) -> dict:
    return {
        "rank": rank,
        "title": "공개 페이지에서 비노출된 작품",
        "author": "",
        "genres": [],
        "hours": None,
        "views": None,
        "changeType": "unknown",
        "change": "—",
        "url": "",
        "unavailable": True,
        "unavailableReason": "로그인·성인 인증 또는 작품 상태로 세부 정보가 공개되지 않았습니다.",
    }


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


def snapshot_identity(snapshot: dict) -> str:
    return snapshot.get("aggregateAt") or snapshot.get("collectedAt", "")


def write_data(snapshot: dict, now: datetime) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    aggregate = snapshot.get("aggregateAt")
    if aggregate:
        date_key = datetime.fromisoformat(aggregate).astimezone(TZ).date().isoformat()
    else:
        date_key = now.date().isoformat()

    day_path = DATA_DIR / f"{date_key}.json"
    if day_path.exists():
        day = json.loads(day_path.read_text(encoding="utf-8"))
    else:
        day = {"date": date_key, "snapshots": []}

    identity = snapshot_identity(snapshot)
    day["snapshots"] = [
        item for item in day.get("snapshots", [])
        if snapshot_identity(item) != identity
    ]
    day["snapshots"].append(snapshot)
    day["snapshots"].sort(key=lambda item: item.get("aggregateAt") or item.get("collectedAt", ""))
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
        "updatedAt": snapshot["collectedAt"],
        "latestDate": date_key,
        "availableDates": sorted(dates),
    })
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    now = datetime.now(TZ).replace(microsecond=0)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    try:
        html = fetch_html()
    except Exception as exc:
        print(f"Fetch failed: {exc}", file=sys.stderr)
        return 1

    (RAW_DIR / "free-today.html").write_text(html, encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")
    top_five = parse_top_five(soup)
    rank_list = parse_rank_list(soup)
    visible_by_rank = {item["rank"]: item for item in [*top_five, *rank_list]}
    unavailable_ranks = sorted(set(range(1, 201)) - set(visible_by_rank))
    rankings = [visible_by_rank.get(rank) or unavailable_row(rank) for rank in range(1, 201)]
    status = "complete" if len(rankings) == 200 else "partial"

    snapshot = {
        "source": SOURCE_URL,
        "collectedAt": now.isoformat(),
        "aggregateAt": aggregate_at(soup, now),
        "status": status,
        "count": len(rankings),
        "visibleCount": len(visible_by_rank),
        "unavailableCount": len(unavailable_ranks),
        "unavailableRanks": unavailable_ranks,
        "missingRanks": [],
        "cutoffs": cutoffs(rankings),
        "rankings": rankings,
    }

    debug = {
        "topFiveCount": len(top_five),
        "rankListCount": len(rank_list),
        "visibleCount": len(visible_by_rank),
        "totalCount": len(rankings),
        "unavailableRanks": unavailable_ranks,
        "aggregateAt": snapshot["aggregateAt"],
    }
    (RAW_DIR / "free-today-debug.json").write_text(
        json.dumps(debug, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(debug, ensure_ascii=False))

    if status != "complete":
        print(f"Expected 200 ranking slots, got {len(rankings)}", file=sys.stderr)
        return 2

    write_data(snapshot, now)
    print(
        f"Saved {len(rankings)} free-today ranking slots "
        f"({len(visible_by_rank)} visible, {len(unavailable_ranks)} unavailable) "
        f"at {snapshot['collectedAt']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
