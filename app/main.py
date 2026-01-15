# Standard library imports for security, time, and UUID generation
import hmac  # HMAC for cryptographic signature verification
import hashlib  # Hash functions for computing signatures
import time  # Time measurement for latency tracking
import uuid  # UUID generation for request tracking
from datetime import datetime  # Timestamp handling
from typing import Optional  # Type hints for optional values
from contextlib import asynccontextmanager  # Context manager for lifecycle

# FastAPI framework imports for building REST API
from fastapi import FastAPI, Request, HTTPException, Query  # Core FastAPI components
from fastapi.responses import JSONResponse, PlainTextResponse  # Response types
# Pydantic for data validation and serialization
from pydantic import BaseModel, Field, field_validator  # Data models and validation
import uvicorn  # ASGI server for running FastAPI app

# Application-specific imports
from storage import DatabaseManager  # Database operations
from logging_utils import setup_logger, log_request  # Structured JSON logging
from metrics import MetricsCollector  # Prometheus metrics collection
from config import settings  # Configuration from environment variables
from models import WebhookMessage  # Pydantic model for webhook validation

# Initialize metrics collector and logger for the application
metrics = MetricsCollector()
logger = setup_logger()

# Application lifecycle context manager - handles startup and shutdown events
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown.
    
    This runs at startup before the app accepts requests,
    and at shutdown when the app is terminating.
    """
    # Startup: Initialize database and log application start
    db_manager.init_db()
    logger.info({"event": "startup", "message": "Application started"})
    yield
    # Shutdown: Log application shutdown
    logger.info({"event": "shutdown", "message": "Application shutting down"})


# Initialize FastAPI app with lifespan context manager
app = FastAPI(lifespan=lifespan)
# Initialize database manager with configured database URL
db_manager = DatabaseManager(settings.database_url)


# HTTP middleware to log requests and record metrics
@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    """Middleware that runs on every HTTP request.
    
    Responsibilities:
    - Generate unique request ID for tracking
    - Measure request latency
    - Record metrics (request count, latency)
    - Log all requests with structured JSON
    """
    # Generate unique ID for tracking this request throughout its lifecycle
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    
    # Record start time to calculate latency
    request.state.start_time = time.time()
    
    # Process the request (call next middleware/route handler)
    response = await call_next(request)
    
    # Calculate request latency in milliseconds
    latency_ms = (time.time() - request.state.start_time) * 1000
    
    # Record metrics for monitoring and observability
    metrics.record_request(
        path=request.url.path,
        method=request.method,
        status=response.status_code,
        latency_ms=latency_ms
    )
    
    # Build structured log data with request and response information
    log_data = {
        "ts": datetime.utcnow().isoformat() + "Z",
        "level": "INFO",
        "request_id": request_id,
        "method": request.method,
        "path": request.url.path,
        "status": response.status_code,
        "latency_ms": round(latency_ms, 2)
    }
    
    # Add any extra fields from the route (e.g., message_id, result)
    if hasattr(request.state, "log_extra"):
        log_data.update(request.state.log_extra)
    
    logger.info(log_data)
    
    return response


# Verify webhook signature using HMAC-SHA256 for security
def verify_signature(body: bytes, signature: str) -> bool:
    """Verify that the webhook request is from a trusted source.
    
    Uses HMAC-SHA256 with a shared secret key. This ensures:
    - Only legitimate clients can send webhooks
    - Messages haven't been tampered with
    
    Uses constant-time comparison to prevent timing attacks
    where an attacker could guess the signature by measuring response time.
    
    Args:
        body: Raw request body bytes (not decoded JSON)
        signature: Hex string signature from X-Signature header
        
    Returns:
        True if signature is valid, False otherwise
    """
    # Return False if webhook secret is not configured
    if not settings.webhook_secret:
        return False
    
    # Generate expected signature from webhook secret and request body
    # Must compute from raw bytes to match what client sent
    expected = hmac.new(
        settings.webhook_secret.encode(),  # Convert secret string to bytes
        body,  # Raw request body bytes
        hashlib.sha256  # Use SHA256 hash algorithm
    ).hexdigest()  # Convert to hex string for comparison
    
    # Compare signatures using constant-time comparison to prevent timing attacks
    # This prevents attackers from using timing information to guess the signature
    return hmac.compare_digest(expected, signature)


# Webhook endpoint to receive and process incoming messages
@app.post("/webhook")
async def webhook(request: Request):
    """Process incoming webhook message with signature verification.
    
    Flow:
    1. Read raw request body
    2. Verify HMAC signature for authenticity
    3. Parse and validate message JSON
    4. Check for duplicates (idempotency)
    5. Insert into database if new
    6. Return 200 OK (always, even for duplicates)
    
    Returns:
        200 OK if successful (message created or was duplicate)
        401 if signature invalid
        422 if message validation failed
    """
    # Read the raw request body (needed for signature verification)
    body = await request.body()
    
    # Extract signature from X-Signature header
    signature = request.headers.get("X-Signature", "")
    
    # Verify webhook signature for security
    if not verify_signature(body, signature):
        # Invalid signature - reject this request as unauthorized
        metrics.record_webhook("invalid_signature")
        request.state.log_extra = {"result": "invalid_signature"}
        logger.error({
            "event": "invalid_signature",
            "request_id": request.state.request_id
        })
        # Return 401 Unauthorized
        raise HTTPException(status_code=401, detail="invalid signature")
    
    # Parse and validate the webhook message using Pydantic
    try:
        message = WebhookMessage.model_validate_json(body)
    except Exception as e:
        # Validation error - message format is incorrect
        metrics.record_webhook("validation_error")
        request.state.log_extra = {"result": "validation_error"}
        # Return 422 Unprocessable Entity
        raise HTTPException(status_code=422, detail=str(e))
    
    # Check if message already exists (duplicate detection for idempotency)
    # Allows clients to safely retry failed requests
    is_duplicate = db_manager.message_exists(message.message_id)
    
    # Only insert message if it's not a duplicate
    if not is_duplicate:
        # Insert new message into database
        db_manager.insert_message(
            message_id=message.message_id,
            from_msisdn=message.from_,  # Note: message.from_ maps to JSON "from"
            to_msisdn=message.to,
            ts=message.ts,
            text=message.text
        )
        # Record metric: message was successfully created
        metrics.record_webhook("created")
        result = "created"
    else:
        # Duplicate message - don't insert but still return success
        # This allows clients to retry without seeing errors
        metrics.record_webhook("duplicate")
        result = "duplicate"
    
    # Add result information to the log
    request.state.log_extra = {
        "message_id": message.message_id,
        "dup": is_duplicate,  # Boolean: was this a duplicate?
        "result": result  # String: created or duplicate
    }
    
    # Always return 200 OK for idempotency
    # Clients can safely retry the same request multiple times
    return {"status": "ok"}


# Retrieve messages with optional filtering and pagination
@app.get("/messages")
async def get_messages(
    # Limit: how many results per page (must be 1-100)
    limit: int = Query(50, ge=1, le=100),
    # Offset: how many results to skip (for pagination)
    offset: int = Query(0, ge=0),
    # Filter by sender phone number (optional, exact match)
    from_: Optional[str] = Query(None, alias="from"),
    # Filter messages since this timestamp (optional, ISO-8601 format)
    since: Optional[str] = None,
    # Full-text search in message text (optional)
    q: Optional[str] = None
):
    """Retrieve messages with pagination and optional filtering.
    
    Supports filtering by:
    - from: sender phone number (exact match)
    - since: timestamp (returns messages >= this time)
    - q: full-text search in message content
    
    Always returns:
    - data: array of messages
    - total: count of ALL messages matching filters (not just returned)
    - limit: the limit parameter used
    - offset: the offset parameter used
    
    This allows pagination UI to know total available results.
    """
    # Fetch messages from database with applied filters
    messages, total = db_manager.get_messages(
        limit=limit,
        offset=offset,
        from_filter=from_,
        since=since,
        text_search=q
    )
    
    # Return paginated results with total count
    return {
        "data": messages,
        "total": total,  # Total matching filters, not just returned count
        "limit": limit,
        "offset": offset
    }


# Retrieve statistics about stored messages
@app.get("/stats")
async def get_stats():
    """Get aggregated statistics about all stored messages.
    
    Returns:
    - total_messages: count of all messages
    - senders_count: count of unique sender phone numbers
    - messages_per_sender: top 10 senders by count
    - first_message_ts: timestamp of oldest message
    - last_message_ts: timestamp of newest message
    """
    # Fetch statistics from database
    stats = db_manager.get_stats()
    return stats


# Liveness probe - indicates if the service is running
@app.get("/health/live")
async def health_live():
    """Kubernetes liveness probe.
    
    Returns 200 OK if the service is running.
    If this returns non-200, Kubernetes will restart the pod.
    
    Always succeeds since we only check if the service is running.
    """
    return {"status": "ok"}


# Readiness probe - indicates if the service is ready to accept traffic
@app.get("/health/ready")
async def health_ready():
    """Kubernetes readiness probe.
    
    Returns 200 OK only if the service is ready to accept traffic.
    If this returns non-200, traffic is not routed to this pod.
    
    Checks:
    - WEBHOOK_SECRET is configured (required for security)
    - Database is initialized and accessible
    
    Returns 503 Service Unavailable if any check fails.
    """
    # Check if webhook secret is configured
    if not settings.webhook_secret:
        raise HTTPException(status_code=503, detail="WEBHOOK_SECRET not set")
    
    # Check if database is ready and accessible
    if not db_manager.check_db_ready():
        raise HTTPException(status_code=503, detail="Database not ready")
    
    # All checks passed - service is ready
    return {"status": "ready"}


# Export metrics in Prometheus format for monitoring
@app.get("/metrics", response_class=PlainTextResponse)
async def get_metrics():
    """Export collected metrics in Prometheus text format.
    
    Returns metrics that can be scraped by Prometheus monitoring system.
    
    Includes:
    - HTTP request counts by endpoint and status
    - Webhook processing outcomes
    - Request latency distribution
    
    Prometheus scrapes this endpoint periodically (e.g., every 15 seconds)
    and stores the time series data for monitoring and alerting.
    """
    # Export collected metrics in text format
    return metrics.export()


# Run the application with Uvicorn server
if __name__ == "__main__":
    # Start the ASGI server
    # - host="0.0.0.0" allows connections from any IP
    # - port=8000 is the default port for the API
    uvicorn.run(app, host="0.0.0.0", port=8000)