# Deployment Checklist

## Required

- Set `COREFLOW_API_TOKEN` to a non-default secret.
- Set `OPENAI_API_KEY` if using `COREFLOW_LLM_PROVIDER=openai`.
- Use managed Postgres and managed Redis in non-local environments.
- Keep `COREFLOW_ASYNC_BACKEND=redis`.
- Run at least one `worker` instance for async processing.

## Before Release

- `py -3 -m pytest`
- `docker compose up --build`
- `GET /ready` returns `status=ok`
- `POST /run` succeeds with bearer auth
- `POST /run/async` returns a correlation id
- `GET /executions/{correlation_id}` reaches a terminal status

## Security

- Do not expose Redis publicly.
- Restrict Postgres to private network access.
- Put the orchestrator behind TLS termination.
- Rotate API and provider credentials.
- Keep `.env` out of version control.

## Reliability

- Enable restart policies in your runtime platform.
- Add CPU and memory limits.
- Configure log aggregation.
- Monitor queue depth, readiness, worker crashes, and database health.
