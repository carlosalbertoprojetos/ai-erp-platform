FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md /app/
COPY agents /app/agents
COPY apps /app/apps
COPY application /app/application
COPY domain /app/domain
COPY infrastructure /app/infrastructure
COPY shared /app/shared

RUN pip install --no-cache-dir .

EXPOSE 8000

CMD ["uvicorn", "apps.orchestrator.main:app", "--host", "0.0.0.0", "--port", "8000"]
