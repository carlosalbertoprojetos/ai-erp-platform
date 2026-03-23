from __future__ import annotations

import argparse
import sys
import time
import urllib.error
import urllib.request


def wait_for_url(url: str, timeout_seconds: int, interval_seconds: int) -> int:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                if response.status == 200:
                    return 0
        except (urllib.error.URLError, TimeoutError, OSError):
            pass
        time.sleep(interval_seconds)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Wait for CoreFlow HTTP endpoint.")
    parser.add_argument("--url", required=True)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--interval", type=int, default=2)
    args = parser.parse_args()
    return wait_for_url(args.url, args.timeout, args.interval)


if __name__ == "__main__":
    sys.exit(main())
