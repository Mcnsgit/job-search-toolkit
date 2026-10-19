import subprocess
import sys
from pathlib import Path

def sync_to_remote(files: list[Path], config: dict) -> None:
    """Pushes artifacts to remote storage using rclone. Isolated and non-blocking."""
    if not config.get("enable_sync"):
        return

    remote = config.get("sync_remote")
    if not remote:
        print("[sync] Remote destination not configured. Skipping.", file=sys.stderr)
        return

    for file_path in files:
        if not file_path.exists():
            continue
        try:
            cmd = ["rclone", "copy", str(file_path), remote]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if res.returncode == 0:
                print(f"[sync] Successfully uploaded {file_path.name} to {remote}")
            else:
                print(f"[sync] Error uploading {file_path.name}: {res.stderr.strip()}", file=sys.stderr)
        except Exception as e:
            print(f"[sync] Failed to execute rclone: {e}", file=sys.stderr)