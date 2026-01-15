"""Structured JSON logging module.

This module provides structured JSON logging for all application events.
Each log line is valid JSON, making logs easy to parse by log aggregation tools.

Example log output:
{
  "ts": "2025-01-15T10:00:00Z",
  "level": "INFO",
  "request_id": "uuid-here",
  "message": "Some event",
  "extra_fields": "can be added"
}
"""

import json
import sys
import logging
from typing import Dict, Any
from datetime import datetime


class JSONFormatter(logging.Formatter):
    """Custom logging formatter that outputs JSON format.
    
    Converts Python logging records to JSON strings for structured logging.
    Each log entry is one valid JSON object per line.
    """
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON string.
        
        Args:
            record: Python logging record to format
            
        Returns:
            JSON string representation of the log record
        """
        # Format timestamp with milliseconds precision
        timestamp = datetime.utcnow().isoformat() + "Z"
        
        # Build base log data with required fields
        log_data = {
            "ts": timestamp,  # Timestamp in ISO-8601 UTC format
            "level": record.levelname,  # Log level (INFO, ERROR, WARNING, DEBUG)
            "message": record.getMessage()  # Log message
        }
        
        # Add extra fields if they exist (from request context)
        if hasattr(record, "extra_fields"):
            log_data.update(record.extra_fields)
        
        # Return as single-line JSON
        return json.dumps(log_data)


class JSONLogger:
    """JSON logger class for structured logging.
    
    This logger outputs JSON to stdout, suitable for log aggregation
    systems like ELK Stack, Splunk, or CloudWatch.
    """
    
    def __init__(self, name: str, level: str = "INFO"):
        """Initialize JSON logger.
        
        Args:
            name: Logger name
            level: Logging level (DEBUG, INFO, WARNING, ERROR)
        """
        # Create underlying Python logger
        self.logger = logging.getLogger(name)
        
        # Set logging level
        self.logger.setLevel(getattr(logging, level.upper()))
        
        # Remove existing handlers to avoid duplicates
        self.logger.handlers = []
        
        # Configure handler to output to stdout
        handler = logging.StreamHandler(sys.stdout)
        
        # Use our custom JSON formatter
        handler.setFormatter(JSONFormatter(datefmt="%Y-%m-%dT%H:%M:%S"))
        
        # Add handler to logger
        self.logger.addHandler(handler)
    
    def _log(self, level: str, data: Dict[str, Any]):
        """Internal method to log data at specified level.
        
        Args:
            level: Log level (INFO, ERROR, WARNING, DEBUG)
            data: Dictionary or string to log
        """
        if isinstance(data, dict):
            # Extract message from data (remove it so it's not duplicated)
            message = data.pop("message", data.pop("event", ""))
            
            # Create log record
            log_record = self.logger.makeRecord(
                self.logger.name,
                getattr(logging, level.upper()),
                "(unknown file)",
                0,
                message,
                (),
                None
            )
            
            # Add extra fields to the record
            log_record.extra_fields = data
            
            # Handle the record with the logger
            self.logger.handle(log_record)
        else:
            # Fall back to string logging
            getattr(self.logger, level.lower())(str(data))
    
    def info(self, data: Dict[str, Any]):
        """Log at INFO level.
        
        Args:
            data: Dictionary to log (will be converted to JSON)
        """
        self._log("INFO", data.copy() if isinstance(data, dict) else data)
    
    def error(self, data: Dict[str, Any]):
        """Log at ERROR level.
        
        Args:
            data: Dictionary to log (will be converted to JSON)
        """
        self._log("ERROR", data.copy() if isinstance(data, dict) else data)
    
    def warning(self, data: Dict[str, Any]):
        """Log at WARNING level.
        
        Args:
            data: Dictionary to log (will be converted to JSON)
        """
        self._log("WARNING", data.copy() if isinstance(data, dict) else data)
    
    def debug(self, data: Dict[str, Any]):
        """Log at DEBUG level.
        
        Args:
            data: Dictionary to log (will be converted to JSON)
        """
        self._log("DEBUG", data.copy() if isinstance(data, dict) else data)


def setup_logger(level: str = "INFO") -> JSONLogger:
    """Factory function to create and configure a JSON logger.
    
    Uses logging level from settings if available.
    
    Args:
        level: Default logging level if not in settings
        
    Returns:
        Configured JSONLogger instance
    """
    from config import settings
    return JSONLogger("app", settings.log_level)


def log_request(logger: JSONLogger, request_data: Dict[str, Any]):
    """Helper function to log request data.
    
    Args:
        logger: JSONLogger instance
        request_data: Dictionary with request information to log
    """
    logger.info(request_data)