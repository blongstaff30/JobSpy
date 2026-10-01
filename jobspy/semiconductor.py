"""Semiconductor employers and helpers for searching their public job boards."""

from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files
import csv
import json
import logging
from pathlib import Path
import time
from urllib.parse import quote_plus, urlsplit

import pandas as pd
import requests
import urllib3
from bs4 import BeautifulSoup


log = logging.getLogger("JobSpy:Semiconductor")

ATS_HOSTS = {
    "myworkdayjobs.com": "workday",
    "greenhouse.io": "greenhouse",
    "lever.co": "lever",
}


def _ats_type(host: str) -> str | None:
    host = host.casefold().removeprefix("www.")
    for suffix, ats_type in ATS_HOSTS.items():
        if host == suffix or host.endswith(f".{suffix}"):
            return ats_type
    return None


def _matches_job(title: str, description: str, role_terms: list[str]) -> bool:
    haystack = f"{title} {description}".casefold()
    if not role_terms:
        return True
    for keyword in role_terms:
        keyword_words = keyword.casefold().split()
        matched_words = sum(word in haystack for word in keyword_words)
        required_words = (len(keyword_words) + 1) // 2
        if matched_words >= required_words:
            return True
    return False


def load_semiconductor_keywords(path: str | Path) -> list[str]:
    """Load quoted, comma-separated keyword phrases from a UTF-8 file."""
    keywords: list[str] = []
    reader = csv.reader(
        Path(path).read_text(encoding="utf-8").splitlines(),
        skipinitialspace=True,
    )
    for row in reader:
        for keyword in row:
            keyword = keyword.strip()
            if keyword and not keyword.startswith("#"):
                keywords.append(keyword.casefold())
    if not keywords:
        raise ValueError(f"No keywords found in {path}")
    return keywords


def _ats_jobs(
    ats_type: str,
    endpoint: str,
    company: "SemiconductorCompany",
    role_terms: list[str],
    location_aliases: tuple[str, ...],
    session: requests.Session,
) -> list[dict[str, object]]:
    """Fetch jobs from a discovered public ATS endpoint."""
    host = urlsplit(endpoint).netloc.casefold().removeprefix("www.")
    if ats_type == "greenhouse":
        path = urlsplit(endpoint).path.strip("/").split("/")
        token = path[0] if path else ""
        if not token:
            return []
        response = session.get(
            f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs",
            params={"content": "true"},
        )
        response.raise_for_status()
        postings = response.json().get("jobs", [])
    elif ats_type == "lever":
        site = urlsplit(endpoint).path.strip("/").split("/")[0]
        if not site:
            return []
        response = session.get(f"https://api.lever.co/v0/postings/{site}", params={"mode": "json"})
        response.raise_for_status()
        postings = response.json()
    elif ats_type == "workday":
        parts = urlsplit(endpoint)
        host_parts = parts.netloc.split(".")
        if len(host_parts) < 3:
            return []
        tenant = host_parts[0]
        site = parts.path.strip("/").split("/")[0]
        if not site:
            return []
        response = session.post(
            f"{parts.scheme}://{parts.netloc}/wday/cxs/{tenant}/{site}/jobs",
            json={
                "appliedFacets": {},
                "limit": 20,
                "offset": 0,
                "searchText": " ".join(role_terms),
            },
        )
        response.raise_for_status()
        postings = response.json().get("jobPostings", [])
    else:
        return []

    rows = []
    for posting in postings:
        title = str(posting.get("title") or posting.get("name") or "")
        description = str(posting.get("content") or posting.get("description") or "")
        location = posting.get("location")
        if isinstance(location, dict):
            location = location.get("name") or location.get("city")
        location = str(location or "")
        if not _matches_job(title, description, role_terms):
            continue
        if location_aliases and location and not any(
            alias in location.casefold() for alias in location_aliases
        ):
            continue
        job_url = (
            posting.get("absolute_url")
            or posting.get("hostedUrl")
            or posting.get("url")
            or posting.get("externalPath")
        )
        if not job_url:
            continue
        if posting.get("externalPath") and not job_url.startswith("http"):
            job_url = f"{urlsplit(endpoint).scheme}://{urlsplit(endpoint).netloc}{job_url}"
        rows.append(
            {
                "site": f"company_portal_{ats_type}",
                "title": title,
                "company": company.name,
                "location": location or None,
                "job_url": job_url,
                "description": description,
                "target_company": company.name,
                "target_careers_url": company.careers_url,
            }
        )
    return rows


@dataclass(frozen=True)
class SemiconductorCompany:
    """A semiconductor employer and the public boards where it can be searched."""

    name: str
    careers_url: str

    @property
    def job_boards(self) -> dict[str, str]:
        """Return board search URLs scoped to this employer."""
        query = quote_plus(f'"{self.name}"')
        return {
            "linkedin": f"https://www.linkedin.com/jobs/search/?keywords={query}",
            "indeed": f"https://www.indeed.com/jobs?q={query}",
            "glassdoor": f"https://www.glassdoor.com/Job/jobs.htm?sc.keyword={query}",
            "google": f"https://www.google.com/search?q={query}+semiconductor+jobs",
        }

    def search_urls(
        self,
        role: str = "process engineering intern",
        location: str | None = None,
    ) -> dict[str, str]:
        """Return direct and public-board URLs for a role at this company.

        Career sites use different ATS platforms and query formats, so the
        official careers page is provided directly and Google is used for a
        domain-scoped career-site search.
        """
        location_query = f" {location}" if location else ""
        role_query = quote_plus(f'"{self.name}" {role}{location_query}')
        domain = urlsplit(self.careers_url).netloc
        return {
            "careers": self.careers_url,
            "careers_search": (
                f"https://www.google.com/search?q={role_query}+site%3A{domain}"
            ),
            "linkedin": (
                "https://www.linkedin.com/jobs/search/?keywords="
                f"{quote_plus(f'{self.name} {role}')}"
            ),
            "indeed": (
                f"https://www.indeed.com/jobs?q={quote_plus(f'{self.name} {role}')}"
                + (f"&l={quote_plus(location)}" if location else "")
            ),
            "glassdoor": (
                "https://www.glassdoor.com/Job/jobs.htm?sc.keyword="
                f"{quote_plus(f'{self.name} {role}')}"
            ),
            "google": f"https://www.google.com/search?q={role_query}+jobs",
        }


def _load_career_sites_file(path: str | Path | object) -> tuple[SemiconductorCompany, ...]:
    """Load ``Company Name | careers URL`` entries from a small text file."""
    if hasattr(path, "read_text"):
        content = path.read_text(encoding="utf-8")
    else:
        content = Path(path).read_text(encoding="utf-8")

    companies: list[SemiconductorCompany] = []
    seen_urls: set[str] = set()
    for line_number, raw_line in enumerate(content.splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "|" in line:
            name, url = (part.strip() for part in line.split("|", 1))
        else:
            url = line
            host = urlsplit(url).netloc.removeprefix("www.")
            name = host.split(".")[0].replace("-", " ").title()
        if not name or (
            url.casefold() != "default"
            and not url.startswith(("http://", "https://"))
        ):
            raise ValueError(
                f"Invalid career-site entry on line {line_number}: {raw_line!r}"
            )
        if url in seen_urls:
            continue
        seen_urls.add(url)
        companies.append(SemiconductorCompany(name, url))
    if not companies:
        raise ValueError(f"No career sites found in {path}")
    return tuple(companies)


DEFAULT_CAREER_SITES_FILE = files("jobspy").joinpath("career_sites.txt")
SEMICONDUCTOR_COMPANIES: tuple[SemiconductorCompany, ...] = _load_career_sites_file(
    DEFAULT_CAREER_SITES_FILE
)


def get_semiconductor_companies() -> tuple[SemiconductorCompany, ...]:
    """Return the semiconductor company directory loaded from career_sites.txt."""
    return SEMICONDUCTOR_COMPANIES


def get_semiconductor_career_sites(
    companies: list[str] | tuple[str, ...] | None = None,
    career_sites_file: str | Path | None = None,
) -> list[dict[str, str]]:
    """Return official careers URLs for the selected semiconductor companies."""
    selected = _load_career_sites_file(career_sites_file or DEFAULT_CAREER_SITES_FILE)
    if companies is not None:
        requested = {company.casefold() for company in companies}
        available = {company.name.casefold() for company in selected}
        unknown = requested - available
        if unknown:
            raise ValueError(f"Unknown semiconductor company: {sorted(unknown)[0]}")
        selected = tuple(
            company for company in selected if company.name.casefold() in requested
        )

    return [
        {"company": company.name, "careers_url": company.careers_url}
        for company in selected
    ]


def scrape_semiconductor_career_portals(
    role: str = "process engineering intern",
    *,
    keywords_file: str | Path | None = None,
    career_sites_file: str | Path | None = None,
    location: str | None = None,
    results_wanted: int = 10,
    results_wanted_per_company: int | None = None,
    companies: list[str] | tuple[str, ...] | None = None,
    max_pages_per_company: int = 3,
    timeout: int = 20,
    delay: float = 1.0,
    user_agent: str = "JobSpy semiconductor career portal crawler",
    fallback_to_job_boards: bool = False,
    fallback_sites: list[str] | tuple[str, ...] = (
        "google",
        "linkedin",
        "indeed",
    ),
) -> pd.DataFrame:
    """Scrape public job data directly from official career portals.

    The crawler stays on the registered careers host (including subdomains),
    follows career/job links, and reads ``JobPosting`` JSON-LD when available.
    Public job boards are queried only when ``fallback_to_job_boards`` is true.
    """
    if results_wanted < 1:
        raise ValueError("results_wanted must be at least 1")
    if max_pages_per_company < 1:
        raise ValueError("max_pages_per_company must be at least 1")
    if results_wanted_per_company is not None and results_wanted_per_company < 1:
        raise ValueError("results_wanted_per_company must be at least 1")

    selected = (
        _load_career_sites_file(career_sites_file)
        if career_sites_file is not None
        else SEMICONDUCTOR_COMPANIES
    )
    if companies is not None:
        requested = {company.casefold() for company in companies}
        available = {company.name.casefold() for company in selected}
        unknown = requested - available
        if unknown:
            raise ValueError(f"Unknown semiconductor company: {sorted(unknown)[0]}")
        selected = tuple(
            company for company in selected if company.name.casefold() in requested
        )

    headers = {"User-Agent": user_agent}
    session = requests.Session()
    session.headers.update(headers)
    role_terms = (
        load_semiconductor_keywords(keywords_file)
        if keywords_file is not None
        else [term.casefold() for term in role.split() if len(term.strip()) >= 3]
    )
    requested_location = (location or "").casefold()
    location_aliases = {
        "united states": ("united states", "usa", "us"),
        "us": ("united states", "usa", "us"),
        "usa": ("united states", "usa", "us"),
    }.get(requested_location, (requested_location,))
    rows: list[dict[str, object]] = []
    for company in selected:
        company_rows_before = len(rows)
        company_limit = results_wanted_per_company or results_wanted
        if len(rows) >= results_wanted:
            break
        if company.careers_url.casefold() == "default":
            fallback = scrape_semiconductor_jobs(
                role=role,
                companies=[company.name],
                site_name=list(fallback_sites),
                location=location,
                results_wanted=results_wanted,
            )
            if not fallback.empty:
                fallback_rows = [
                    row
                    for row in fallback.to_dict("records")
                    if _matches_job(
                        str(row.get("title", "")),
                        str(row.get("description", "")),
                        role_terms,
                    )
                ]
                rows.extend(
                    fallback_rows[
                        : min(
                            company_limit - (len(rows) - company_rows_before),
                            results_wanted - len(rows),
                        )
                    ]
                )
            continue
        base_url = company.careers_url
        base_host = urlsplit(base_url).netloc.casefold().removeprefix("www.")
        pending = [base_url]
        visited: set[str] = set()
        pages_read = 0
        while pending and pages_read < max_pages_per_company and len(rows) < results_wanted:
            url = pending.pop(0)
            if url in visited:
                continue
            visited.add(url)
            try:
                response = session.get(url, timeout=timeout)
                response.raise_for_status()
            except requests.RequestException:
                continue
            pages_read += 1
            soup = BeautifulSoup(response.text, "html.parser")
            ats_endpoints: dict[str, str] = {}
            for anchor in soup.select("a[href]"):
                child_url = requests.compat.urljoin(response.url, anchor["href"])
                ats_type = _ats_type(urlsplit(child_url).netloc)
                if ats_type:
                    ats_endpoints[ats_type] = child_url
            for ats_type, endpoint in ats_endpoints.items():
                try:
                    ats_rows = _ats_jobs(
                        ats_type,
                        endpoint,
                        company,
                        role_terms,
                        location_aliases,
                        session,
                    )
                except (requests.RequestException, ValueError):
                    ats_rows = []
                for row in ats_rows:
                    if len(rows) >= results_wanted:
                        break
                    if not any(existing["job_url"] == row["job_url"] for existing in rows):
                        rows.append(row)
                if len(rows) >= results_wanted:
                    break
            for script in soup.select('script[type="application/ld+json"]'):
                try:
                    data = json.loads(script.string or script.get_text())
                except (TypeError, json.JSONDecodeError):
                    continue
                postings = data if isinstance(data, list) else [data]
                for posting in postings:
                    if isinstance(posting, dict) and posting.get("@graph"):
                        postings.extend(posting["@graph"])
                    if not isinstance(posting, dict):
                        continue
                    if posting.get("@type") != "JobPosting":
                        continue
                    title = str(posting.get("title") or "")
                    posting_location = posting.get("jobLocation")
                    if isinstance(posting_location, list):
                        posting_location = posting_location[0] if posting_location else {}
                    if isinstance(posting_location, dict):
                        address = posting_location.get("address", posting_location)
                        posting_location = ", ".join(
                            str(address.get(key))
                            for key in ("addressLocality", "addressRegion", "addressCountry")
                            if isinstance(address, dict) and address.get(key)
                        )
                    else:
                        posting_location = str(posting_location or "")
                    if not _matches_job(
                        title,
                        str(posting.get("description", "")),
                        role_terms,
                    ):
                        continue
                    posting_location_text = (
                        f"{posting_location} {posting.get('jobLocationType', '')}"
                    ).casefold()
                    if location and posting_location and not any(
                        alias in posting_location_text for alias in location_aliases
                    ):
                        continue
                    job_url = posting.get("url") or url
                    if any(row["job_url"] == job_url for row in rows):
                        continue
                    rows.append(
                        {
                            "title": title,
                            "company": company.name,
                            "location": posting_location or None,
                            "job_url": job_url,
                            "description": posting.get("description"),
                            "target_company": company.name,
                            "target_careers_url": company.careers_url,
                            "site": "company_portal",
                        }
                    )
                    if len(rows) >= results_wanted:
                        break
                if len(rows) >= results_wanted:
                    break

            for anchor in soup.select("a[href]"):
                href = anchor.get("href")
                if not href:
                    continue
                child_url = requests.compat.urljoin(response.url, href)
                child_parts = urlsplit(child_url)
                child_host = child_parts.netloc.casefold().removeprefix("www.")
                link_text = f"{anchor.get_text(' ', strip=True)} {child_parts.path}".casefold()
                if (
                    child_parts.scheme in ("http", "https")
                    and (child_host == base_host or child_host.endswith(f".{base_host}"))
                    and any(term in link_text for term in ("career", "job", "intern", "employment"))
                    and child_url not in visited
                ):
                    pending.append(child_url)
            if delay and pending:
                time.sleep(delay)

    if fallback_to_job_boards and len(rows) < results_wanted:
        for fallback_site in fallback_sites:
            if len(rows) >= results_wanted:
                break
            try:
                fallback_jobs = scrape_semiconductor_jobs(
                    role=role,
                    companies=[company.name for company in selected],
                    site_name=fallback_site,
                    location=location,
                    results_wanted=results_wanted - len(rows),
                )
            except (
                KeyError,
                requests.RequestException,
                urllib3.exceptions.HTTPError,
                urllib3.exceptions.ResponseError,
            ) as exc:
                log.warning(
                    "Skipping fallback board %s after request failure: %s",
                    fallback_site,
                    exc,
                )
                continue
            if not fallback_jobs.empty:
                rows.extend(
                    fallback_jobs.head(results_wanted - len(rows)).to_dict("records")
                )

    columns = [
        "site",
        "title",
        "company",
        "location",
        "job_url",
        "description",
        "target_company",
        "target_careers_url",
    ]
    return pd.DataFrame(rows, columns=columns)


def scrape_semiconductor_career_portals_playwright(
    role: str = "intern",
    *,
    search_query: str | None = None,
    filter_role: str | None = None,
    keywords_file: str | Path | None = None,
    career_sites_file: str | Path | None = None,
    location: str | None = None,
    results_wanted: int = 10,
    results_wanted_per_company: int | None = None,
    companies: list[str] | tuple[str, ...] | None = None,
    max_pages_per_company: int = 100,
    company_timeout: float = 30.0,
    timeout: int = 20_000,
    interaction_timeout: int = 2_000,
    delay: float = 1.0,
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) "
        "Gecko/20100101 Firefox/128.0"
    ),
    fallback_to_job_boards: bool = False,
    ignore_role_keywords: bool = False,
    verbose: bool = False,
    fallback_sites: list[str] | tuple[str, ...] = (
        "google",
        "linkedin",
        "indeed",
    ),
) -> pd.DataFrame:
    """Scrape JavaScript-rendered career portals with Firefox.

    Images, fonts, media, stylesheets, and common analytics/ad requests are
    aborted to reduce load time. Install the optional dependency and browser
    with ``pip install -e .[playwright]`` and ``playwright install firefox``.
    """
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise ImportError(
            "Playwright support requires `pip install -e .[playwright]` "
            "and `playwright install firefox`."
        ) from exc

    if results_wanted < 1:
        raise ValueError("results_wanted must be at least 1")
    if results_wanted_per_company is not None and results_wanted_per_company < 1:
        raise ValueError("results_wanted_per_company must be at least 1")
    if company_timeout <= 0:
        raise ValueError("company_timeout must be greater than 0")
    if interaction_timeout < 1:
        raise ValueError("interaction_timeout must be at least 1")

    selected = (
        _load_career_sites_file(career_sites_file)
        if career_sites_file is not None
        else _select_semiconductor_companies(companies)
    )
    filter_terms = filter_role if filter_role is not None else role
    role_terms = (
        load_semiconductor_keywords(keywords_file)
        if keywords_file is not None
        else [term.casefold() for term in filter_terms.split() if len(term) >= 3]
    )
    portal_search_query = search_query if search_query is not None else role
    location_aliases = _location_aliases(location)
    rows: list[dict[str, object]] = []

    def should_abort(request) -> bool:
        if request.resource_type in {"image", "font", "media", "stylesheet"}:
            return True
        return any(
            marker in request.url.casefold()
            for marker in (
                "google-analytics",
                "googletagmanager",
                "doubleclick",
                "/analytics",
                "/advert",
            )
        )

    def search_portal(
        page,
        company: SemiconductorCompany,
        search_query: str,
        deadline: float,
    ) -> None:
        """Submit one discoverable portal search form."""
        remaining_ms = max(
            1, min(timeout, int((deadline - time.monotonic()) * 1000))
        )
        page.set_default_timeout(min(interaction_timeout, remaining_ms))
        search_box = page.locator(
            'input[placeholder*="search" i], '
            'input[placeholder*="keyword" i], '
            'input[aria-label*="search" i], '
            'input[aria-label*="keyword" i], '
            'input[name*="search" i], '
            'input[name*="keyword" i], '
            'input[type="search"]'
        ).first
        try:
            if search_box.count() == 0:
                return
            search_box.fill(search_query)
            form = search_box.locator("xpath=ancestor::form[1]")
            if form.count():
                submit = form.locator(
                    'button[type="submit"], input[type="submit"], '
                    'button:has-text("Search"), button:has-text("Find")'
                ).first
                if submit.count():
                    submit.click()
                else:
                    search_box.press("Enter")
            else:
                search_box.press("Enter")
            page.wait_for_load_state("domcontentloaded", timeout=remaining_ms)
            page.wait_for_timeout(min(1000, remaining_ms))
            if verbose:
                log.info(
                    "portal %s: submitted search for %r",
                    company.name,
                    search_query,
                )
        except PlaywrightTimeoutError:
            raise
        except Exception as exc:
            if verbose:
                log.info("portal %s: search form not submitted (%s)", company.name, exc)

    def next_page(page, deadline: float) -> bool:
        """Click a visible next/load-more control, if present."""
        remaining_ms = max(
            1, min(timeout, int((deadline - time.monotonic()) * 1000))
        )
        page.set_default_timeout(min(interaction_timeout, remaining_ms))
        selectors = (
            'a[rel="next"]',
            'button:has-text("Next")',
            'a:has-text("Next")',
            'button:has-text("Load more")',
            'button:has-text("Show more")',
            'a:has-text("Load more")',
            'a:has-text("Show more")',
        )
        for selector in selectors:
            control = page.locator(selector).last
            try:
                if (
                    control.count() == 0
                    or not control.is_visible()
                    or not control.is_enabled()
                ):
                    continue
                before = page.content()
                control.click()
                page.wait_for_load_state("domcontentloaded", timeout=remaining_ms)
                page.wait_for_timeout(min(750, remaining_ms))
                return page.content() != before
            except PlaywrightTimeoutError:
                raise
            except Exception:
                continue
            except KeyboardInterrupt:
                if verbose:
                    log.warning("Pagination interrupted; skipping current portal")
                return False
        return False

    with sync_playwright() as playwright:
        browser = playwright.firefox.launch()
        context = browser.new_context(user_agent=user_agent)
        page = context.new_page()
        page.set_default_timeout(interaction_timeout)
        page.route(
            "**/*",
            lambda route: (
                route.abort()
                if should_abort(route.request)
                else route.continue_()
            ),
        )
        try:
            for company in selected:
                company_rows_before = len(rows)
                company_limit = results_wanted_per_company or results_wanted
                company_deadline = time.monotonic() + company_timeout
                if len(rows) >= results_wanted:
                    break
                if company.careers_url.casefold() == "default":
                    fallback = scrape_semiconductor_jobs(
                        role=role,
                        companies=[company.name],
                        site_name=list(fallback_sites),
                        location=location,
                        results_wanted=results_wanted,
                    )
                    if not fallback.empty:
                        fallback_rows = [
                            row
                            for row in fallback.to_dict("records")
                            if ignore_role_keywords
                            or _matches_job(
                                str(row.get("title", "")),
                                str(row.get("description", "")),
                                role_terms,
                            )
                        ]
                        rows.extend(
                            fallback_rows[
                                : min(
                                    company_limit,
                                    results_wanted - len(rows),
                                )
                            ]
                        )
                    continue
                pages_read = 0
                jobs_before = len(rows)
                page.set_default_timeout(int(company_timeout * 1000))
                search_queries = [portal_search_query]
                if "intern" not in portal_search_query.casefold():
                    search_queries.append("intern")
                if verbose:
                    log.info("portal %s: starting at %s", company.name, company.careers_url)
                for search_query in search_queries:
                    if (
                        time.monotonic() >= company_deadline
                        or
                        pages_read >= max_pages_per_company
                        or len(rows) - company_rows_before >= company_limit
                        or len(rows) >= results_wanted
                    ):
                        break
                    try:
                        page.goto(
                            company.careers_url,
                            wait_until="domcontentloaded",
                            timeout=max(
                                1,
                                min(
                                    timeout,
                                    int((company_deadline - time.monotonic()) * 1000),
                                ),
                            ),
                        )
                        remaining_ms = max(
                            1,
                            min(
                                timeout,
                                int((company_deadline - time.monotonic()) * 1000),
                            ),
                        )
                        page.wait_for_timeout(min(750, remaining_ms))
                        search_portal(page, company, search_query, company_deadline)
                    except PlaywrightTimeoutError:
                        if verbose:
                            log.warning(
                                "portal %s: Playwright timeout; skipping company",
                                company.name,
                            )
                        break
                    except Exception as exc:
                        if verbose:
                            log.warning(
                                "portal %s: failed %s (%s)",
                                company.name,
                                company.careers_url,
                                exc,
                            )
                        continue
                    try:
                        while (
                            time.monotonic() < company_deadline
                            and pages_read < max_pages_per_company
                            and len(rows) - company_rows_before < company_limit
                            and len(rows) < results_wanted
                        ):
                            pages_read += 1
                            if verbose:
                                log.info(
                                    "portal %s: scraped page %d/%d %s (query=%r)",
                                    company.name,
                                    pages_read,
                                    max_pages_per_company,
                                    page.url,
                                    search_query,
                                )
                            html = page.content()
                            rows.extend(
                                _parse_portal_html(
                                    html,
                                    page.url,
                                    company,
                                    role_terms,
                                    location_aliases,
                                    len(rows) - company_rows_before,
                                    min(company_limit, results_wanted - len(rows)),
                                    ignore_role_keywords,
                                )
                            )
                            rows = rows[:company_rows_before + company_limit]
                            rows = rows[:results_wanted]
                            if not next_page(page, company_deadline):
                                break
                            if delay:
                                time.sleep(
                                    min(
                                        delay,
                                        max(0, company_deadline - time.monotonic()),
                                    )
                                )
                    except PlaywrightTimeoutError:
                        if verbose:
                            log.warning(
                                "portal %s: Playwright timeout; skipping company",
                                company.name,
                            )
                        break
                if time.monotonic() >= company_deadline and verbose:
                    log.warning(
                        "portal %s: skipped after %.1f-second company timeout",
                        company.name,
                        company_timeout,
                    )
                if verbose:
                    log.info(
                        "portal %s: finished; pages=%d, jobs=%d",
                        company.name,
                        pages_read,
                        len(rows) - jobs_before,
                    )
        finally:
            for resource, name in (
                (page, "page"),
                (context, "browser context"),
                (browser, "browser"),
            ):
                try:
                    resource.close()
                except KeyboardInterrupt:
                    log.warning("Interrupted while closing Playwright %s", name)
                except Exception as exc:
                    log.warning("Failed to close Playwright %s: %s", name, exc)

    if fallback_to_job_boards and len(rows) < results_wanted:
        from jobspy import scrape_semiconductor_career_portals

        fallback = scrape_semiconductor_career_portals(
            role=role,
            location=location,
            results_wanted=results_wanted,
            companies=companies,
            fallback_to_job_boards=True,
            fallback_sites=fallback_sites,
        )
        if not fallback.empty:
            rows.extend(fallback.head(results_wanted - len(rows)).to_dict("records"))
        elif verbose:
            log.info("fallback boards: no jobs returned")

    columns = [
        "site",
        "title",
        "company",
        "location",
        "job_url",
        "description",
        "target_company",
        "target_careers_url",
    ]
    return pd.DataFrame(rows[:results_wanted], columns=columns)


def _normalized_host(url: str) -> str:
    return urlsplit(url).netloc.casefold().removeprefix("www.")


def _select_semiconductor_companies(
    companies: list[str] | tuple[str, ...] | None,
) -> tuple[SemiconductorCompany, ...]:
    if companies is None:
        return SEMICONDUCTOR_COMPANIES
    requested = {company.casefold() for company in companies}
    available = {company.name.casefold() for company in SEMICONDUCTOR_COMPANIES}
    unknown = requested - available
    if unknown:
        raise ValueError(f"Unknown semiconductor company: {sorted(unknown)[0]}")
    return tuple(
        company
        for company in SEMICONDUCTOR_COMPANIES
        if company.name.casefold() in requested
    )


def _location_aliases(location: str | None) -> tuple[str, ...]:
    normalized = (location or "").casefold()
    return {
        "united states": ("united states", "usa", "us"),
        "us": ("united states", "usa", "us"),
        "usa": ("united states", "usa", "us"),
    }.get(normalized, (normalized,))


def _parse_portal_html(
    html: str,
    page_url: str,
    company: SemiconductorCompany,
    role_terms: list[str],
    location_aliases: tuple[str, ...],
    current_count: int,
    results_wanted: int,
    ignore_role_keywords: bool = False,
) -> list[dict[str, object]]:
    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict[str, object]] = []
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.string or script.get_text())
        except (TypeError, json.JSONDecodeError):
            continue
        postings = data if isinstance(data, list) else [data]
        for posting in postings:
            if isinstance(posting, dict) and posting.get("@graph"):
                postings.extend(posting["@graph"])
            if not isinstance(posting, dict) or posting.get("@type") != "JobPosting":
                continue
            title = str(posting.get("title") or "")
            description = str(posting.get("description") or "")
            if not ignore_role_keywords and not _matches_job(
                title, description, role_terms
            ):
                continue
            job_location = posting.get("jobLocation")
            if isinstance(job_location, dict):
                address = job_location.get("address", job_location)
                job_location = ", ".join(
                    str(address.get(key))
                    for key in ("addressLocality", "addressRegion", "addressCountry")
                    if isinstance(address, dict) and address.get(key)
                )
            job_location = str(job_location or "")
            if location_aliases and job_location and not any(
                alias in job_location.casefold() for alias in location_aliases
            ):
                continue
            rows.append(
                {
                    "site": "company_portal_playwright",
                    "title": title,
                    "company": company.name,
                    "location": job_location or None,
                    "job_url": posting.get("url") or page_url,
                    "description": description,
                    "target_company": company.name,
                    "target_careers_url": company.careers_url,
                }
            )
    if len(rows) < results_wanted:
        rows.extend(
            _parse_rendered_job_links(
                soup,
                page_url,
                company,
                role_terms,
                location_aliases,
                {row["job_url"] for row in rows},
                results_wanted - len(rows),
                ignore_role_keywords,
            )
        )
    return rows


def _parse_rendered_job_links(
    soup: BeautifulSoup,
    page_url: str,
    company: SemiconductorCompany,
    role_terms: list[str],
    location_aliases: tuple[str, ...],
    seen_urls: set[object],
    limit: int,
    ignore_role_keywords: bool,
) -> list[dict[str, object]]:
    """Extract job cards rendered as ordinary anchors instead of JSON-LD."""
    rows: list[dict[str, object]] = []
    for anchor in soup.select("a[href]"):
        href = anchor.get("href")
        title = anchor.get_text(" ", strip=True)
        if not href or len(title) < 4:
            continue
        job_url = requests.compat.urljoin(page_url, href)
        path = urlsplit(job_url).path.casefold()
        classes = " ".join(anchor.get("class", [])).casefold()
        if not (
            any(term in path for term in ("/job", "/jobs", "jobposting", "requisition"))
            or any(term in classes for term in ("job", "posting", "requisition"))
        ):
            continue
        card = anchor.find_parent(["article", "li"])
        if card is None:
            for parent in anchor.parents:
                parent_classes = " ".join(parent.get("class", [])).casefold()
                if any(
                    marker in parent_classes
                    for marker in ("job", "posting", "requisition", "card")
                ):
                    card = parent
                    break
        if card is None:
            card = anchor.parent
            if card and len(card.select("a[href]")) > 1:
                card = None
        card_text = card.get_text(" ", strip=True) if card else title
        if not ignore_role_keywords and not _matches_job(
            title, card_text, role_terms
        ):
            continue
        country_only_location = location_aliases in (
            ("united states", "usa", "us"),
            ("usa", "united states", "us"),
            ("us", "united states", "usa"),
        )
        if (
            location_aliases
            and not country_only_location
            and not any(alias in card_text.casefold() for alias in location_aliases)
        ):
            continue
        if job_url in seen_urls or any(row["job_url"] == job_url for row in rows):
            continue
        rows.append(
            {
                "site": "company_portal_rendered",
                "title": title,
                "company": company.name,
                "location": card_text or None,
                "job_url": job_url,
                "description": card_text,
                "target_company": company.name,
                "target_careers_url": company.careers_url,
            }
        )
        if len(rows) >= limit:
            break
    return rows


def get_semiconductor_job_searches(
    role: str = "process engineering intern",
    location: str | None = None,
    companies: list[str] | tuple[str, ...] | None = None,
) -> list[dict[str, str]]:
    """Return role-specific career-site and job-board URLs for the directory."""
    selected = SEMICONDUCTOR_COMPANIES
    if companies is not None:
        requested = {company.casefold() for company in companies}
        available = {company.name.casefold() for company in selected}
        unknown = requested - available
        if unknown:
            raise ValueError(f"Unknown semiconductor company: {sorted(unknown)[0]}")
        selected = tuple(
            company for company in selected if company.name.casefold() in requested
        )

    return [
        {
            "company": company.name,
            "careers_url": company.careers_url,
            **company.search_urls(role=role, location=location),
        }
        for company in selected
    ]


def scrape_semiconductor_jobs(
    role: str = "process engineering intern",
    *,
    companies: list[str] | tuple[str, ...] | None = None,
    site_name: str | list[str] | None = None,
    location: str | None = None,
    results_wanted: int = 15,
    **kwargs,
) -> pd.DataFrame:
    """Search JobSpy-supported boards for a role at semiconductor companies.

    ``role`` is combined with each company name before delegating to
    :func:`jobspy.scrape_jobs`. The returned rows retain the normal JobSpy
    schema and add ``target_company`` and ``target_careers_url``.
    """
    from jobspy import scrape_jobs

    selected = SEMICONDUCTOR_COMPANIES
    if companies is not None:
        requested = {company.casefold() for company in companies}
        available = {company.name.casefold() for company in selected}
        unknown = requested - available
        if unknown:
            raise ValueError(f"Unknown semiconductor company: {sorted(unknown)[0]}")
        selected = tuple(
            company for company in selected if company.name.casefold() in requested
        )

    frames: list[pd.DataFrame] = []
    for company in selected:
        jobs = scrape_jobs(
            site_name=site_name,
            search_term=f'"{company.name}" {role}',
            location=location,
            results_wanted=results_wanted,
            **kwargs,
        )
        if not jobs.empty:
            jobs = jobs.copy()
            jobs["target_company"] = company.name
            jobs["target_careers_url"] = company.careers_url
            frames.append(jobs)

    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


__all__ = [
    "SEMICONDUCTOR_COMPANIES",
    "SemiconductorCompany",
    "get_semiconductor_career_sites",
    "get_semiconductor_companies",
    "get_semiconductor_job_searches",
    "load_semiconductor_keywords",
    "scrape_semiconductor_career_portals",
    "scrape_semiconductor_career_portals_playwright",
    "scrape_semiconductor_jobs",
]
