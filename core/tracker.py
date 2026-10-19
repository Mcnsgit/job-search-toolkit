import csv
from pathlib import Path
from core.models import Job

# Preserves any custom columns manually edited by the user in Excel/Numbers/Sheets
DEFAULT_HEADERS = [
    "CompositeKey", "Source", "Title", "Organisation", 
    "Location", "Wage", "Score", "Keywords", "URL", 
    "Status", "Notes", "AppliedDate"
]

def update_tracker(jobs: list[Job], tracker_path: Path) -> int:
    """Appends unseen jobs to a CSV ledger while preserving existing user annotations."""
    if not jobs:
        return 0

    existing_rows: dict[str, dict[str, str]] = {}
    fieldnames = list(DEFAULT_HEADERS)

    if tracker_path.exists():
        with open(tracker_path, mode="r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames:
                fieldnames = reader.fieldnames
            for row in reader:
                key = row.get("CompositeKey")
                if key:
                    existing_rows[key] = row

    new_count = 0
    for job in jobs:
        if job.composite_key not in existing_rows:
            new_row = {field: "" for field in fieldnames}
            new_row.update({
                "CompositeKey": job.composite_key,
                "Source": job.source,
                "Title": job.title,
                "Organisation": job.org,
                "Location": job.location,
                "Wage": job.wage,
                "Score": str(job.score),
                "Keywords": ", ".join(job.matched_keywords),
                "URL": job.url,
                "Status": "New",
                "Notes": "",
                "AppliedDate": ""
            })
            existing_rows[job.composite_key] = new_row
            new_count += 1

    temp_path = tracker_path.with_suffix(".tmp")
    with open(temp_path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(existing_rows.values())

    temp_path.replace(tracker_path)  # Atomic rename
    return new_count