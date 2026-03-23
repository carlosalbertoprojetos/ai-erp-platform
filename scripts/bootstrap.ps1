$ErrorActionPreference = "Stop"

Write-Host "Running test suite..."
py -3 -m pytest

Write-Host "Starting docker stack..."
docker compose up --build -d

Write-Host "Waiting for readiness..."
Start-Sleep -Seconds 5

Write-Host "Running smoke test..."
py -3 scripts/smoke_test.py

Write-Host "CoreFlow bootstrap completed."
