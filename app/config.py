"""Configuration module for loading environment variables.

This module manages all application configuration from environment variables
following the 12-factor app methodology. All configuration is loaded at startup.
"""

import os
from typing import Optional


class Settings:
    """Configuration settings loaded from environment variables.
    
    Attributes:
        database_url: SQLite database path (default: /data/app.db)
        log_level: Python logging level (default: INFO)
        webhook_secret: Secret key for HMAC signature verification (required)
    """
    
    def __init__(self):
        # Database configuration - path where SQLite file is stored
        self.database_url: str = os.getenv("DATABASE_URL", "sqlite:////data/app.db")
        
        # Logging configuration - verbosity level (DEBUG, INFO, WARNING, ERROR)
        self.log_level: str = os.getenv("LOG_LEVEL", "INFO")
        
        # Webhook secret configuration - required for HMAC-SHA256 signature verification
        # Without this, /health/ready will return 503 Service Unavailable
        self.webhook_secret: Optional[str] = os.getenv("WEBHOOK_SECRET")
        
        # Note: We allow app to start without WEBHOOK_SECRET but health check will fail
        # This is intentional - readiness probe will indicate service not ready
        if not self.webhook_secret:
            pass  # Service will be unhealthy until secret is provided


# Global settings instance used throughout the application
settings = Settings()