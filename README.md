# CoreFlow Agents

CoreFlow Agents is a production-hardened multi-agent engineering platform with:

- FastAPI orchestrator
- pluggable agents
- structured LLM layer
- sync and async execution
- Redis-backed queue worker
- Postgres execution persistence
- JSON observability artifacts
- control plane admin UI

## Architecture

- `domain/`: business models and architecture design rules
- `application/`: orchestration, ports, dispatcher, settings
- `infrastructure/`: persistence, scanners, git integration
- `apps/orchestrator/`: HTTP API
- `apps/worker/`: Redis queue worker
- `apps/control_plane_ui/`: control plane SPA
- `agents/`: plug-and-play agent implementations

## Quick Start

1. Copy `.env.example` to `.env` and adjust values.
2. Start the stack:

```bash
docker compose up --build
```

3. Verify readiness:

```bash
curl http://localhost:8000/ready
```

4. Open the control plane:

```text
http://localhost:8000/admin/
```

5. Sign in with:

```text
username: admin
password: admin123
```

6. Run the smoke test:

```bash
py -3 scripts/smoke_test.py
```

## API

Use header:

```text
Authorization: Bearer <COREFLOW_API_TOKEN or issued access token>
```

Endpoints:

- `GET /health`
- `GET /ready`
- `GET /admin/`
- `POST /api/control-plane/auth/login`
- `GET /api/control-plane/auth/session`
- `GET /api/control-plane/dashboard`
- `GET /api/control-plane/plans`
- `GET /api/control-plane/tenants`
- `POST /api/control-plane/tenants`
- `PATCH /api/control-plane/tenants/{tenant_id}/plan`
- `GET /api/control-plane/billing`
- `GET /api/control-plane/system-health`
- `GET /api/control-plane/users`
- `GET /api/control-plane/roles`
- `GET /api/control-plane/modules`
- `POST /run`
- `POST /run/async`
- `GET /executions/{correlation_id}`

## Example Flows

### Create tenant
1. Sign in at `/admin/`
2. Open `Tenants`
3. Fill the tenant onboarding form
4. Submit to create a real tenant record, subscription and invoice

### Assign plan
1. Open a tenant detail in `Tenants`
2. Go to the `Billing` tab
3. Select a new plan and apply it
4. The system creates a new subscription state and invoice dynamically

### View billing
1. Open `Billing`
2. Filter subscriptions and invoices by status
3. Review the updated ledger after plan changes

## Local Validation

```bash
py -3 -m pytest
```

## Deployment Checklist

- Provide real secrets for `COREFLOW_API_TOKEN`, `COREFLOW_ADMIN_PASSWORD`, `COREFLOW_AUTH_SECRET` and `OPENAI_API_KEY`.
- Point `DATABASE_URL` to managed Postgres.
- Point `REDIS_URL` to managed Redis.
- Keep `COREFLOW_ASYNC_BACKEND=redis` in deployed environments.
- Run at least one worker replica.
- Expose only the orchestrator service publicly.
- Keep `/ready` behind internal network or trusted monitoring.
- Configure centralized log shipping for `.coreflow/logs`.
- Enable TLS and ingress authentication at the platform edge.
- Add container restart policies and resource limits in deployment manifests.

## Operational Notes

- `template` provider keeps the system runnable without OpenAI credentials.
- `openai` provider requires `OPENAI_API_KEY`.
- Async jobs are persisted as `queued` before worker execution starts.
- Worker failures are reflected in execution status.
- The control plane seeds a bootstrap dataset for local/admin validation when the database is empty.
