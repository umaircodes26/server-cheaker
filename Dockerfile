FROM python:3.11-slim

# Install system dependencies (curl, docker cli tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Expose Web Dashboard port
EXPOSE 8000

ENV HOST=0.0.0.0
ENV PORT=8000

CMD ["python", "run.py"]

