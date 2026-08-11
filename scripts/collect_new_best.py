from __future__ import annotations

import json
import re
import sys
import urllib.request
from datetime import datetime
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


def clean(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def to_int(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r"-?[\d,]+", value)
    return int(match.group(0).replace(",", "")) if match else None


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


def detect_change(cell) -> tuple[str, str]:
    text = clean(cell.get_text(" ", strip=True))
    class_text = " ".join(cell.get("class", []))
    for child in cell.find_all(True):
        class_text += " " + " ".join(child.get("class", []))
        alt = child.get("alt")
        title = child.get("title")
        if alt:
            class_text += " " + alt
        if title:
            class_text += " " + title
    probe = f"{class_text} {text}".lower()
    if "new" in probe or "신규" in probe:
        return "new", "NEW"
    if any(token in probe for token in ("up", "rise", "상승")):
        return "up", text or "—"
    if any(token in probe for token in ("down", "fall", "하락")):
        return "down", text or "—"
    if any(token in probe for token in ("same", "stay", "유지", "-")) and not re.search(r"\d", text):
        return "same", text or "—"
    return "unknown", text or "—"


def extract_link(container):
    links = container.find_all("a", href=True)
    preferred = []
    fallback = []
    for link in links:
        label = clean(link.get_text(" ", strip=True))
        href = link.get("href", "")
        if not label or label in {"더보기", "보기", "NEW"} or re.fullmatch(r"\d+위?", label):
            continue
        if "/novel/" in href or "menu=novel" in href or "novel" in href:
            preferred.append(link)
        else:
            fallback.append(link)
    pool = preferred or fallback
    if not pool:
        return None
    return max(pool, key=lambda link: len(clean(link.get_text(" ", strip=True))))


def parse_table(soup: BeautifulSoup) -> list[dict]:
    results = []
    for table in soup.find_all("table"):
        header = clean(table.get_text(" ", strip=True))
        if not all(word in header for word in ("순위", "작품", "작가", "조회")):
            continue
        for tr in table.find_all("tr"):
            cells = tr.find_all("td", recursive=False) or tr.find_all("td")
            if len(cells) < 5:
                continue
            rank = to_int(clean(cells[0].get_text(" ", strip=True)))
            if rank is None or not 1 <= rank <= 200:
                continue
            link = extract_link(cells[1]) or extract_link(tr)
            title = clean(link.get_text(" ", strip=True)) if link else clean(cells[1].get_text(" ", strip=True))
            author = clean(cells[2].get_text(" ", strip=True)) if len(cells) > 2 else ""
            genre_text = clean(cells[3].get_text(" ", strip=True)) if len(cells) > 3 else ""
            hours = to_int(clean(cells[4].get_text(" ", strip=True))) if len(cells) > 4 else None
            views = to_int(clean(cells[5].get_text(" ", strip=True))) if len(cells) > 5 else None
            change_type, change = detect_change(cells[6]) if len(cells) > 6 else ("unknown", "—")
            if title and title not in {"작품", "순위"}:
                results.append({
                    "rank": rank,
                    "title": title,
                    "author": author,
                    "genres": [clean(item) for item in re.split(r"[,/]", genre_text) if clean(item)],
                    "hours": hours,
                    "views": views,
                    "changeType": change_type,
                    "change": change,
                    "url": urljoin(BASE_URL, link.get("href")) if link else "",
                })
        if len(results) >= 190:
            break
    return results


def find_feature_container(rank_node):
    node = rank_node
    best = None
    for _ in range(8):
        node = getattr(node, "parent", None)
        if node is None:
            break
        text = clean(node.get_text(" ", strip=True))
        if len(text) > 1400:
            break
        if "조회" in text and extract_link(node):
            best = node
            if any(tag in (node.name or "") for tag in ("li", "article")) or len(text) < 500:
                return node
    return best


def parse_featured(soup: BeautifulSoup, missing_ranks: set[int]) -> list[dict]:
    results = []
    for rank in sorted(missing_ranks):
        matches = []
        for text_node in soup.find_all(string=re.compile(rf"^\s*{rank}\s*위\s*$")):
            container = find_feature_container(text_node)
            if container:
                matches.append(container)
        if not matches:
            continue
        container = min(matches, key=lambda node: len(clean(node.get_text(" ", strip=True))))
        text = clean(container.get_text(" ", strip=True))
        link = extract_link(container)
        if not link:
            continue
        title = clean(link.get_text(" ", strip=True))
        views_match = re.search(r"조회\s*([\d,]+)", text)
        hours_match = re.search(r"(\d+)\s*시간", text)
        # Best-effort metadata for the featured top five. Title/rank/views are the critical fields.
        author = ""
        author_node = container.select_one('[class*="author"], [class*="writer"], [class*="nickname"]')
        if author_node:
            author = clean(author_node.get_text(" ", strip=True))
        genre_nodes = container.select('[class*="genre"] a, [class*="genre"] span, [class*="category"] a')
        genres = []
        for item in genre_nodes:
            label = clean(item.get_text(" ", strip=True))
            if label and label not in genres:
                genres.append(label)
        results.append({
            "rank": rank,
            "title": title,
            "author": author,
            "genres": genres,
            "hours": int(hours_match.group(1)) if hours_match else None,
            "views": int(views_match.group(1).replace(",", "")) if views_match else None,
            "changeType": "unknown",
            "change": "—",
            "url": urljoin(BASE_URL, link.get("href")),
        })
    return results


def aggregate_at(soup: BeautifulSoup, now: datetime) -> str | None:
    text = clean(soup.get_text(" ", strip=True))
    match = re.search(r"(\d{2})월\s*(\d{2})일\s*(\d{2})시\s*집계", text)
    if not match:
        return None
    month, day, hour = map(int, match.groups())
    year = now.year
    candidate = datetime(year, month, day, hour, tzinfo=TZ)
    if candidate - now > __import__("datetime").timedelta(days=2):
        candidate = candidate.replace(year=year - 1)
    return candidate.isoformat()


def cutoffs(rankings: list[dict]) -> dict:
    by_rank = {item["rank"]: item for item in rankings}
    return {
        str(rank): by_rank.get(rank, {}).get("views")
        for rank in (10, 20, 50, 100, 200)
    }


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

    latest_path = DATA_DIR / "latest.json"
    latest_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

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


def main() -> int:
    now = datetime.now(TZ).replace(microsecond=0)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    try:
        html = fetch_html()
    except Exception as exc:
        print(f"Fetch failed: {exc}", file=sys.stderr)
        return 1

    (RAW_DIR / "new-best.html").write_text(html, encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")
    table_items = parse_table(soup)
    by_rank = {item["rank"]: item for item in table_items}
    missing = set(range(1, 201)) - set(by_rank)
    featured = parse_featured(soup, {rank for rank in missing if rank <= 5})
    for item in featured:
        by_rank[item["rank"]] = item

    rankings = [by_rank[rank] for rank in sorted(by_rank) if 1 <= rank <= 200]
    missing = sorted(set(range(1, 201)) - set(by_rank))
    status = "complete" if len(rankings) == 200 and not missing else "partial"
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
        "tableCount": len(table_items),
        "featuredCount": len(featured),
        "totalCount": len(rankings),
        "missingRanks": missing,
        "aggregateAt": snapshot["aggregateAt"],
        "tables": len(soup.find_all("table")),
    }
    (RAW_DIR / "new-best-debug.json").write_text(json.dumps(debug, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(debug, ensure_ascii=False))

    if status != "complete":
        print(f"Expected 200 rankings, got {len(rankings)}. Missing: {missing[:30]}", file=sys.stderr)
        return 2

    write_data(snapshot, now)
    print(f"Saved {len(rankings)} rankings at {snapshot['collectedAt']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
