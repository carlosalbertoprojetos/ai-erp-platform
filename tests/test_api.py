from __future__ import annotations

from fastapi.testclient import TestClient

from apps.orchestrator.main import app, get_dispatcher, get_repository, get_settings

AUTH_HEADER = {"Authorization": f"Bearer {get_settings().api_token}"}


def test_healthcheck_endpoint():
    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.headers["traceparent"]


def test_readiness_endpoint():
    client = TestClient(app)
    response = client.get("/ready")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["database"] == "ok"
    assert "dispatcher" in payload


def test_metrics_prometheus_endpoint():
    client = TestClient(app)
    response = client.get("/metrics/prometheus", headers=AUTH_HEADER)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "coreflow_http_requests_total" in response.text or response.text == ""


def test_run_endpoint_requires_auth(tmp_path):
    client = TestClient(app)
    response = client.post(
        "/run",
        json={
            "request": {
                "title": "Catalog",
                "description": "Create a product catalog service.",
                "module_name": "catalog",
                "entities": ["Product"],
                "capabilities": ["create_product", "list_products"]
            },
            "target_root": str(tmp_path),
            "dry_run": True,
            "provider": "template"
        },
    )

    assert response.status_code == 401


def test_run_endpoint_dry_run(tmp_path):
    client = TestClient(app)
    response = client.post(
        "/run",
        headers=AUTH_HEADER,
        json={
            "request": {
                "title": "Catalog",
                "description": "Create a product catalog service.",
                "module_name": "catalog",
                "entities": ["Product"],
                "capabilities": ["create_product", "list_products"]
            },
            "target_root": str(tmp_path),
            "dry_run": True,
            "provider": "template"
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert "architect" in payload["results"]
    assert payload["results"]["security"]["payload"]["security_report"]["status"] == "passed"


def test_async_run_endpoint_returns_correlation_id_and_status(tmp_path):
    client = TestClient(app)
    response = client.post(
        "/run/async",
        headers=AUTH_HEADER,
        json={
            "request": {
                "title": "Async Catalog",
                "description": "Create a product catalog service asynchronously.",
                "module_name": "catalog_async",
                "entities": ["Product"],
                "capabilities": ["create_product", "list_products"]
            },
            "target_root": str(tmp_path),
            "dry_run": True,
            "provider": "template"
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["correlation_id"]
    assert payload["status"] == "queued"

    status_response = client.get(f"/executions/{payload['correlation_id']}", headers=AUTH_HEADER)
    assert status_response.status_code == 200
    assert status_response.json()["status"] in {"queued", "running", "success"}
