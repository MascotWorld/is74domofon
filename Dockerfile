FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ ./src/
COPY run_api.py .
COPY static/ ./static/

# Create config directory
RUN mkdir -p /app/config

# Expose port
EXPOSE 10777

# Set environment variables
ENV LOG_LEVEL=info
ENV PYTHONUNBUFFERED=1

# Run the API server
CMD ["python", "run_api.py"]

