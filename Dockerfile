FROM python:3.11-slim

# Prevent Python from writing .pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies if required
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create certs directory target for dynamic volume mounts (read-only)
RUN mkdir -p /app/certs

# Copy source code only (certificates are injected dynamically via volumes)
COPY src/ ./src/

# Run the scanner engine as a module
CMD ["python", "-m", "src.main"]
