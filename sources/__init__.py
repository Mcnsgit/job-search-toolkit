import importlib
import pkgutil
import sys
from pathlib import Path
from core.models import Job
from sources.base import BaseSource

# Dynamically import all modules in this package to execute __init_subclass__
_package_dir = Path(__file__).parent
for _, module_name, _ in pkgutil.iter_modules([str(_package_dir)]):
    if module_name != "base":
        importlib.import_module(f"sources.{module_name}")

def run_source(name: str, profile: dict, config: dict) -> list[Job]:
    """Crash-isolated execution of an individual source adapter."""
    source_cls = BaseSource.registry.get(name)
    if not source_cls:
        print(f"[-] Source '{name}' requested in profile but not found in registry.", file=sys.stderr)
        return []

    try:
        instance = source_cls()
        jobs = instance.fetch(profile, config)
        max_allowed = config.get("max_per_source", 50)
        return jobs[:max_allowed]
    except Exception as e:
        # Fault isolation: Never allow a single failing scraper to break the batch
        print(f"[!] Source '{name}' failed with exception: {e}", file=sys.stderr)
        return []