from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request


BASE_URL = os.getenv("COREFLOW_BASE_URL", "http://localhost:8000")
API_TOKEN = os.getenv("COREFLOW_API_TOKEN", "local-token")


def request(method: str, path: str, payload: dict | None = None) -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url=f"{BASE_URL}{path}",
        data=data,
        method=method,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_TOKEN}",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    ready = request("GET", "/ready")
    if ready["status"] != "ok":
        raise SystemExit(f"Readiness failed: {ready}")

    payload = {
        "request": {
            "title": "Smoke Catalog",
            "description": "Validate the deployed CoreFlow stack.",
            "module_name": "smoke_catalog",
            "entities": ["Product"],
            "capabilities": ["create_product", "list_products"],
        },
        "target_root": "generated",
        "dry_run": True,
        "provider": "template",
    }
    queued = request("POST", "/run/async", payload)
    correlation_id = queued["correlation_id"]

    for _ in range(30):
        status_payload = request("GET", f"/executions/{correlation_id}")
        if status_payload["status"] in {"success", "error", "failed", "completed"}:
            break
        time.sleep(1)
    else:
        raise SystemExit(f"Execution did not complete in time: {correlation_id}")

    final_status = request("GET", f"/executions/{correlation_id}")
    if final_status["status"] not in {"success", "completed"}:
        raise SystemExit(f"Smoke test failed: {final_status}")

    print("Smoke test passed.")


if __name__ == "__main__":
    try:
        main()
    except urllib.error.URLError as exc:
        raise SystemExit(f"Unable to reach CoreFlow API: {exc}") from exc
