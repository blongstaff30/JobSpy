"""Scrape all semiconductor job boards and career portals."""

from pathlib import Path
import logging

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


def _desktop_output_file() -> Path:
    """Use the user's OneDrive Desktop folder."""
    desktop = Path.home() / "OneDrive" / "Desktop"
    desktop.mkdir(parents=True, exist_ok=True)
    return desktop / "semiconductor_jobs.txt"


OUTPUT_FILE = _desktop_output_file()


def _format_results(title: str, jobs: pd.DataFrame) -> str:
    if jobs.empty:
        return f"{title}\nNo jobs found.\n"
    output = pd.DataFrame(
        {
            "job_title": jobs.get("title", ""),
            "company": jobs.get("company", jobs.get("company_name", "")),
            "location": jobs.get("location", ""),
            "url": jobs.get("job_url", jobs.get("job_url_direct", "")),
        }
    )
    return f"{title}\n{output.to_csv(sep='\t', index=False, lineterminator='\n')}"


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
    print("Starting scrape_semiconductor_jobs() across all companies and boards...", flush=True)
    board_jobs = scrape_semiconductor_jobs(
        site_name=BOARD_SITES,
        results_wanted=RESULT_LIMIT,
        location=None,
        ignore_company=True,
        keywords_file=KEYWORDS_FILE,
        request_timeout=5,
    )
    board_output = _format_results("Results from scrape_semiconductor_jobs()", board_jobs)
    OUTPUT_FILE.write_text(board_output, encoding="utf-8-sig")
    print(
        f"Completed board scraping ({len(board_jobs)} results). "
        "Starting Playwright career portals...",
        flush=True,
    )

    portal_jobs = scrape_semiconductor_career_portals_playwright(
        keywords_file=KEYWORDS_FILE,
        results_wanted=RESULT_LIMIT,
        results_wanted_per_company=RESULT_LIMIT,
        fallback_to_job_boards=True,
        location=None,
    )
    portal_output = _format_results(
        "Results from scrape_semiconductor_career_portals_playwright()",
        portal_jobs,
    )
    with OUTPUT_FILE.open("a", encoding="utf-8") as output_file:
        output_file.write("\n" + portal_output)
    print(f"Wrote results to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
