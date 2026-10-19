#!/usr/bin/env python3
"""Job Alerts Orchestrator. 

Zero internal business logic. Coordinates I/O, concurrency, and serialization.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import os
from pathlib import Path
import tomllib

from core.digest import render_digest
from core.models import Job
from core.scorer import score_job
from core.seen_store import SeenStore
from core.sync import sync_to_remote
from core.tracker import update_tracker
from sources import run_source

ROOT = Path(__file__).resolve().parent

def load_dotenv(path: Path = ROOT / ".env") -> None:
    """Minimal, standard library .env parser."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip())

def main() -> None:
    load_dotenv()

    # Load TOML configuration files using Python 3.11 stdlib
    with open(ROOT / "config" / "config.toml", "rb") as f:
        config = tomllib.load(f)
    with open(ROOT / "config" / "profiles.toml", "rb") as f:
        profiles_cfg = tomllib.load(f).get("profiles", {})

    seen_store = SeenStore(ROOT / config.get("database_path", "seen_jobs.db"))
    all_profile_results: list[tuple[str, list[Job]]] = []
    new_jobs_to_mark: list[Job] = []

    print("[*] Starting job discovery pipeline...")

    for profile_key, profile in profiles_cfg.items():
        profile_name = profile.get("name", profile_key)
        sources_to_run = profile.get("sources", [])
        print(f"\n[+] Processing Profile: {profile_name}")

        discovered_jobs: list[Job] = []

        # Run independent sources concurrently using ThreadPoolExecutor
        workers = min(len(sources_to_run), config.get("max_workers", 5)) or 1
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_src = {
                executor.submit(run_source, src_name, profile, config): src_name
                for src_name in sources_to_run
            }
            for future in as_completed(future_to_src):
                src_name = future_to_src[future]
                try:
                    results = future.result()
                    print(f"    -> [{src_name}] fetched {len(results)} listings")
                    discovered_jobs.extend(results)
                except Exception as e:
                    print(f"    -> [{src_name}] crashed: {e}")

        # Batch filter unseen jobs via SQLite
        unseen_jobs = seen_store.filter_unseen(discovered_jobs)
        print(f"    -> Filtered {len(discovered_jobs) - len(unseen_jobs)} already seen jobs")

        # Score and filter by minimum threshold
        scored_jobs: list[Job] = []
        for job in unseen_jobs:
            scored = score_job(job, profile)
            if scored.score >= config.get("min_score", 0):
                scored_jobs.append(scored)
                new_jobs_to_mark.append(scored)

        print(f"    -> {len(scored_jobs)} jobs met the score threshold")
        all_profile_results.append((profile_name, scored_jobs))

    # Persist all newly discovered matches to SQLite
    seen_store.mark_seen(new_jobs_to_mark)

    # Output Delivery Pipeline
    out_dir = ROOT / config.get("output_dir", "digests")
    out_dir.mkdir(exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    digest_path = out_dir / f"Job_Alerts_{today}.md"
    digest_path.write_text(render_digest(all_profile_results), encoding="utf-8")
    print(f"\n[✓] Digest written: {digest_path}")

    flat_list = [j for _, jobs in all_profile_results for j in jobs]
    tracker_path = ROOT / config.get("tracker_csv", "Job Tracker - Auto.csv")
    added_count = update_tracker(flat_list, tracker_path)
    print(f"[✓] Tracker updated: {tracker_path} (+{added_count} new entries)")

    # Isolated Cloud Sync
    sync_to_remote([digest_path, tracker_path], config)

if __name__ == "__main__":
    main()