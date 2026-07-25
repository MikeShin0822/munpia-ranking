#!/usr/bin/env python3

import datetime as dt
import html
import json
import re
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "raw"
DATA_PATH = ROOT / "data" / "rankings.json"

AJAX_CATEGORIES = {
    "free_today": ("today", "무료 베스트"),
    "paid_today": ("plsa.eachtoday", "유료 베스트"),
    "favorites": ("prefer", "선호작 베스트"),
    "bestseller": ("plsa.bestseller", "베스트셀러"),
}


def clean_title(value):
    value = html.unescape(str(value or ""))
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"^\s*(NEW|완결|독점|공모전)\s*", "", value, flags=re.I)
    return re.sub(r"\s+", " ", value).strip()


def collect_ajax(section, label, collected_at):
    titles = []
    seen = set()
    errors = []
    collection_date = None
    safe = section.replace(".", "_")

    for page in range(1, 4):
        path = RAW_DIR / f"{safe}-{page}.json"
        if not path.exists() or path.stat().st_size == 0:
            errors.append(f"{page}페이지 응답 없음")
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            collection_date = collection_date or payload.get("get_date")
            entries = payload.get("list") or []
            if not entries:
                errors.append(f"{page}페이지 작품 없음")
            for entry in entries:
                title = clean_title(entry.get("nvTitle"))
                if title and title not in seen:
                    seen.add(title)
                    titles.append(title)
        except Exception as exc:
            errors.append(f"{page}페이지 해석 실패: {exc}")

    return {
        "label": label,
        "collectedAt": collected_at,
        "collectionDate": collection_date,
        "status": "complete" if len(titles) >= 30 else ("partial" if titles else "failed"),
        "source": (
            "https://mm.munpia.com/?ajx=1&menu=best&action=list"
            f"&section={section}&keyword=&page=1"
        ),
        **({"error": "; ".join(errors)} if errors else {}),
        "titles": titles[:30],
    }


def collect_exclusive(collected_at):
    path = RAW_DIR / "exclusive.html"
    titles = []
    seen = set()
    errors = []

    if path.exists() and path.stat().st_size:
        text = path.read_text(encoding="utf-8", errors="ignore")
        pattern = re.compile(
            r'<span\b[^>]*class=["\'][^"\']*\btitle-wrap\b[^"\']*["\'][^>]*>'
            r"([\s\S]*?)</span>",
            re.I,
        )
        for match in pattern.finditer(text):
            title = clean_title(match.group(1))
            if title and title not in seen and 2 <= len(title) <= 100:
                seen.add(title)
                titles.append(title)
            if len(titles) >= 30:
                break
    else:
        errors.append("데스크톱 페이지 응답 없음")

    if not titles and not errors:
        errors.append("데스크톱 페이지에서 작품을 찾지 못했습니다.")

    return {
        "label": "선독점 베스트",
        "collectedAt": collected_at,
        "collectionDate": None,
        "status": "complete" if len(titles) >= 30 else ("partial" if titles else "failed"),
        "source": "https://www.munpia.com/best/plsa.exclusive-eachtoday",
        **({"error": "; ".join(errors)} if errors else {}),
        "titles": titles[:30],
    }


def main():
    now = dt.datetime.now(ZoneInfo("Asia/Seoul"))
    date = now.strftime("%Y-%m-%d")
    collected_at = now.isoformat(timespec="seconds")

    rankings = {
        key: collect_ajax(section, label, collected_at)
        for key, (section, label) in AJAX_CATEGORIES.items()
    }
    rankings["exclusive_today"] = collect_exclusive(collected_at)

    ordered = {
        "free_today": rankings["free_today"],
        "paid_today": rankings["paid_today"],
        "exclusive_today": rankings["exclusive_today"],
        "favorites": rankings["favorites"],
        "bestseller": rankings["bestseller"],
    }

    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    snapshot = next((item for item in data["snapshots"] if item["date"] == date), None)
    if snapshot is None:
        snapshot = {"date": date, "rankings": {}}
        data["snapshots"].append(snapshot)
    snapshot["rankings"] = ordered

    data["snapshots"].sort(key=lambda item: item["date"])
    data["updatedAt"] = collected_at
    data.setdefault("collectionLog", []).append(
        {
            "date": date,
            "message": " · ".join(
                f"{ranking['label']} {len(ranking['titles'])}개"
                + (f" ({ranking.get('error')})" if ranking.get("error") else "")
                for ranking in ordered.values()
            ),
        }
    )
    data["collectionLog"] = data["collectionLog"][-90:]
    DATA_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    for key, ranking in ordered.items():
        print(f"{key}: {ranking['status']} {len(ranking['titles'])}개")

    if not any(ranking["titles"] for ranking in ordered.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
