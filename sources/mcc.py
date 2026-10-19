import re
from core.models import Job
from sources.base import BaseSource
from utils.http import http_get
from utils.text import clean_html

class ManchesterCityCouncilSource(BaseSource):
    name = "ManchesterCC"

    def fetch(self, profile: dict, config: dict) -> list[Job]:
        # Example target listing page
        url = "https://jobs.manchester.gov.uk/search/"
        html = http_get(url)
        if not html:
            return []

        jobs: list[Job] = []
        # Target table row or card containers
        matches = re.findall(
            r'<tr class="job-row".*?href="(/job/(\d+))">(.*?)</a>.*?<td class="salary">(.*?)</td>', 
            html, 
            re.DOTALL
        )
        for link, job_id, title, salary in matches:
            jobs.append(Job(
                source=self.name,
                id=str(job_id),
                title=clean_html(title),
                url=f"https://jobs.manchester.gov.uk{link}",
                org="Manchester City Council",
                location="Manchester",
                wage=clean_html(salary),
                details=""
            ))
        return jobs
    