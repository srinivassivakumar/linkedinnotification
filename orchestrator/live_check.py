from __future__ import annotations

import requests


def live_status(url: str, enabled: bool = False, timeout_seconds: int = 8) -> str:
    if not enabled:
        return "unknown"
    try:
        response = requests.head(url, timeout=timeout_seconds, allow_redirects=True)
        if response.status_code in {405, 403}:
            response = requests.get(url, timeout=timeout_seconds, allow_redirects=True)
        if response.status_code in {404, 410}:
            return "dead"
        if 200 <= response.status_code < 500:
            return "live"
        return "unknown"
    except requests.RequestException:
        return "unknown"

