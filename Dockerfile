FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

# Create persistent data directory for SQLite DB and enriched CSVs
# Mount this as a volume in Railway/Docker to survive container restarts
RUN mkdir -p /app/data

EXPOSE 8000

# VOLUME declaration tells container runtimes this path should be mounted
VOLUME ["/app/data"]

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
