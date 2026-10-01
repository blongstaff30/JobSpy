"""Collect all available semiconductor jobs from boards, then career portals."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from jobspy import (
    get_semiconductor_career_sites,
    load_semiconductor_keywords,
    scrape_semiconductor_career_portals_playwright,
    scrape_semiconductor_jobs,
)
from jobspy.semiconductor import _matches_job


ROLE = "intern"
LOCATION = "United States"
KEYWORDS_FILE = Path("keywords.txt")
CAREER_SITES_FILE = Path("career_sites.txt")
OUTPUT_FILE = Path("semiconductor_jobs_all.txt")

# The public scraper APIs currently take integer limits. "all" is the user-facing
# setting; this cap is only a guard against a portal that never signals completion.
RESULTS_WANTED = "all"
RESULTS_PER_COMPANY = "all"
ALL_RESULTS_CAP = 1_000


def _all_results_cap(company_count: int) -> int:
    return max(ALL_RESULTS_CAP, company_count * ALL_RESULTS_CAP)


def _resolve_result_limit(value: str, company_count: int) -> int:
    if value != "all":
        raise ValueError(f"Unsupported result limit: {value!r}")
    return _all_results_cap(company_count)


def _filter_board_jobs(jobs: pd.DataFrame, keywords: list[str]) -> pd.DataFrame:
    if jobs.empty:
        return jobs
    matches = jobs.apply(
        lambda row: _matches_job(
            str(row.get("title", "")),
            str(row.get("description", "")),
            keywords,
        ),
        axis=1,
    )
    return jobs.loc[matches].reset_index(drop=True)


def _write_output(board_jobs: pd.DataFrame, portal_jobs: pd.DataFrame) -> None:
    sections = [
        ("JOB BOARDS", board_jobs),
        ("CAREER PORTALS", portal_jobs),
    ]
    with OUTPUT_FILE.open("w", encoding="utf-8") as output:
        for index, (title, jobs) in enumerate(sections):
            if index:
                output.write("\n\n")
            output.write(f"{title}\n")
            output.write("=" * len(title) + "\n")
            if jobs.empty:
                output.write("No jobs found.\n")
            else:
                output.write(jobs.to_string(index=False))
                output.write("\n")


def main() -> None:
    career_sites = get_semiconductor_career_sites(
        career_sites_file=CAREER_SITES_FILE
    )
    companies = [site["company"] for site in career_sites]
    results_cap = _resolve_result_limit(RESULTS_WANTED, len(companies))
    results_per_company_cap = _resolve_result_limit(
        RESULTS_PER_COMPANY, len(companies)
    )
    keywords = load_semiconductor_keywords(KEYWORDS_FILE)

    # Run public boards first. site_name=None means every supported JobSpy board.
    board_jobs = scrape_semiconductor_jobs(
        role=ROLE,
        companies=companies,
        site_name=None,
        location=LOCATION,
        results_wanted=results_cap,
    )
    board_jobs = _filter_board_jobs(board_jobs, keywords)

    # Run direct/browser portals second. The fallback is enabled for entries
    # whose direct portal cannot provide results.
    portal_jobs = scrape_semiconductor_career_portals_playwright(
        role=ROLE,
        keywords_file=KEYWORDS_FILE,
        career_sites_file=CAREER_SITES_FILE,
        location=LOCATION,
        results_wanted=results_cap,
        results_wanted_per_company=results_per_company_cap,
        max_pages_per_company=100,
        fallback_to_job_boards=True,
        verbose=True,
    )

    _write_output(board_jobs, portal_jobs)
    print(
        f"Wrote {len(board_jobs)} board jobs followed by "
        f"{len(portal_jobs)} portal jobs to {OUTPUT_FILE}"
    )


if __name__ == "__main__":
    main()
