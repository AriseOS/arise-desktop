# Ami Cloud Backend - Docker Image
# Server-side AI analysis and data storage

FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt /app/

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire project (needed for imports from src/)
COPY . /app/

# Set Python path to include project root
ENV PYTHONPATH=/app

# Expose port
EXPOSE 9000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:9000/health')" || exit 1

# Run the application
CMD ["uvicorn", "src.cloud_backend.main:app", "--host", "0.0.0.0", "--port", "9000"]
