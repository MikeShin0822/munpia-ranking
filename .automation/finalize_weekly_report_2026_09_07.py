from __future__ import annotations

import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "data" / "weekly-patterns" / "2026-09-07_2026-09-13.json"
LATEST_PATH = ROOT / "data" / "weekly-patterns" / "latest.json"
INDEX_PATH = ROOT / "data" / "weekly-patterns" / "index.json"


def main() -> None:
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    start = date.fromisoformat(report["startDate"])
    end = date.fromisoformat(report["endDate"])
    key = f"{report['startDate']}_{report['endDate']}"

    assert start.weekday() == 0, start
    assert end.weekday() == 6, end
    assert (end - start).days == 6
    assert report["dataQuality"]["complete"] is True
    assert report["analysisMethod"] == "llm_semantic_with_quantitative_support"
    assert len(report.get("patterns", [])) >= 8

    LATEST_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    reports = [item for item in index.get("reports", []) if item.get("key") != key]
    reports.append({
        "key": key,
        "startDate": report["startDate"],
        "endDate": report["endDate"],
        "title": report["title"],
        "generatedAt": report["generatedAt"],
        "analysisMethod": report["analysisMethod"],
    })
    reports.sort(key=lambda item: item["startDate"])
    updated = {
        "updatedAt": report["generatedAt"],
        "latestKey": key,
        "reports": reports,
    }
    INDEX_PATH.write_text(
        json.dumps(updated, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "latestKey": key,
        "reportCount": len(reports),
        "patterns": len(report["patterns"]),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
