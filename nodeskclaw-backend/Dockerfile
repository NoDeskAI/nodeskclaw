FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY nodeskclaw-backend/pyproject.toml nodeskclaw-backend/uv.lock ./
RUN uv sync --frozen --no-dev

COPY nodeskclaw-backend/ .
COPY openclaw-channel-nodeskclaw/ ./openclaw-channel-nodeskclaw/

RUN mkdir -p /app/data

EXPOSE 8000

CMD [".venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
