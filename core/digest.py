from datetime import datetime, timezone
from core.models import Job

def render_digest(profile_results: list[tuple[str, list[Job]]]) -> str:
    """Generates clean, human-readable Markdown digest."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"# Daily Job Digest — {now}\n"]

    total_jobs = sum(len(jobs) for _, jobs in profile_results)
    if total_jobs == 0:
        lines.append("_No new matching roles discovered today._")
        return "\n".join(lines)

    for profile_name, jobs in profile_results:
        lines.append(f"## Profile: {profile_name} ({len(jobs)} matches)")
        if not jobs:
            lines.append("_No matching listings above threshold._\n")
            continue

        # Sort highest score first
        sorted_jobs = sorted(jobs, key=lambda j: j.score, reverse=True)
        for job in sorted_jobs:
            lines.append(f"### [{job.title}]({job.url})")
            lines.append(f"- **Company:** {job.org} | **Location:** {job.location}")
            lines.append(f"- **Wage:** {job.wage} | **Score:** `{job.score}` ({', '.join(job.matched_keywords)})")
            lines.append(f"- **Source:** `{job.source}` | **Closing:** {job.closing or 'N/A'}")
            if job.details:
                excerpt = job.details[:180].strip() + ("..." if len(job.details) > 180 else "")
                lines.append(f"> {excerpt}")
            lines.append("")

    return "\n".join(lines)