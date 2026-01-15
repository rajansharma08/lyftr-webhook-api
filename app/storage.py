"""Database operations module using SQLite.

This module handles all database interactions including:
- Creating and initializing the database schema
- Inserting messages idempotently (duplicate handling)
- Querying messages with pagination and filtering
- Aggregating statistics from stored messages

The database uses SQLite for simplicity and has been designed for:
- Fast lookups with indexed columns (from_msisdn, ts)
- Idempotency with PRIMARY KEY on message_id
- Pagination support with offset/limit
"""

import sqlite3
from datetime import datetime
from typing import Optional, List, Dict, Tuple
from pathlib import Path


class DatabaseManager:
    """Manages SQLite database operations for webhook messages.
    
    This class provides methods for creating tables, inserting messages,
    and querying data with various filters and aggregations.
    """
    
    def __init__(self, database_url: str):
        """Initialize database manager with database path.
        
        Args:
            database_url: Database URL in format sqlite:////path/to/db.db
        """
        # Extract database path from sqlite:////path format
        # Example: sqlite:////data/app.db -> /data/app.db
        self.db_path = database_url.replace("sqlite:///", "")
        
    def _get_connection(self) -> sqlite3.Connection:
        """Get a SQLite connection and configure it.
        
        Creates parent directories if needed and sets row factory
        to return rows as dictionaries.
        
        Returns:
            Configured SQLite connection object
        """
        # Create directory structure if it doesn't exist
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        
        # Connect to database
        conn = sqlite3.connect(self.db_path)
        
        # Return rows as dictionaries instead of tuples for easier access
        conn.row_factory = sqlite3.Row
        return conn
    
    def init_db(self):
        """Initialize database schema.
        
        Creates the messages table and indexes if they don't exist.
        This is called once at application startup.
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Create messages table with all required fields
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                message_id TEXT PRIMARY KEY,
                from_msisdn TEXT NOT NULL,
                to_msisdn TEXT NOT NULL,
                ts TEXT NOT NULL,
                text TEXT,
                created_at TEXT NOT NULL
            )
        """)
        
        # Create index on sender phone number for fast filtering
        # This speeds up queries like "GET /messages?from=+919876543210"
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_from_msisdn 
            ON messages(from_msisdn)
        """)
        
        # Create index on timestamp for fast sorting and filtering
        # This speeds up queries like "GET /messages?since=2025-01-15T10:00:00Z"
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_ts 
            ON messages(ts)
        """)
        
        # Commit the schema changes
        conn.commit()
        conn.close()
    
    def check_db_ready(self) -> bool:
        """Check if database is initialized and ready.
        
        This is used by the /health/ready endpoint to verify
        the database is functioning properly.
        
        Returns:
            True if messages table exists, False otherwise
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # Query sqlite_master to check if table exists
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='messages'"
            )
            result = cursor.fetchone()
            conn.close()
            
            # Table exists if result is not None
            return result is not None
        except Exception:
            # Database error - consider as not ready
            return False
    
    def message_exists(self, message_id: str) -> bool:
        """Check if a message with given ID already exists (duplicate detection).
        
        Used for idempotent message ingestion - if a duplicate arrives,
        we return 200 OK without re-inserting.
        
        Args:
            message_id: The message ID to check for
            
        Returns:
            True if message exists, False otherwise
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Query for the message
        cursor.execute(
            "SELECT 1 FROM messages WHERE message_id = ? LIMIT 1",
            (message_id,)
        )
        
        # Check if result was found
        exists = cursor.fetchone() is not None
        conn.close()
        
        return exists
    
    def insert_message(
        self,
        message_id: str,
        from_msisdn: str,
        to_msisdn: str,
        ts: str,
        text: Optional[str]
    ):
        """Insert a new message into the database.
        
        Gracefully handles duplicates - if message with same ID exists,
        ignores the insert (idempotency).
        
        Args:
            message_id: Unique message identifier
            from_msisdn: Sender phone number
            to_msisdn: Recipient phone number
            ts: Message timestamp
            text: Optional message text content
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Current timestamp when message is received (server-side)
        created_at = datetime.utcnow().isoformat() + "Z"
        
        try:
            # Insert the message
            cursor.execute("""
                INSERT INTO messages (message_id, from_msisdn, to_msisdn, ts, text, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (message_id, from_msisdn, to_msisdn, ts, text, created_at))
            
            conn.commit()
        except sqlite3.IntegrityError:
            # PRIMARY KEY violation - message already exists, ignore
            # This is a fallback to app-level duplicate detection
            pass
        finally:
            conn.close()
    
    def get_messages(
        self,
        limit: int = 50,
        offset: int = 0,
        from_filter: Optional[str] = None,
        since: Optional[str] = None,
        text_search: Optional[str] = None
    ) -> Tuple[List[Dict], int]:
        """Retrieve messages with pagination and filtering.
        
        This method supports multiple filter parameters and returns both
        the paginated results and total count for proper pagination UI.
        
        Args:
            limit: Number of results per page (1-100)
            offset: Number of results to skip (for pagination)
            from_filter: Filter by sender phone number (exact match)
            since: Filter messages received after this timestamp (ISO-8601)
            text_search: Full-text search in message text (uses LIKE)
            
        Returns:
            Tuple of (messages_list, total_count)
                - messages_list: List of message dictionaries
                - total_count: Total messages matching filters (not just returned count)
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Build WHERE clause dynamically based on provided filters
        where_clauses = []
        params = []
        
        # Add sender filter if provided
        if from_filter:
            where_clauses.append("from_msisdn = ?")
            params.append(from_filter)
        
        # Add timestamp filter if provided
        # Returns messages with timestamp >= since
        if since:
            where_clauses.append("ts >= ?")
            params.append(since)
        
        # Add text search filter if provided
        # Uses LIKE for substring matching
        if text_search:
            where_clauses.append("text LIKE ?")
            params.append(f"%{text_search}%")
        
        # Combine all WHERE clauses with AND, or use "1=1" if no filters
        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
        
        # Get total count of messages matching filters
        # This is used for pagination UI to know total available results
        count_query = f"SELECT COUNT(*) FROM messages WHERE {where_sql}"
        cursor.execute(count_query, params)
        total = cursor.fetchone()[0]
        
        # Get paginated results with consistent ordering
        # Ordered by timestamp (ASC) then message_id (ASC) for deterministic results
        data_query = f"""
            SELECT message_id, from_msisdn, to_msisdn, ts, text
            FROM messages
            WHERE {where_sql}
            ORDER BY ts ASC, message_id ASC
            LIMIT ? OFFSET ?
        """
        cursor.execute(data_query, params + [limit, offset])
        
        # Convert rows to dictionaries
        rows = cursor.fetchall()
        messages = [
            {
                "message_id": row["message_id"],
                "from": row["from_msisdn"],
                "to": row["to_msisdn"],
                "ts": row["ts"],
                "text": row["text"]
            }
            for row in rows
        ]
        
        conn.close()
        return messages, total
    
    def get_stats(self) -> Dict:
        """Get aggregated statistics about stored messages.
        
        Returns statistics including:
        - Total message count
        - Number of unique senders
        - Top 10 senders by message count
        - First and last message timestamps
        
        Returns:
            Dictionary with statistics:
                - total_messages: Total count of all messages
                - senders_count: Count of unique sender phone numbers
                - messages_per_sender: List of top 10 senders with counts
                - first_message_ts: Timestamp of earliest message (or None)
                - last_message_ts: Timestamp of latest message (or None)
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Count total messages in database
        cursor.execute("SELECT COUNT(*) FROM messages")
        total_messages = cursor.fetchone()[0]
        
        # Count unique senders (distinct phone numbers)
        cursor.execute("SELECT COUNT(DISTINCT from_msisdn) FROM messages")
        senders_count = cursor.fetchone()[0]
        
        # Get top 10 senders by message count (aggregation)
        # Ordered by count descending to show most active senders first
        cursor.execute("""
            SELECT from_msisdn, COUNT(*) as count
            FROM messages
            GROUP BY from_msisdn
            ORDER BY count DESC
            LIMIT 10
        """)
        messages_per_sender = [
            {"from": row["from_msisdn"], "count": row["count"]}
            for row in cursor.fetchall()
        ]
        
        # Get first and last message timestamps
        # Used to show time range of data in database
        cursor.execute("SELECT MIN(ts) as first_ts, MAX(ts) as last_ts FROM messages")
        row = cursor.fetchone()
        first_message_ts = row["first_ts"]
        last_message_ts = row["last_ts"]
        
        conn.close()
        
        # Return all statistics as dictionary
        return {
            "total_messages": total_messages,
            "senders_count": senders_count,
            "messages_per_sender": messages_per_sender,
            "first_message_ts": first_message_ts,
            "last_message_ts": last_message_ts
        }