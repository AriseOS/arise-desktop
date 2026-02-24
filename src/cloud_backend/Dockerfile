# Ami Cloud Backend - Multi-stage Docker Image
# Memory-as-a-Service + Auth proxy (no local database)

# ===== Stage 1: Dependencies =====
FROM python:3.12-slim AS deps

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml /app/
RUN pip install --no-cache-dir ".[all]"

# ===== Stage 2: Runtime =====
FROM python:3.12-slim

WORKDIR /app

# Copy installed packages from deps stage
COPY --from=deps /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin

# Copy project source
COPY . /app/

# Python path: project root for imports like `from src.common.memory...`
ENV PYTHONPATH=/app

# Non-root user
RUN groupadd -r ami && useradd -r -g ami -d /app ami && \
    mkdir -p /app/data && chown -R ami:ami /app
USER ami

EXPOSE 9090

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:9090/health')" || exit 1

# Run from cloud_backend directory (imports: from core.config_service, from api.auth, etc.)
CMD ["python", "-m", "uvicorn", "src.cloud_backend.main:app", "--host", "0.0.0.0", "--port", "9090"]
