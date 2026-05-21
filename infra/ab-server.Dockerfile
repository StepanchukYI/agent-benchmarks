FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends git curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /app

COPY pyproject.toml ./
COPY uv.lock* ./
COPY packages ./packages

RUN uv sync --frozen --all-packages || uv sync --all-packages

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "ab_server.main:app", "--host", "0.0.0.0", "--port", "8000"]
