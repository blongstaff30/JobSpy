<img src="https://github.com/cullenwatson/JobSpy/assets/78247585/ae185b7e-e444-4712-8bb9-fa97f53e896b" width="400">

**JobSpy** is a job scraping library with the goal of aggregating all the jobs from popular job boards with one tool.

## Features

- Scrapes job postings from **LinkedIn**, **Indeed**, **Glassdoor**, **Google**, **ZipRecruiter**, & other job boards concurrently
- Aggregates the job postings in a dataframe
- Proxies support to bypass blocking

![jobspy](https://github.com/cullenwatson/JobSpy/assets/78247585/ec7ef355-05f6-4fd3-8161-a817e31c5c57)

### Installation

```
pip install -U python-jobspy
```

_Python version >= [3.10](https://www.python.org/downloads/release/python-3100/) required_

### Usage

```python
import csv
from jobspy import scrape_jobs

jobs = scrape_jobs(
    site_name=["indeed", "linkedin", "zip_recruiter", "google"], # "glassdoor", "bayt", "naukri", "bdjobs"
    search_term="software engineer",
    google_search_term="software engineer jobs near San Francisco, CA since yesterday",
    location="San Francisco, CA",
    results_wanted=20,
    hours_old=72,
    country_indeed='USA',
    
    # linkedin_fetch_description=True # gets more info such as description, direct job url (slower)
    # proxies=["208.195.175.46:65095", "208.195.175.45:65095", "localhost"],
)
print(f"Found {len(jobs)} jobs")
print(jobs.head())
jobs.to_csv("jobs.csv", quoting=csv.QUOTE_NONNUMERIC, escapechar="\\", index=False) # to_excel
```

### Semiconductor companies

JobSpy loads 50 major semiconductor manufacturers, equipment suppliers, and EDA
vendors from the bundled `jobspy/career_sites.txt` file. Each entry includes its
official careers page and generated LinkedIn, Indeed, Glassdoor, and Google
job-board URLs:

```python
from jobspy import get_semiconductor_job_searches, scrape_semiconductor_jobs

searches = get_semiconductor_job_searches(
    role="process engineering intern MSE",
    location="United States",
    companies=["Intel", "TSMC", "Applied Materials"],
)
for search in searches:
    print(search["company"], search["careers_url"], search["careers_search"])

jobs = scrape_semiconductor_jobs(
    role="process engineering intern MSE",
    companies=["Intel", "TSMC", "Applied Materials"],
    site_name=["linkedin", "indeed", "google"],
    location="United States",
    results_wanted=25,
)
```

`get_semiconductor_job_searches()` provides the official careers page, a
domain-scoped careers search, and role-specific LinkedIn, Indeed, Glassdoor,
and Google links. The helper delegates to the existing board scrapers. Results
include the normal JobSpy columns plus `target_company` and
`target_careers_url`.

To get the official careers pages without making automated requests, use:

```python
from jobspy import get_semiconductor_career_sites

career_sites = get_semiconductor_career_sites(
    companies=["Intel", "TSMC", "Applied Materials"],
)
for company in career_sites:
    print(company["company"], company["careers_url"])
```

This returns official company career URLs only. Open each site and use its own
role, location, and internship filters; no Google Jobs or proxy is required.

For portals that expose public `JobPosting` JSON-LD, JobSpy can crawl the
official site directly:

```python
from jobspy import scrape_semiconductor_career_portals

jobs = scrape_semiconductor_career_portals(
    role="process engineering intern",
    companies=["Intel", "TSMC", "Applied Materials"],
    location="United States",
    results_wanted=10,
    ignore_role_keywords=True,
)
```

This crawler stays on each company’s careers host, follows a small number of
career/job links, and does not call Google Jobs or third-party boards. Portals
that require JavaScript APIs or authentication may return no rows and need a
dedicated adapter.

For JavaScript-rendered portals, use the optional Firefox/Playwright crawler:

```powershell
python -m pip install -e ".[playwright]"
playwright install firefox
```

```python
from jobspy import scrape_semiconductor_career_portals_playwright

jobs = scrape_semiconductor_career_portals_playwright(
    role="intern",
    location="United States",
    results_wanted=10,
)
```

The default portal list is the bundled `jobspy/career_sites.txt` file. To use a
different lightweight list, provide another UTF-8 text file with one URL per
line. You can optionally provide a display name before a pipe:

```text
# company career portals
Intel | https://intel.wd1.myworkdayjobs.com/External
Example Company | default
https://careers.example.com/jobs
```

Use `Company Name | default` when a company does not have a direct portal
configured. That entry skips portal crawling and uses the configured fallback
sites (`google`, `linkedin`, and `indeed` by default).

Pass that file to the Playwright scraper:

```python
jobs = scrape_semiconductor_career_portals_playwright(
    role="intern",
    keywords_file="keywords.txt",
    career_sites_file="career_sites.txt",
    location="United States",
    verbose=False,
)
```

The text format uses less parsing overhead than a structured JSON file for a
simple URL list.

Use `results_wanted_per_company=1` with a larger `results_wanted` value to
collect a fixed number from each configured site instead of filling the total
from the first sites that return matches.

Keyword filtering can also be loaded from a UTF-8 file. Keywords are
comma-separated and quoted so multi-word phrases stay together:

```text
"Process Engineer", "TCAD Modeling", "R&D", "Materials"
```

Pass `keywords_file` to either official-portal scraper. The portal still
searches using `role` (or `search_query` for Playwright), while matching uses
the phrases from the file. Each phrase is evaluated independently: a phrase
matches when at least half of its words are present, rounded up, and a job is
accepted when any phrase matches. For example, `Process Engineer` matches
`Process` or `Engineer`, while `Materials` requires `Materials`.

It uses a Firefox user agent, discovers search inputs by placeholder or
accessible label, submits the role query, follows pagination/load-more
controls, and blocks images, fonts, media, stylesheets, and common analytics/ad
requests. `max_pages_per_company` defaults to 100 as a loop safety limit.
Set `verbose=True` to enable per-company INFO diagnostics; the default
`verbose=False` (or `--no-verbose` in a wrapper CLI) suppresses those blocks.
Public-board fallback remains opt-in.

To opt in to public-board fallback after direct portals and ATS adapters fail:

```python
jobs = scrape_semiconductor_career_portals(
    role="process engineering intern",
    results_wanted=10,
    fallback_to_job_boards=True,
    fallback_sites=["google", "linkedin", "indeed"],
)
```

The fallback is disabled by default. When enabled, direct company portals and
known ATS adapters are attempted first; only then are the selected JobSpy
boards queried.

### Output

```
SITE           TITLE                             COMPANY           CITY          STATE  JOB_TYPE  INTERVAL  MIN_AMOUNT  MAX_AMOUNT  JOB_URL                                            DESCRIPTION
indeed         Software Engineer                 AMERICAN SYSTEMS  Arlington     VA     None      yearly    200000      150000      https://www.indeed.com/viewjob?jk=5e409e577046...  THIS POSITION COMES WITH A 10K SIGNING BONUS!...
indeed         Senior Software Engineer          TherapyNotes.com  Philadelphia  PA     fulltime  yearly    135000      110000      https://www.indeed.com/viewjob?jk=da39574a40cb...  About Us TherapyNotes is the national leader i...
linkedin       Software Engineer - Early Career  Lockheed Martin   Sunnyvale     CA     fulltime  yearly    None        None        https://www.linkedin.com/jobs/view/3693012711      Description:By bringing together people that u...
linkedin       Full-Stack Software Engineer      Rain              New York      NY     fulltime  yearly    None        None        https://www.linkedin.com/jobs/view/3696158877      Rain’s mission is to create the fastest and ea...
zip_recruiter Software Engineer - New Grad       ZipRecruiter      Santa Monica  CA     fulltime  yearly    130000      150000      https://www.ziprecruiter.com/jobs/ziprecruiter...  We offer a hybrid work environment. Most US-ba...
zip_recruiter Software Developer                 TEKsystems        Phoenix       AZ     fulltime  hourly    65          75          https://www.ziprecruiter.com/jobs/teksystems-0...  Top Skills' Details• 6 years of Java developme...

```

### Parameters for `scrape_jobs()`

```plaintext
Optional
├── site_name (list|str): 
|    linkedin, zip_recruiter, indeed, glassdoor, google, bayt, bdjobs
|    (default is all)
│
├── search_term (str)
|
├── google_search_term (str)
|     search term for google jobs. This is the only param for filtering google jobs.
│
├── location (str)
│
├── distance (int): 
|    in miles, default 50
│
├── job_type (str): 
|    fulltime, parttime, internship, contract
│
├── proxies (list): 
|    in format ['user:pass@host:port', 'localhost']
|    each job board scraper will round robin through the proxies
|
├── is_remote (bool)
│
├── results_wanted (int): 
|    number of job results to retrieve for each site specified in 'site_name'
│
├── easy_apply (bool): 
|    filters for jobs that are hosted on the job board site (LinkedIn easy apply filter no longer works)
|
├── user_agent (str): 
|    override the default user agent which may be outdated
│
├── description_format (str): 
|    markdown, html (Format type of the job descriptions. Default is markdown.)
│
├── offset (int): 
|    starts the search from an offset (e.g. 25 will start the search from the 25th result)
│
├── hours_old (int): 
|    filters jobs by the number of hours since the job was posted 
|    (ZipRecruiter and Glassdoor round up to next day.)
│
├── verbose (int) {0, 1, 2}: 
|    Controls the verbosity of the runtime printouts 
|    (0 prints only errors, 1 is errors+warnings, 2 is all logs. Default is 2.)

├── linkedin_fetch_description (bool): 
|    fetches full description and direct job url for LinkedIn (Increases requests by O(n))
│
├── linkedin_company_ids (list[int]): 
|    searches for linkedin jobs with specific company ids
|
├── country_indeed (str): 
|    filters the country on Indeed & Glassdoor (see below for correct spelling)
|
├── enforce_annual_salary (bool): 
|    converts wages to annual salary
|
├── ca_cert (str)
|    path to CA Certificate file for proxies
```

```
├── Indeed limitations:
|    Only one from this list can be used in a search:
|    - hours_old
|    - job_type & is_remote
|    - easy_apply
│
└── LinkedIn limitations:
|    Only one from this list can be used in a search:
|    - hours_old
|    - easy_apply
```

## Supported Countries for Job Searching

### **LinkedIn**

LinkedIn searches globally & uses only the `location` parameter. 

### **ZipRecruiter**

ZipRecruiter searches for jobs in **US/Canada** & uses only the `location` parameter.

### **Indeed / Glassdoor**

Indeed & Glassdoor supports most countries, but the `country_indeed` parameter is required. Additionally, use the `location`
parameter to narrow down the location, e.g. city & state if necessary. 

You can specify the following countries when searching on Indeed (use the exact name, * indicates support for Glassdoor):

|                      |              |            |                |
|----------------------|--------------|------------|----------------|
| Argentina            | Australia*   | Austria*   | Bahrain        |
| Belgium*             | Brazil*      | Canada*    | Chile          |
| China                | Colombia     | Costa Rica | Czech Republic |
| Denmark              | Ecuador      | Egypt      | Finland        |
| France*              | Germany*     | Greece     | Hong Kong*     |
| Hungary              | India*       | Indonesia  | Ireland*       |
| Israel               | Italy*       | Japan      | Kuwait         |
| Luxembourg           | Malaysia     | Mexico*    | Morocco        |
| Netherlands*         | New Zealand* | Nigeria    | Norway         |
| Oman                 | Pakistan     | Panama     | Peru           |
| Philippines          | Poland       | Portugal   | Qatar          |
| Romania              | Saudi Arabia | Singapore* | South Africa   |
| South Korea          | Spain*       | Sweden     | Switzerland*   |
| Taiwan               | Thailand     | Turkey     | Ukraine        |
| United Arab Emirates | UK*          | USA*       | Uruguay        |
| Venezuela            | Vietnam*     |            |                |

### **Bayt**

Bayt only uses the search_term parameter currently and searches internationally



## Notes
* Indeed is the best scraper currently with no rate limiting.  
* All the job board endpoints are capped at around 1000 jobs on a given search.  
* LinkedIn is the most restrictive and usually rate limits around the 10th page with one ip. Proxies are a must basically.

## Frequently Asked Questions

---
**Q: Why is Indeed giving unrelated roles?**  
**A:** Indeed searches the description too.

- use - to remove words
- "" for exact match

Example of a good Indeed query

```py
search_term='"engineering intern" software summer (java OR python OR c++) 2025 -tax -marketing'
```

This searches the description/title and must include software, summer, 2025, one of the languages, engineering intern exactly, no tax, no marketing.

---

**Q: No results when using "google"?**  
**A:** You have to use super specific syntax. Search for google jobs on your browser and then whatever pops up in the google jobs search box after applying some filters is what you need to copy & paste into the google_search_term. 

---

**Q: Received a response code 429?**  
**A:** This indicates that you have been blocked by the job board site for sending too many requests. All of the job board sites are aggressive with blocking. We recommend:

- Wait some time between scrapes (site-dependent).
- Try using the proxies param to change your IP address.

---

### JobPost Schema

```plaintext
JobPost
├── title
├── company
├── company_url
├── job_url
├── location
│   ├── country
│   ├── city
│   ├── state
├── is_remote
├── description
├── job_type: fulltime, parttime, internship, contract
├── job_function
│   ├── interval: yearly, monthly, weekly, daily, hourly
│   ├── min_amount
│   ├── max_amount
│   ├── currency
│   └── salary_source: direct_data, description (parsed from posting)
├── date_posted
└── emails

Linkedin specific
└── job_level

Linkedin & Indeed specific
└── company_industry

Indeed specific
├── company_country
├── company_addresses
├── company_employees_label
├── company_revenue_label
├── company_description
└── company_logo

Naukri specific
├── skills
├── experience_range
├── company_rating
├── company_reviews_count
├── vacancy_count
└── work_from_home_type
```
