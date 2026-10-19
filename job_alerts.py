#!/usr/bin/env python3
"""
Job Alerts for Find an Apprenticeship + Reed + Adzuna
==============================================================
Searches UK job sources for entry-level IT, digital/comms and electrician
apprenticeship roles near Manchester, scores them against user's CV,
dedupes against a seen-list, and writes a Markdown digest.

Usage:
    python3 job_alerts.py            # run all sources, write digest
    python3 job_alerts.py --seen     # path override for seen-jobs file
    python3 job_alerts.py --max-quiet # suppress low-scoring jobs in output

Environment (or edit CONFIG below):
    ADZUNA_APP_ID / ADZUNA_APP_KEY
    REED_API_KEY   (free key from reed.co.uk/developers/Jobseeker)
"""

import os, re, sys, json, html, time, urllib.request, urllib.parse, urllib.error
from datetime import datetime, timezone

# ------------------------------------------------------------------ CONFIG
CONFIG = {
    "ADZUNA_APP_ID": os.getenv("ADZUNA_APP_ID"),
    "ADZUNA_APP_KEY": os.getenv("ADZUNA_APP_KEY"),
    "REED_API_KEY": os.getenv("REED_API_KEY"),
    "OUT_DIR": os.getenv("JOBS_OUT_DIR"),
    "SEEN_FILE": os.getenv("JOBS_SEEN_FILE", "seen_jobs.json"),
    "MAX_PER_SOURCE": 30,          # cap results pulled per source per query
    "MIN_SCORE_TO_SHOW": 5,        # below this, job is dropped from digest
    "USER_AGENT": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
}

# ------------------------------------------------------------------ SEARCH PROFILES
# Tune keywords/radius here. "Boost"/"Penalty" feed the relevance scorer.
PROFILES = [
    {
        "name": "IT & Apprenticeships (entry)",
        "faa_search": {
            "WhatSearchTerm": "IT",
            "WhereSearchTerm": "Manchester",
            "Distance": 20,
        },
        "adzuna": {
            "what": "IT support apprentice OR IT technician apprentice OR service desk apprentice OR ICT apprentice",
            "where": "Manchester",
            "max_days_old": 21,
        },
        "reed": {
            "keywords": "IT support apprentice",
            "locationName": "Manchester",
            "distanceFromLocation": 20,
        },
        "sources": ["FAA", "Adzuna", "Reed", "NHSJobs", "ManchesterCC", "SalfordCC"],
        "boosts": {
            "apprentice": 4, "apprenticeship": 4, "trainee": 3, "entry level": 2,
            "junior": 2, "1st line": 3, "first line": 3, "service desk": 3,
            "helpdesk": 3, "help desk": 3, "it support": 4, "technician": 2,
            "ict": 2, "graduate": 2, "level 3": 2, "infrastructure": 2,
            "analyst": 1, "it logistics": 1, "it ": 1,
        },
        "penalties": {
            "senior": -6, "manager": -3, "head of": -5, "lead developer": -4,
            "principal": -5, "10 years": -4, "5+ years": -3, "director": -5,
            "architect": -4, "specialist": -1, "domestic": -4, "facilities": -3,
        },
    },
    {
        "name": "Digital, Comms & Accessibility",
        "faa_search": {
            "WhatSearchTerm": "digital",
            "WhereSearchTerm": "Manchester",
            "Distance": 25,
        },
        "adzuna": {
            "what": "digital officer OR communications officer OR website coordinator OR accessibility",
            "where": "Manchester",
            "max_days_old": 21,
        },
        "reed": {
            "keywords": "digital communications",
            "locationName": "Manchester",
            "distanceFromLocation": 25,
        },
        "charityjob_search": {
            "search": "communications digital",
            "location": "Manchester",
        },
        "sources": ["Adzuna", "Reed", "NHSJobs", "CharityJob", "ManchesterCC", "SalfordCC"],
        "boosts": {
            "accessibility": 4, "wcag": 4, "non-profit": 3, "charity": 3,
            "social enterprise": 3, "digital officer": 4, "communications": 2,
            "content": 2, "wordpress": 3, "website": 2, "community": 2,
            "marketing": 1, "third sector": 3,
        },
        "penalties": {
            "senior": -4, "head of": -5, "director": -5, "10 years": -4,
            "sales": -6, "recruitment": -6, "estate agent": -8,
        },
    },
    {
        "name": "Electrician Apprenticeships",
        "faa_search": {
            "WhatSearchTerm": "electrician",
            "WhereSearchTerm": "Manchester",
            "Distance": 40,
        },
        "adzuna": {
            "what": "electrician apprentice",
            "where": "Manchester",
            "max_days_old": 28,
        },
        "reed": {
            "keywords": "electrician apprentice",
            "locationName": "Manchester",
            "distanceFromLocation": 40,
        },
        "sources": ["FAA", "Adzuna"],
        "boosts": {
            "apprentice": 5, "apprenticeship": 5, "level 3": 3, "level 2": 2,
            "installation": 3, "electrotechnical": 3, "jib": 3, "trainee": 2,
        },
        "penalties": {
            "experienced": -5, "qualified": -4, "years": -3, "manager": -4,
            "approved electrician": -2, "diesel": -3, "gas engineer": -4,
        },
    },
]

# ------------------------------------------------------------------ HTTP helpers
def http_get(url, headers=None, retries=2, timeout=25):
    h = {"User-Agent": CONFIG["USER_AGENT"]}
    if headers:
        h.update(headers)
    last_err = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=h)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", "replace")
        except Exception as e:
            last_err = e
            if attempt < retries:
                time.sleep(2 * (attempt + 1))
    print(f"  !! fetch failed: {url[:80]}... ({last_err})", file=sys.stderr)
    return None

def strip_tags(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"\s+", " ", html.unescape(s)).strip()

# ------------------------------------------------------------------ Source: Find an Apprenticeship (GOV.UK)
def parse_faa_results(html_text):
    """Parse the FAA search-results page. Returns list of dicts."""
    items = re.findall(r'<li class="das-search-results__list-item.*?</li>', html_text, re.S)
    out = []
    for it in items:
        title_m = re.search(r'href="(/apprenticeship/[^"]+)"[^>]*>\s*<span[^>]*>(.*?)</span>', it, re.S)
        if not title_m:
            continue
        text = strip_tags(it)
        out.append({
            "source": "FindAnApprenticeship",
            "id": "FAA-" + title_m.group(1).split("/")[-1],
            "title": strip_tags(title_m.group(2)),
            "url": "https://www.findapprenticeship.service.gov.uk" + title_m.group(1),
            "org": _first_group(re.search(r'</strong>\s*</div>\s*<p class="govuk-body[^>]*>([^<]+)</p>', it)) or "",
            "location": _first_group(re.search(r'das-!-color-dark-grey">([^<]+)</p>', it)) or "",
            "details": text,
            "wage": _first_group(re.search(r'Wage\s+(?:&#163;|£|\u00a3)?\s*([^<\s][^<]*?)(?=\s+\w+\s+\w+\s*\(|\s+Closes|\s+Posted|$)', text)) or "",
        })
    return out

def _first_group(m):
    return m.group(1).strip() if m else None

def fetch_faa(profile):
    params = dict(profile["faa_search"])
    qs = urllib.parse.urlencode({k: v for k, v in params.items() if v})
    url = f"https://www.findapprenticeship.service.gov.uk/apprenticeshipsearch?search=1&{qs}"
    html_text = http_get(url)
    if not html_text:
        return []
    return parse_faa_results(html_text)[: CONFIG["MAX_PER_SOURCE"]]

# ------------------------------------------------------------------ Source: Adzuna
def fetch_adzuna(profile):
    if not CONFIG["ADZUNA_APP_ID"] or not CONFIG["ADZUNA_APP_KEY"]:
        print("  (Adzuna keys not set — skipping)", file=sys.stderr)
        return []
    q = profile["adzuna"]
    results, page = [], 1
    while page <= 2:  # up to 2 pages × 30 = 60 results
        url = ("https://api.adzuna.com/v1/api/jobs/gb/search/{p}"
               "?app_id={id}&app_key={key}&results_per_page=30"
               "&what={what}&where={where}&max_days_old={old}&sort_by=date"
               "&content-type=application/json").format(
            p=page,
            id=urllib.parse.quote(CONFIG["ADZUNA_APP_ID"]),
            key=urllib.parse.quote(CONFIG["ADZUNA_APP_KEY"]),
            what=urllib.parse.quote(q["what"]),
            where=urllib.parse.quote(q["where"]),
            old=q.get("max_days_old", 21),
        )
        raw = http_get(url)
        if not raw:
            break
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            break
        for r in data.get("results", []):
            results.append({
                "source": "Adzuna",
                "id": "ADZ-" + str(r.get("id", "")),
                "title": r.get("title", "").strip(),
                "org": r.get("company", {}).get("display_name", ""),
                "location": r.get("location", {}).get("display_name", "") if r.get("location") else "",
                "url": r.get("redirect_url", ""),
                "salary": _fmt_salary(r.get("salary_min"), r.get("salary_max")),
                "details": (r.get("description") or "")[:600],
                "posted": r.get("created", "")[:10],
            })
        if len(data.get("results", [])) < 30 or len(results) >= CONFIG["MAX_PER_SOURCE"]:
            break
        page += 1
    return results[: CONFIG["MAX_PER_SOURCE"]]

def _fmt_salary(lo, hi):
    if lo or hi:
        def f(v):
            return f"£{v:,.0f}" if isinstance(v, (int, float)) else "?"
        if lo and hi:
            return f"£{lo:,.0f}–{hi:,.0f}"
        return f(lo or hi)
    return ""

# ------------------------------------------------------------------ Source: Reed
def fetch_reed(profile):
    if not CONFIG["REED_API_KEY"]:
        print("  (Reed API key not set — skipping)", file=sys.stderr)
        return []
    q = profile["reed"]
    url = ("https://www.reed.co.uk/api/1.0/search?keywords={kw}&locationName={loc}"
           "&distanceFromLocation={dist}&resultsToTake=30").format(
        kw=urllib.parse.quote(q["keywords"]),
        loc=urllib.parse.quote(q["locationName"]),
        dist=q["distanceFromLocation"],
    )
    raw = http_get(url, headers={"Authorization": "Basic " + CONFIG["REED_API_KEY"] + ":"})
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    out = []
    for r in data.get("results", []):
        out.append({
            "source": "Reed",
            "id": "REED-" + str(r.get("jobId", "")),
            "title": r.get("jobTitle", ""),
            "org": r.get("employerName", ""),
            "location": r.get("locationName", ""),
            "url": r.get("jobUrl", ""),
            "salary": _fmt_salary(r.get("minimumSalary"), r.get("maximumSalary")),
            "details": (r.get("jobDescription") or "")[:600],
            "posted": r.get("date", "")[:10],
        })
    return out[: CONFIG["MAX_PER_SOURCE"]]

# ------------------------------------------------------------------ Source: NHS Jobs
def parse_nhs_results(html_text):
    """Parse NHS Jobs search results page into job dicts."""
    out = []
    blocks = re.split(r'<li class="nhsuk-list-panel search-result', html_text)[1:]
    for b in blocks:
        tm = re.search(r'href="(/candidate/jobadvert/[^"?]+)[^"]*"[^>]*>(.*?)</a>', b, re.S)
        if not tm:
            continue
        text = strip_tags(b)
        org_m = re.search(r'(?:staff group|employer)?\s*([A-Z][^<]{3,60})\s*<', b)
        org = _first_group(re.search(r'jobadvert[^>]*>.*?</a>\s*</h2>.*?<h3[^>]*>\s*([^<\n]{3,80}?)\s*(?:<|$)', b, re.S)) or ""
        loc = _first_group(re.search(r'<div class="location-font-size">\s*([^<]+?)\s*</div>', b, re.S)) or ""
        out.append({
            "source": "NHSJobs",
            "id": "NHS-" + tm.group(1).rsplit("/", 1)[-1],
            "title": strip_tags(tm.group(2)),
            "url": "https://www.jobs.nhs.uk" + tm.group(1),
            "org": org or "NHS",
            "location": loc,
            "salary": _first_group(re.search(r'Salary:\s*<[^>]*>[^£]*(£[^<]+)', b)) or "",
            "details": text[:600],
            "posted": _first_group(re.search(r'Date posted:\s*([\d\w ]+?)(?=\s+Contract|$)', text)) or "",
        })
    return out

def fetch_nhs(profile):
    url = ("https://www.jobs.nhs.uk/candidate/search/results?keyword={kw}&location={loc}&distance={d}"
           .format(kw=urllib.parse.quote(profile["faa_search"]["WhatSearchTerm"]),
                   loc=urllib.parse.quote(profile["faa_search"]["WhereSearchTerm"]),
                   d=profile["faa_search"].get("Distance", 20)))
    html_text = http_get(url)
    if not html_text:
        return []
    return parse_nhs_results(html_text)[: CONFIG["MAX_PER_SOURCE"]]

# ------------------------------------------------------------------ Source: CharityJob
def parse_charityjob_results(html_text):
    """Parse CharityJob job cards into job dicts."""
    out = []
    cards = re.findall(r'<article job-id="\d+".*?</article>', html_text, re.S)
    for c in cards:
        url_m = re.search(r'href="(https://www\.charityjob\.co\.uk/jobs/[^"\?]+)', c)
        if not url_m:
            continue
        lines = [html.unescape(l.strip()) for l in re.sub(r"<[^>]+>", "\n", c).split("\n") if l.strip()]
        # Prefer the title from the actual anchor text
        title = ""
        tm = re.search(r'href="' + re.escape(url_m.group(1)) + r'"[^>]*>([^<]+)', c)
        if tm:
            title = tm.group(1).strip()
        if not title:
            for l in lines[:6]:
                if l.lower() in ("top job", "featured") or l.startswith("Closing in"):
                    continue
                if l and not l.startswith("£"):
                    title = l
                    break
        # Org line = the "Name, Location" pair after the (possibly duplicated) title
        org_line = ""
        for i, l in enumerate(lines):
            if l == title:
                j = i + 1
                while j < len(lines) and lines[j] == title:
                    j += 1
                if j < len(lines):
                    org_line = lines[j]
                break
        salary_line = ""
        for l in lines:
            if l.startswith("£"):
                salary_line = l
                break
        # org_line usually "Org Name, Location"
        if org_line:
            parts = org_line.rsplit(",", 1)
            org = parts[0].strip()
            loc = parts[1].strip() if len(parts) > 1 else ""
        else:
            org, loc = "", ""
        out.append({
            "source": "CharityJob",
            "id": "CJ-" + url_m.group(1).rstrip("/").split("/")[-1],
            "title": title,
            "org": org.strip() or org_line,
            "location": loc.strip(),
            "salary": salary_line if "£" in salary_line or "per annum" in salary_line else "",
            "url": url_m.group(1),
            "details": next((l for l in lines if len(l) > 60 and not l.startswith("£")), "")[:400],
            "posted": _first_group(re.search(r'Posted ([\w\s]+ago)', c)) or "",
        })
    return out

def fetch_charityjob(profile):
    url = ("https://www.charityjob.co.uk/jobs?search={kw}&location={loc}"
           .format(kw=urllib.parse.quote(profile["charityjob_search"]["search"]),
                   loc=urllib.parse.quote(profile["charityjob_search"]["location"])))
    html_text = http_get(url)
    if not html_text:
        return []
    return parse_charityjob_results(html_text)[: CONFIG["MAX_PER_SOURCE"]]

# ------------------------------------------------------------------ Source: Manchester City Council
def parse_mcc_results(html_text):
    """Parse Manchester City Council vacancy list into job dicts."""
    out = []
    for u, t in re.findall(r'href="(\d+/[^"#]+\.html)"[^>]*>([^<]+)</a>', html_text):
        title = t.strip()
        if title.lower() == "more info":
            continue
        out.append({
            "source": "ManchesterCC",
            "id": "MCC-" + u.split("/")[0],
            "title": title,
            "org": "Manchester City Council",
            "location": "Manchester",
            "url": "https://jobs.manchester.gov.uk/vacancies/" + u,
            "details": "Manchester City Council vacancy",
            "posted": "",
        })
    return out

def fetch_mcc(profile):
    html_text = http_get("https://jobs.manchester.gov.uk/vacancies/vacancy-search-results.aspx")
    if not html_text:
        return []
    return parse_mcc_results(html_text)[: CONFIG["MAX_PER_SOURCE"]]

# ------------------------------------------------------------------ Source: Salford Council (greater.jobs)
def parse_salford_cards(html_text):
    """Parse Salford's _JobCard fragment into job dicts."""
    out = []
    cards = re.findall(r'<div tabindex="-1" class="card mb-7 mb-md-20 job-card.*?(?=<div tabindex="-1" class="card|$)',
                       html_text, re.S)
    for c in cards:
        href = _first_group(re.search(r'href="(/salford/Job/JobDetail\?JobId=\d+)"', c))
        if not href:
            continue
        title_m = re.search(r'<(?:h2|h3|a)[^>]*>([^<]{4,120})</', c)
        text = strip_tags(c)
        out.append({
            "source": "SalfordCC",
            "id": "SAL-" + href.split("JobId=")[-1],
            "title": title_m.group(1).strip() if title_m else "",
            "org": "Salford City Council",
            "location": "Salford",
            "url": "https://apply.greater.jobs" + href,
            "details": text[:400],
            "posted": "",
        })
    return out

def fetch_salford(profile):
    out = []
    for skip in (0, 12, 24, 36):  # 4 pages × 12 cards
        html_text = http_get("https://apply.greater.jobs/salford/Home/_JobCard?skip={}".format(skip))
        if not html_text:
            break
        out.extend(parse_salford_cards(html_text))
        if len(out) >= CONFIG["MAX_PER_SOURCE"]:
            break
    return out[: CONFIG["MAX_PER_SOURCE"]]

# ------------------------------------------------------------------ Scoring
def score_job(job, profile):
    blob = " ".join([job.get("title", ""), job.get("org", ""),
                     job.get("details", ""), job.get("wage", "")]).lower()
    score = 0
    for kw, pts in profile.get("boosts", {}).items():
        if kw.lower() in blob:
            score += pts
    for kw, pts in profile.get("penalties", {}).items():
        if kw.lower() in blob:
            score += pts  # penalties are negative
    if job.get("wage"):
        score += 1
    if "apprentice" in job.get("title", "").lower():
        score += 2
    return score

# ------------------------------------------------------------------ Dedupe + persistence
def load_seen(path):
    if os.path.exists(path):
        with open(path) as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                pass
    return {"seen": {}}

def save_seen(path, seen):
    # keep only the last 5000 entries
    if len(seen.get("seen", {})) > 5000:
        items = sorted(seen["seen"].items(), key=lambda kv: kv[1], reverse=True)
        seen["seen"] = dict(items[:5000])
    with open(path, "w") as f:
        json.dump(seen, f, indent=1)

# ------------------------------------------------------------------ Digest rendering
def render_digest(jobs_by_profile, seen_path):
    now = datetime.now(timezone.utc)
    lines = [
        "# Job Alerts",
        "",
        f"*Generated {now:%A %d %B %Y at %H:%M UTC} — auto-compiled by `job_alerts.py`*",
        "",
        "**Sources:** Find an Apprenticeship (GOV.UK), Adzuna, Reed",
        "",
    ]
    total_new = 0
    for prof_name, jobs in jobs_by_profile:
        new_jobs = [j for j in jobs if not j["seen_before"]]
        lines.append(f"## {prof_name} — {len(jobs)} matches ({len(new_jobs)} new)")
        lines.append("")
        if not jobs:
            lines.append("_No matches today._")
            lines.append("")
            continue
        for j in sorted(jobs, key=lambda x: -x["score"]):
            flag = " 🆕" if not j["seen_before"] else ""
            score_line = f"**Match: {j['score']}**"
            bits = [f"[{j['title']}]({j['url']}){flag}"]
            if j.get("org"):
                bits.append(j["org"])
            if j.get("location"):
                bits.append(j["location"])
            header = " — ".join(bits)
            lines.append(f"### {header}")
            lines.append("")
            meta = [f"Source: {j['source']}"]
            if j.get("wage"): meta.append(f"Wage: £{j['wage']}")
            if j.get("salary"): meta.append(f"Salary: {j['salary']}")
            if j.get("posted"): meta.append(f"Posted: {j['posted']}")
            lines.append(f"*{score_line} · " + " · ".join(meta) + "*")
            lines.append("")
            if j.get("details"):
                lines.append(f"> {j['details'][:400]}")
                lines.append("")
    return "\n".join(lines)

# ------------------------------------------------------------------ Main
def main():
    seen_path = os.path.join(CONFIG["OUT_DIR"], CONFIG["SEEN_FILE"])
    seen = load_seen(seen_path)
    all_results = []
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    for profile in PROFILES:
        print(f"== {profile['name']} ==")
        jobs = []
        fetchers = [fetch_faa, fetch_adzuna, fetch_reed]
        if "NHSJobs" in profile.get("sources", []):
            fetchers.append(fetch_nhs)
        if "CharityJob" in profile.get("sources", []):
            fetchers.append(fetch_charityjob)
        if "ManchesterCC" in profile.get("sources", []):
            fetchers.append(fetch_mcc)
        if "SalfordCC" in profile.get("sources", []):
            fetchers.append(fetch_salford)
        for fetcher in fetchers:
            try:
                jobs.extend(fetcher(profile) or [])
            except Exception as e:
                print(f"  !! {fetcher.__name__} failed: {e}", file=sys.stderr)
        for j in jobs:
            j["score"] = score_job(j, profile)
            key = j["id"]
            j["seen_before"] = key in seen.get("seen", {})
            seen.setdefault("seen", {})[key] = today
        scored = sorted([j for j in jobs if j["score"] >= CONFIG["MIN_SCORE_TO_SHOW"]],
                        key=lambda x: -x["score"])[:15]
        all_results.append((profile["name"], scored))

    save_seen(seen_path, seen)

    digest = render_digest(all_results, seen_path)
    fname = os.path.join(CONFIG["OUT_DIR"], f"Job Alerts - {today}.md")
    with open(fname, "w") as f:
        f.write(digest)
    print(f"\nWrote {fname}")
    # also print summary to stdout
    for name, jobs in all_results:
        new = sum(1 for j in jobs if not j["seen_before"])
        print(f"  {name}: {len(jobs)} shown ({new} new)")

if __name__ == "__main__":
    main()
