"""Smoke test for direct portals, ATS adapters, and opt-in board fallback."""

import logging
import multiprocessing
from queue import Empty

import pandas as pd

from jobspy import (
    get_semiconductor_career_sites,
    scrape_semiconductor_career_portals_playwright,
)


def scrape_company(company_name: str, result_queue) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        jobs = scrape_semiconductor_career_portals_playwright(
            role="intern",
            keywords_file="keywords.txt",
            career_sites_file="career_sites.txt",
            companies=[company_name],
            location="United States",
            results_wanted=1,
            results_wanted_per_company=1,
            max_pages_per_company=5,
            company_timeout=60.0,
            delay=1.0,
            fallback_to_job_boards=False,
            verbose=True,
            ignore_role_keywords=False,
        )
        result_queue.put(("ok", jobs.to_dict("records")))
    except Exception as exc:
        result_queue.put(("error", f"{type(exc).__name__}: {exc}"))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    career_sites = get_semiconductor_career_sites()
    print(f"Loaded {len(career_sites)} official semiconductor career sites.")

    context = multiprocessing.get_context("spawn")
    records = []
    for site in career_sites:
        print(f"Starting {site['company']}...", flush=True)
        result_queue = context.Queue()
        process = context.Process(
            target=scrape_company,
            args=(site["company"], result_queue),
        )
        process.start()
        process.join(65)
        if process.is_alive():
            print(f"Skipping {site['company']} after 60-second timeout.", flush=True)
            process.terminate()
            process.join(5)
            continue
        try:
            status, result = result_queue.get(timeout=2)
        except Empty:
            print(f"{site['company']} exited without results.", flush=True)
            continue
        if status == "ok":
            records.extend(result[:1])
        else:
            print(f"{site['company']} failed: {result}", flush=True)
    jobs = pd.DataFrame(records)

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
