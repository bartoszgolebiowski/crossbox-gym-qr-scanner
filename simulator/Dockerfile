FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install system build dependencies required for awsiotsdk / awscrt compilation if needed
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create certs directory target for dynamic volume mounts (read-only)
RUN mkdir -p /app/certs

# Copy source code and static web assets
COPY src/ ./src/
COPY static/ ./static/

# Expose Web API & UI Port
EXPOSE 8000

# Run simulator server
CMD ["python", "-m", "src.main"]
