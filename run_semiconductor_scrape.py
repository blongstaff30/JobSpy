"""Scrape all semiconductor job boards and career portals."""

from pathlib import Path
import logging
import json
import math
import shutil
import os
from datetime import datetime

import pandas as pd

from jobspy import (
    scrape_semiconductor_career_portals_playwright,
    scrape_semiconductor_jobs,
)


# The scraper APIs require a positive integer and do not support an "all"
# sentinel. A very large value makes some boards paginate indefinitely.
# Increase this deliberately if a larger bounded collection is needed.
RESULT_LIMIT = 100
# These boards returned errors or CAPTCHA/redirect responses in the test run.
BOARD_SITES = [
    "linkedin",
    "indeed",
    "google",
]
KEYWORDS_FILE = Path(__file__).with_name("keywords.txt")
CAREER_SITES_FILE = Path(__file__).with_name("career_sites.txt")


def _default_output_directory() -> Path:
    """Use the user's OneDrive Desktop folder."""
    desktop = Path.home() / "OneDrive" / "Desktop"
    desktop.mkdir(parents=True, exist_ok=True)
    return desktop


configured_output_directory = os.environ.get("JOBSPY_OUTPUT_DIRECTORY")
OUTPUT_DIRECTORY = Path(
    configured_output_directory
    if configured_output_directory
    else _default_output_directory()
)
OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)
OUTPUT_FILE = OUTPUT_DIRECTORY / "semiconductor_jobs.json"
PREVIOUS_OUTPUT_FILE = OUTPUT_DIRECTORY / "semiconductor_jobs_previous.json"
DIFFERENCE_OUTPUT_FILE = OUTPUT_DIRECTORY / "semiconductor_jobs_difference.json"


def _timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _result_records(jobs: pd.DataFrame) -> list[dict[str, object]]:
    """Project scraper rows to the stable, useful output schema."""
    if jobs.empty:
        return []

    company_column = "company" if "company" in jobs else "company_name"
    url_column = "job_url" if "job_url" in jobs else "job_url_direct"
    columns = {
        "job_title": "title",
        "company": company_column,
        "location": "location",
        "url": url_column,
        "description": "description",
        "date_posted": "date_posted",
    }
    records = []
    for row in jobs.to_dict("records"):
        record = {}
        for output_name, input_name in columns.items():
            value = row.get(input_name)
            if value is None or (
                isinstance(value, float) and math.isnan(value)
            ) or (not isinstance(value, (dict, list)) and pd.isna(value)):
                value = None
            record[output_name] = value
        records.append(record)
    return records


def _write_output(
    board_jobs: pd.DataFrame,
    portal_jobs: pd.DataFrame,
    output_file: Path,
) -> None:
    payload = {
        "board_results": _result_records(board_jobs),
        "career_portal_results": _result_records(portal_jobs),
    }
    output_file.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def _load_snapshot(path: Path) -> dict[str, list[dict[str, object]]]:
    if not path.is_file():
        return {"board_results": [], "career_portal_results": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {"board_results": [], "career_portal_results": []}
    return {
        "board_results": data.get("board_results", []),
        "career_portal_results": data.get("career_portal_results", []),
    }


def _record_key(record: dict[str, object]) -> str:
    return str(
        record.get("url")
        or (
            record.get("job_title"),
            record.get("company"),
            record.get("location"),
        )
    )


def _write_difference(previous: dict, current: dict, difference_file: Path) -> None:
    previous_records = {
        _record_key(record): record
        for section in previous.values()
        for record in section
    }
    current_records = {
        _record_key(record): record
        for section in current.values()
        for record in section
    }
    added_keys = current_records.keys() - previous_records.keys()
    removed_keys = previous_records.keys() - current_records.keys()
    changed_keys = (
        current_records.keys() & previous_records.keys()
    )
    difference = {
        "added": [current_records[key] for key in sorted(added_keys)],
        "removed": [previous_records[key] for key in sorted(removed_keys)],
        "changed": [
            {
                "before": previous_records[key],
                "after": current_records[key],
            }
            for key in sorted(changed_keys)
            if previous_records[key] != current_records[key]
        ],
    }
    difference_file.write_text(
        json.dumps(difference, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def main(output_directory: Path | None = None) -> dict[str, Path]:
    output_directory = output_directory or OUTPUT_DIRECTORY
    output_directory.mkdir(parents=True, exist_ok=True)
    output_file = output_directory / "semiconductor_jobs.json"
    previous_output_file = output_directory / "semiconductor_jobs_previous.json"
    difference_output_file = output_directory / "semiconductor_jobs_difference.json"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    )
    print(
        f"[{_timestamp()}] Starting scrape_semiconductor_jobs() "
        "across all companies and boards...",
        flush=True,
    )
    previous_snapshot = _load_snapshot(output_file)
    if output_file.is_file():
        shutil.copyfile(output_file, previous_output_file)
    elif not previous_output_file.is_file():
        previous_output_file.write_text(
            json.dumps(
                previous_snapshot,
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    board_jobs = scrape_semiconductor_jobs(
        site_name=BOARD_SITES,
        results_wanted=RESULT_LIMIT,
        location=None,
        ignore_company=True,
        keywords_file=KEYWORDS_FILE,
        request_timeout=5,
    )
    _write_output(board_jobs, pd.DataFrame(), output_file)
    print(
        f"[{_timestamp()}] Completed board scraping ({len(board_jobs)} results). "
        "Starting Playwright career portals...",
        flush=True,
    )

    portal_jobs = scrape_semiconductor_career_portals_playwright(
        role="intern",
        search_query="intern",
        filter_role=None,
        keywords_file=KEYWORDS_FILE,
        career_sites_file=CAREER_SITES_FILE,
        results_wanted=RESULT_LIMIT,
        results_wanted_per_company=RESULT_LIMIT,
        fallback_to_job_boards=True,
        location=None,
        verbose=True,
    )
    _write_output(board_jobs, portal_jobs, output_file)
    current_snapshot = _load_snapshot(output_file)
    _write_difference(previous_snapshot, current_snapshot, difference_output_file)
    print(
        f"[{_timestamp()}] Wrote results to {output_file}; "
        f"comparison to {previous_output_file} written to "
        f"{difference_output_file}",
        flush=True,
    )
    return {
        "current": output_file,
        "previous": previous_output_file,
        "difference": difference_output_file,
    }


if __name__ == "__main__":
    main()
