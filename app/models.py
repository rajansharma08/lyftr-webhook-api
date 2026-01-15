"""Pydantic models for data validation and serialization.

This module defines all request and response schemas for the webhook API.
Pydantic automatically validates incoming JSON data and serializes responses.
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime


class WebhookMessage(BaseModel):
    """Pydantic model to validate incoming webhook messages.
    
    This model automatically validates the structure and content of incoming
    webhook requests. All fields are validated before processing.
    
    Attributes:
        message_id: Unique identifier for this message
        from_: Sender phone number in E.164 format (e.g., +919876543210)
        to: Recipient phone number in E.164 format
        ts: Message timestamp in ISO-8601 UTC format (must end with 'Z')
        text: Optional message text (max 4096 characters)
    """
    
    # message_id must be provided and non-empty
    message_id: str = Field(..., min_length=1)
    
    # 'from_' is used internally but maps to 'from' in JSON (Python keyword)
    from_: str = Field(..., alias="from")
    
    # 'to' is recipient phone number
    to: str
    
    # 'ts' is timestamp of the message
    ts: str
    
    # Optional message text content (can be empty)
    text: Optional[str] = Field(None, max_length=4096)

    @field_validator("from_", "to")
    @classmethod
    def validate_e164(cls, v: str) -> str:
        """Validate phone numbers are in E.164 format.
        
        E.164 format: '+' followed by 1-15 digits
        Examples: +919876543210, +14155550100
        
        Args:
            v: Phone number to validate
            
        Returns:
            Validated phone number
            
        Raises:
            ValueError: If phone number is not in E.164 format
        """
        if not v.startswith("+") or not v[1:].isdigit():
            raise ValueError("Must be E.164 format: + followed by digits")
        return v

    @field_validator("ts")
    @classmethod
    def validate_timestamp(cls, v: str) -> str:
        """Validate timestamp is ISO-8601 UTC format.
        
        Expected format: YYYY-MM-DDTHH:MM:SSZ (must end with 'Z' for UTC)
        Example: 2025-01-15T10:00:00Z
        
        Args:
            v: Timestamp string to validate
            
        Returns:
            Validated timestamp
            
        Raises:
            ValueError: If timestamp is not valid ISO-8601 UTC format
        """
        if not v.endswith("Z"):
            raise ValueError("Timestamp must end with Z")
        try:
            # Try to parse the timestamp (remove Z and add UTC offset)
            datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError("Invalid ISO-8601 timestamp")
        return v


class MessageResponse(BaseModel):
    """Schema for individual message in API responses.
    
    This is used when returning messages in /messages endpoint.
    """
    message_id: str
    from_msisdn: str
    to_msisdn: str
    ts: str
    text: Optional[str] = None


class MessagesListResponse(BaseModel):
    """Paginated messages list response schema.
    
    This is returned by the /messages endpoint with pagination info.
    """
    data: List[MessageResponse]
    total: int
    limit: int
    offset: int


class StatsResponse(BaseModel):
    """Statistics response"""
    total_messages: int
    senders_count: int
    messages_per_sender: List[dict]
    first_message_ts: Optional[str] = None
    last_message_ts: Optional[str] = None


class WebhookResponse(BaseModel):
    """Webhook response"""
    status: str


class HealthResponse(BaseModel):
    """Health check response"""
    status: str