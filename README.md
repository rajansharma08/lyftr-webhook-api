# Lyftr Webhook API - Backend Assignment

FastAPI service for receiving WhatsApp-like messages with HMAC-SHA256 signature verification, SQLite database, and metrics.

**Assignment:** Lyftr AI Backend Assignment - Containerized Webhook API  
**Tech Stack:** Python 3.11+ | FastAPI | SQLite | Docker | Prometheus Metrics

---

## Table of Contents

1. [Features](#features)
2. [Project Structure](#project-structure)
3. [Setup & Installation](#setup--installation)
4. [Running the Service](#running-the-service)
5. [Testing](#testing)
6. [API Documentation](#api-documentation)
7. [Design Decisions](#design-decisions)
8. [Troubleshooting](#troubleshooting)

---

## Features

- HMAC-SHA256 signature verification
- Idempotent message ingestion (duplicate handling)
- REST API with pagination and filtering
- Prometheus metrics endpoint
- JSON structured logging
- Health check endpoints
- SQLite database with indexes
- Docker and Docker Compose support
- 20 unit tests passing
- Environment variable configuration

---

## Project Structure

```
lyftr-webhook-api/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app, routes, middleware
│   ├── models.py            # Pydantic schemas and validators
│   ├── storage.py           # SQLite database operations
│   ├── logging_utils.py     # JSON logger for structured logging
│   ├── metrics.py           # Prometheus metrics collector
│   └── config.py            # Environment configuration
├── tests/
│   ├── conftest.py          # Pytest fixtures for test database
│   ├── test_webhook.py      # Webhook endpoint tests
│   ├── test_messages.py     # Message listing & filtering tests
│   ├── test_stats.py        # Statistics endpoint tests
│   └── requirements.txt      # Test dependencies
├── Dockerfile               # Multi-stage Docker build
├── docker-compose.yml       # Docker Compose orchestration
├── Makefile                 # Convenience commands
├── requirements.txt         # Python dependencies
├── README.md                # This file
└── .gitignore              # Git ignore rules
```

---

## Setup & Installation

### Prerequisites

#### Windows
- Python 3.11+ ([Download](https://www.python.org/downloads/))
- Docker Desktop ([Download](https://www.docker.com/products/docker-desktop))
- Git ([Download](https://git-scm.com/download/win))

#### macOS
```bash
brew install python@3.11 docker
```

#### Linux (Ubuntu/Debian)
```bash
sudo apt-get update
sudo apt-get install python3.11 python3-pip docker.io docker-compose
```

### Clone & Install

```bash
# Clone repository
git clone https://github.com/YOUR_USERNAME/lyftr-webhook-api.git
cd lyftr-webhook-api

# Install dependencies
pip install -r requirements.txt
pip install -r tests/requirements.txt
```

---

## Running the Service

### Option 1: Docker Compose (Recommended - Cross-platform)

```bash
# Set environment variables
export WEBHOOK_SECRET="your-secret-key"
export DATABASE_URL="sqlite:////data/app.db"
export LOG_LEVEL="INFO"

# Start service
docker compose up -d --build

# Check logs
docker compose logs -f api

# Stop service
docker compose down -v
```

**Windows PowerShell:**
```powershell
$env:WEBHOOK_SECRET = "your-secret-key"
$env:DATABASE_URL = "sqlite:////data/app.db"
$env:LOG_LEVEL = "INFO"

docker compose up -d --build
docker compose logs -f api
docker compose down -v
```

### Option 2: Local Python (Linux/macOS)

```bash
# Set environment variables
export WEBHOOK_SECRET="testsecret"
export DATABASE_URL="sqlite:////tmp/app.db"
export LOG_LEVEL="INFO"

# Run directly
python app/main.py

# Or with uvicorn
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Option 3: Using Makefile (Linux/macOS)

```bash
# Start service
make up

# View logs
make logs

# Stop service
make down

# Run tests
make test
```

---

## Testing

### Run All Tests

```bash
# From project root
python -m pytest tests/ -v

# Or using Makefile
make test
```

**Expected Output:**
```
tests/test_webhook.py::test_webhook_valid_message PASSED
tests/test_webhook.py::test_webhook_duplicate_message PASSED
tests/test_webhook.py::test_webhook_invalid_signature PASSED
tests/test_messages.py::test_messages_basic_list PASSED
tests/test_messages.py::test_messages_pagination PASSED
tests/test_stats.py::test_stats_basic PASSED
...
===================== 20 passed in 1.77s =====================
```

### Manual Testing

#### 1. Health Checks

```bash
# Liveness probe
curl http://localhost:8000/health/live
# Response: {"status":"ok"}

# Readiness probe
curl http://localhost:8000/health/ready
# Response: {"status":"ready"}
```

#### 2. Webhook with Signature (Linux/macOS)

```bash
WEBHOOK_SECRET="testsecret"
BODY='{"message_id":"m1","from":"+919876543210","to":"+14155550100","ts":"2025-01-15T10:00:00Z","text":"Hello"}'
SIGNATURE=$(echo -n "$BODY" | openssl dgst -sha256 -hmac "$WEBHOOK_SECRET" | cut -d' ' -f2)

# Send valid message
curl -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -H "X-Signature: $SIGNATURE" \
  -d "$BODY"
# Response: {"status":"ok"}

# Send duplicate (should still return 200)
curl -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -H "X-Signature: $SIGNATURE" \
  -d "$BODY"
# Response: {"status":"ok"}

# Send with invalid signature (should return 401)
curl -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -H "X-Signature: invalidsig" \
  -d "$BODY"
# Response: {"detail":"invalid signature"}
```

#### 3. Webhook (Windows PowerShell)

```powershell
$WEBHOOK_SECRET = "testsecret"
$BODY = '{"message_id":"m1","from":"+919876543210","to":"+14155550100","ts":"2025-01-15T10:00:00Z","text":"Hello"}'

# Compute signature
$bytes = [System.Text.Encoding]::UTF8.GetBytes($BODY)
$hmac = New-Object System.Security.Cryptography.HMACSHA256
$hmac.Key = [System.Text.Encoding]::UTF8.GetBytes($WEBHOOK_SECRET)
$sig = ([System.BitConverter]::ToString($hmac.ComputeHash($bytes)) -replace '-', '').ToLower()

# Send request
$response = Invoke-WebRequest -Uri "http://localhost:8000/webhook" `
    -Method POST `
    -Headers @{"Content-Type"="application/json"; "X-Signature"=$sig} `
    -Body $BODY

$response.StatusCode  # 200
$response.Content     # {"status":"ok"}
```

#### 4. List Messages

```bash
curl http://localhost:8000/messages
# Response: {"data":[{"message_id":"m1","from":"+919876543210",...}],"total":1,"limit":50,"offset":0}

# With pagination
curl "http://localhost:8000/messages?limit=10&offset=0"

# With filter by sender
curl "http://localhost:8000/messages?from=%2B919876543210"

# With text search
curl "http://localhost:8000/messages?q=Hello"

# With timestamp filter
curl "http://localhost:8000/messages?since=2025-01-15T10:00:00Z"
```

#### 5. Get Statistics

```bash
curl http://localhost:8000/stats
# Response: {
#   "total_messages": 1,
#   "senders_count": 1,
#   "messages_per_sender": [{"from": "+919876543210", "count": 1}],
#   "first_message_ts": "2025-01-15T10:00:00Z",
#   "last_message_ts": "2025-01-15T10:00:00Z"
# }
```

#### 6. View Metrics

```bash
curl http://localhost:8000/metrics
# Response:
# # HELP http_requests_total Total HTTP requests
# # TYPE http_requests_total counter
# http_requests_total{path="/webhook",status="200"} 2
# http_requests_total{path="/webhook",status="401"} 1
# ...
```

---

## API Documentation

### POST /webhook

**Ingest a new message with HMAC signature verification**

**Request:**
```json
{
  "message_id": "m1",
  "from": "+919876543210",
  "to": "+14155550100",
  "ts": "2025-01-15T10:00:00Z",
  "text": "Hello"
}
```

**Headers:**
- `Content-Type: application/json`
- `X-Signature: <hex HMAC-SHA256 of raw request body>`

**Response (200 OK):**
```json
{"status": "ok"}
```

**Status Codes:**
- `200` - Message created or duplicate (idempotent)
- `401` - Invalid signature
- `422` - Validation error (invalid phone, timestamp, etc.)

---

### GET /messages

**List stored messages with pagination and filtering**

**Query Parameters:**
- `limit` (int, default: 50, min: 1, max: 100)
- `offset` (int, default: 0)
- `from` (string) - Filter by sender phone (E.164 format)
- `since` (string) - Filter by ISO-8601 timestamp
- `q` (string) - Full-text search in message text

**Response (200 OK):**
```json
{
  "data": [
    {
      "message_id": "m1",
      "from": "+919876543210",
      "to": "+14155550100",
      "ts": "2025-01-15T10:00:00Z",
      "text": "Hello"
    }
  ],
  "total": 1,
  "limit": 50,
  "offset": 0
}
```

---

### GET /stats

**Get message statistics**

**Response (200 OK):**
```json
{
  "total_messages": 123,
  "senders_count": 10,
  "messages_per_sender": [
    {"from": "+919876543210", "count": 50},
    {"from": "+911234567890", "count": 30}
  ],
  "first_message_ts": "2025-01-10T09:00:00Z",
  "last_message_ts": "2025-01-15T10:00:00Z"
}
```

---

### GET /health/live

**Kubernetes liveness probe**

**Response (200 OK):**
```json
{"status": "ok"}
```

---

### GET /health/ready

**Kubernetes readiness probe**

**Response (200 OK):**
```json
{"status": "ready"}
```

**Response (503 Service Unavailable):**
- Returns 503 if `WEBHOOK_SECRET` not set
- Returns 503 if database not ready

---

### GET /metrics

**Prometheus-compatible metrics endpoint**

**Response (200 OK):**
```
# HELP http_requests_total Total HTTP requests
# TYPE http_requests_total counter
http_requests_total{path="/webhook",status="200"} 15
http_requests_total{path="/webhook",status="401"} 2

# HELP webhook_requests_total Total webhook processing outcomes
# TYPE webhook_requests_total counter
webhook_requests_total{result="created"} 10
webhook_requests_total{result="duplicate"} 5
webhook_requests_total{result="invalid_signature"} 2

# HELP request_latency_ms Request latency in milliseconds
# TYPE request_latency_ms histogram
request_latency_ms_bucket{le="100"} 20
request_latency_ms_bucket{le="500"} 25
request_latency_ms_bucket{le="+Inf"} 25
request_latency_ms_count 25
```

---

## 🏗️ Design Decisions

### 1. HMAC-SHA256 Signature Verification

Implemented in `app/main.py`

- Uses `hmac.compare_digest()` for constant-time signature comparison
- Computes signature from raw request body bytes
- Returns 401 if signature is invalid
- Prevents unauthorized messages from being accepted

---

### 2. Idempotent Message Ingestion

Implemented in `app/main.py` and `app/storage.py`

- Database PRIMARY KEY on message_id prevents duplicates
- If a duplicate comes in, returns 200 OK without re-inserting
- Check if message exists before inserting
- Clients can safely retry failed requests without worry

---

### 3. Pagination

Implemented in `/messages` endpoint

- `limit` parameter controls number of results (default 50, max 100)
- `offset` parameter skips results to move to next page
- Response includes `total` count of all filtered messages
- Results ordered by timestamp for consistent ordering

---

### 4. Statistics Aggregation

Implemented in `/stats` endpoint

- Total message count
- Number of unique senders
- Top 10 senders by message count
- First and last message timestamps
- Uses SQL aggregation

---

### 5. Structured JSON Logging

Implemented in `app/logging_utils.py`

- Each log entry is valid JSON (one per line)
- Includes timestamp, level, request ID, method, path, status, latency
- Webhook logs include message ID, duplicate flag, and result
- Makes logs easy to parse and analyze

---

### 6. Prometheus Metrics

Implemented in `app/metrics.py`

- Counter for HTTP requests with endpoint and status labels
- Counter for webhook results (created vs duplicate vs error)
- Histogram for request latency with time buckets
- Exposed at `/metrics` endpoint

---

### 7. Database Schema

Implemented in `app/storage.py`

```sql
CREATE TABLE messages (
  message_id TEXT PRIMARY KEY,
  from_msisdn TEXT NOT NULL,
  to_msisdn TEXT NOT NULL,
  ts TEXT NOT NULL,
  text TEXT,
  created_at TEXT NOT NULL
);

CREATE INDEX idx_from_msisdn ON messages(from_msisdn);
CREATE INDEX idx_ts ON messages(ts);
```

- PRIMARY KEY prevents duplicate message IDs
- Indexes on phone number and timestamp for faster queries

---

## Environment Variables

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `WEBHOOK_SECRET` | - | ✅ Yes | Secret for HMAC signature (min 8 chars recommended) |
| `DATABASE_URL` | `sqlite:////data/app.db` | - | SQLite database path |
| `LOG_LEVEL` | `INFO` | - | Python logging level (DEBUG, INFO, WARNING, ERROR) |

**Example:**
```bash
export WEBHOOK_SECRET="mysecretkey"
export DATABASE_URL="sqlite:////tmp/webhook.db"
export LOG_LEVEL="DEBUG"
```

---

## Troubleshooting

### Port 8000 Already in Use

**Linux/macOS:**
```bash
lsof -i :8000
kill -9 <PID>
```

**Windows PowerShell:**
```powershell
netstat -ano | findstr :8000
taskkill /PID <PID> /F
```

### Database Permission Error

Ensure the database directory is writable:
```bash
mkdir -p /data
chmod 777 /data
```

### WEBHOOK_SECRET Not Set

The service starts but `/health/ready` returns 503:
```bash
export WEBHOOK_SECRET="your-secret"
```

### Tests Failing

Ensure dependencies are installed:
```bash
pip install -r requirements.txt -r tests/requirements.txt
python -m pytest tests/ -v
```

---

## Deployment

### Docker Image

```bash
docker build -t lyftr-webhook-api:latest .
docker run -d \
  -e WEBHOOK_SECRET="secret" \
  -e LOG_LEVEL="INFO" \
  -v webhook_data:/data \
  -p 8000:8000 \
  lyftr-webhook-api:latest
```

### Docker Compose

```bash
docker compose up -d
```

### Kubernetes

```bash
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
```

---

## Monitoring & Observability

### Prometheus Scrape Config

```yaml
scrape_configs:
  - job_name: 'webhook-api'
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: '/metrics'
    scrape_interval: 15s
```

### Example Queries

```promql
# Request rate per endpoint
rate(http_requests_total[5m]) by (path)

# Error rate
rate(http_requests_total{status=~"4..|5.."}[5m])

# P95 latency
histogram_quantile(0.95, request_latency_ms)

# Webhook success rate
webhook_requests_total{result="created"} / webhook_requests_total
```

---

## Tools & Libraries

- Python 3.11.2
- FastAPI 0.109.0
- Pydantic 2.5.3
- SQLite3
- Pytest 7.4.3
- Docker and Docker Compose

---

## Submission

Submitted for Lyftr AI Backend Assignment
