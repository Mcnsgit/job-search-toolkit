import time
import urllib.request
import urllib.error
from typing import Optional

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36 JobAlertsBot/2.0"
)

def http_get(
    url: str,
    headers: Optional[dict[str, str]] = None,
    retries: int = 3,
    backoff_factor: float = 1.5,
    timeout: int = 12
) -> Optional[str]:
    """Robust, stdlib-only HTTP client with headers, retries, and exponential backoff."""
    req_headers = {"User-Agent": DEFAULT_USER_AGENT, "Accept": "*/*"}
    if headers:
        req_headers.update(headers)

    req = urllib.request.Request(url, headers=req_headers)

    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                return response.read().decode(charset, errors="replace")
        except urllib.error.HTTPError as e:
            if 400 <= e.code < 500 and e.code != 429:
                # Client errors (404, 403) should not be retried
                return None
            sleep_time = backoff_factor ** attempt
            time.sleep(sleep_time)
        except (urllib.error.URLError, TimeoutError):
            sleep_time = backoff_factor ** attempt
            time.sleep(sleep_time)
        except Exception:
            return None
    return None