"""Smoke test for direct portals, ATS adapters, and opt-in board fallback."""

import logging

from jobspy import (
    get_semiconductor_career_sites,
    scrape_semiconductor_career_portals_playwright,
)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    career_sites = get_semiconductor_career_sites()
    print(f"Loaded {len(career_sites)} official semiconductor career sites.")

    jobs = scrape_semiconductor_career_portals_playwright(
        role="intern",
        keywords_file="keywords.txt",
        career_sites_file="career_sites.txt",
        location="United States",
        results_wanted=50,
        results_wanted_per_company=1,
        max_pages_per_company=5,
        delay=1.0,
        fallback_to_job_boards=False,
        fallback_sites=["google", "linkedin", "indeed"],
        verbose=True,
        ignore_role_keywords=False,
    )

    if jobs.empty:
        print("No jobs were found on the portals, ATS adapters, or fallback boards.")
        return

    columns = [
        "target_company",
        "title",
        "location",
        "site",
        "job_url",
        "target_careers_url",
    ]
    print(f"Scraped {len(jobs)} internship jobs.")
    print(
        jobs[[column for column in columns if column in jobs.columns]]
        .head(10)
        .to_string(index=False)
    )


if __name__ == "__main__":
    main()
