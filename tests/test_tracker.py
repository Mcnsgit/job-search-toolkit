import csv
from core.models import Job
from core.tracker import update_tracker

def test_tracker_preserves_user_edits(tmp_path):
    csv_file = tmp_path / "tracker.csv"
    
    # 1. First run creates the row
    job1 = Job(source="FAA", id="101", title="Apprentice Dev", url="http://a")
    update_tracker([job1], csv_file)

    # 2. Simulate user editing "Status" and "Notes" in Excel
    rows = []
    with open(csv_file, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for r in reader:
            r["Status"] = "Interviewing"
            r["Notes"] = "Spoke with recruiter on phone"
            rows.append(r)

    with open(csv_file, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    # 3. Second run adds job2 while processing job1 again
    job2 = Job(source="FAA", id="102", title="Junior Dev", url="http://b")
    update_tracker([job1, job2], csv_file)

    # 4. Verify user edits on job1 were NOT overwritten
    final_rows = {}
    with open(csv_file, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            final_rows[r["CompositeKey"]] = r

    assert len(final_rows) == 2
    assert final_rows["FAA::101"]["Status"] == "Interviewing"
    assert final_rows["FAA::101"]["Notes"] == "Spoke with recruiter on phone"
    assert final_rows["FAA::102"]["Status"] == "New"