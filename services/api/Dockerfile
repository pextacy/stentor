# Build from the repo root:  docker build -f services/api/Dockerfile -t stentor-api .
FROM python:3.11-slim
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv
WORKDIR /app/services/api
COPY services/api/pyproject.toml services/api/uv.lock services/api/.python-version ./
RUN uv sync --frozen --no-dev --no-install-project
COPY services/api/stentor ./stentor
COPY eval /app/eval
ENV PORT=8000 STENTOR_DB_URL=sqlite:////tmp/stentor.db
EXPOSE 8000
CMD ["sh", "-c", "uv run --no-dev uvicorn stentor.main:app --host 0.0.0.0 --port ${PORT}"]
