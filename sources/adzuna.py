import json
import os
import urllib.parse
from core.models import Job
from sources.base import BaseSource
from utils.http import http_get
from utils.text import clean_html

class AdzunaSource(BaseSource):
    name = "Adzuna"

    def fetch(self, profile: dict, config: dict) -> list[Job]:
        app_id = os.getenv("ADZUNA_APP_ID")
        app_key = os.getenv("ADZUNA_APP_KEY")
        if not app_id or not app_key:
            return []

        adzuna_cfg = profile.get("adzuna", {})
        what = adzuna_cfg.get("what", "")
        where = adzuna_cfg.get("where", "Manchester")

        params = {
            "app_id": app_id,
            "app_key": app_key,
            "what": what,
            "where": where,
            "results_per_page": config.get("max_per_source", 25),
            "content-type": "application/json"
        }
        url = f"https://api.adzuna.com/v1/api/jobs/gb/search/1?{urllib.parse.urlencode(params)}"
        
        raw_json = http_get(url)
        if not raw_json:
            return []

        try:
            payload = json.loads(raw_json)
        except json.JSONDecodeError:
            return []

        jobs: list[Job] = []
        for item in payload.get("results", []):
            # Defensive field extraction to avoid unpack runtime errors
            min_salary = item.get("salary_min")
            max_salary = item.get("salary_max")
            wage = "Undisclosed"
            if min_salary and max_salary:
                wage = f"£{min_salary:,.0f} - £{max_salary:,.0f}"
            elif min_salary:
                wage = f"From £{min_salary:,.0f}"

            jobs.append(Job(
                source=self.name,
                id=str(item.get("id")),
                title=clean_html(item.get("title", "")),
                url=item.get("redirect_url", ""),
                org=item.get("company", {}).get("display_name", "Unknown"),
                location=item.get("location", {}).get("display_name", where),
                wage=wage,
                closing=item.get("created", ""),
                details=clean_html(item.get("description", ""))
            ))
        return jobs