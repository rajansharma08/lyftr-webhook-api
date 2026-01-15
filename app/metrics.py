"""Prometheus metrics collection module.

This module collects metrics for monitoring and observability.
Metrics are exposed at the /metrics endpoint in Prometheus text format.

Collected metrics:
1. http_requests_total: Counter of total HTTP requests with path and status
2. webhook_requests_total: Counter of webhook outcomes (created, duplicate, error)
3. request_latency_ms: Histogram of request latencies with time buckets

These metrics can be scraped by Prometheus for alerting and dashboards.
"""

from collections import defaultdict
from threading import Lock
from typing import Dict, List


class MetricsCollector:
    """Thread-safe metrics collector for application monitoring.
    
    Collects three types of metrics:
    - Counters: Track cumulative values
    - Histograms: Track distribution of values (latency)
    
    All methods are thread-safe using locks for concurrent access.
    """
    
    def __init__(self):
        """Initialize metrics collector with empty metrics."""
        # Lock for thread-safe access to metrics
        self.lock = Lock()
        
        # Counter: {path,status} -> count
        # Example: path="/webhook",status="200" -> 10
        self.http_requests = defaultdict(int)
        
        # Counter: {result} -> count
        # Results can be: created, duplicate, invalid_signature, validation_error
        self.webhook_results = defaultdict(int)
        
        # Latency buckets in milliseconds for histogram
        # Buckets help understand latency distribution
        self.latency_buckets = [100, 500, 1000, 5000, float('inf')]
        
        # Histogram: bucket size -> count of requests in that bucket
        self.latency_counts = defaultdict(int)
        
        # Sum and count for computing average latency
        self.latency_sum = 0
        self.latency_count = 0
    
    def record_request(self, path: str, method: str, status: int, latency_ms: float):
        """Record HTTP request metrics.
        
        Called by middleware for every HTTP request to track:
        - Request count by endpoint and status code
        - Request latency distribution
        
        Args:
            path: HTTP endpoint path (e.g., /webhook, /messages)
            method: HTTP method (GET, POST, etc.)
            status: HTTP response status code (200, 401, 422, etc.)
            latency_ms: Request latency in milliseconds
        """
        with self.lock:
            # Build labels string for Prometheus format
            # Example: path="/webhook",status="200"
            key = f'path="{path}",status="{status}"'
            
            # Increment counter for this endpoint and status
            self.http_requests[key] += 1
            
            # Record latency in histogram buckets
            # Count how many requests fall into each latency bucket
            for bucket in self.latency_buckets:
                if latency_ms <= bucket:
                    self.latency_counts[bucket] += 1
            
            # Track sum and count for average calculation
            self.latency_sum += latency_ms
            self.latency_count += 1
    
    def record_webhook(self, result: str):
        """Record webhook processing outcome.
        
        Called after processing each webhook request to track:
        - How many messages were created
        - How many were duplicates
        - How many had errors
        
        Args:
            result: Outcome of webhook processing
                   Can be: 'created', 'duplicate', 'invalid_signature', 'validation_error'
        """
        with self.lock:
            # Build labels string for Prometheus format
            # Example: result="created"
            key = f'result="{result}"'
            
            # Increment counter for this result type
            self.webhook_results[key] += 1
    
    def export(self) -> str:
        """Export all metrics in Prometheus text format.
        
        This format can be scraped by Prometheus monitoring system.
        Each metric has HELP and TYPE lines followed by data lines.
        
        Returns:
            String with all metrics in Prometheus format
        """
        with self.lock:
            lines = []
            
            # === HTTP REQUESTS COUNTER ===
            # HELP and TYPE lines are required by Prometheus format
            lines.append("# HELP http_requests_total Total HTTP requests")
            lines.append("# TYPE http_requests_total counter")
            
            # Export each path/status combination with its count
            # Sorted for consistent output
            for labels, count in sorted(self.http_requests.items()):
                lines.append(f"http_requests_total{{{labels}}} {count}")
            
            # === WEBHOOK RESULTS COUNTER ===
            lines.append("# HELP webhook_requests_total Total webhook processing outcomes")
            lines.append("# TYPE webhook_requests_total counter")
            
            # Export each result type with its count
            for labels, count in sorted(self.webhook_results.items()):
                lines.append(f"webhook_requests_total{{{labels}}} {count}")
            
            # === REQUEST LATENCY HISTOGRAM ===
            lines.append("# HELP request_latency_ms Request latency in milliseconds")
            lines.append("# TYPE request_latency_ms histogram")
            
            # Export latency buckets
            # Histogram shows how many requests had latency <= each bucket
            cumulative = 0
            for bucket in self.latency_buckets:
                # Add all requests in this bucket and previous buckets
                cumulative += self.latency_counts[bucket]
                
                # Format bucket label ("+Inf" for infinity bucket)
                bucket_label = "+Inf" if bucket == float('inf') else str(int(bucket))
                
                # Export cumulative count for this bucket
                lines.append(f'request_latency_ms_bucket{{le="{bucket_label}"}} {cumulative}')
            
            # Export sum and count for average calculation
            lines.append(f"request_latency_ms_sum {self.latency_sum}")
            lines.append(f"request_latency_ms_count {self.latency_count}")
            
            # Join all lines and add final newline
            return "\n".join(lines) + "\n"
            lines.append(f"request_latency_ms_count {self.latency_count}")
            
            return "\n".join(lines) + "\n"