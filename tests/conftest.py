"""Pytest configuration and fixtures for test database initialization.

This file sets up the test environment before running tests.
It creates a temporary database and initializes it with the schema.
"""

import pytest
import sys
import os
import tempfile

# Add parent directory to path so we can import from it
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.main import app, db_manager
from app.config import settings


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """Initialize test database once for the entire test session.
    
    This fixture:
    - Creates a temporary directory for test database
    - Configures the app to use the test database
    - Sets a test webhook secret for signature verification
    - Initializes the database schema
    
    The 'session' scope means this runs once at the start of all tests.
    The 'autouse=True' means it runs automatically without being imported.
    
    Yields:
        After all tests complete, cleans up the temporary database file
    """
    # Create temporary directory for test database
    # tempfile.mkdtemp() creates a unique directory that will be cleaned up
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test.db")
    
    # Update config to use test database instead of production database
    # This ensures tests don't affect real data
    settings.database_url = f"sqlite:///{db_path}"
    
    # Set test webhook secret for signature verification
    # All tests will use this secret when computing signatures
    settings.webhook_secret = "testsecret"
    
    # Initialize database with schema
    # This creates the messages table and indexes
    db_manager.db_path = db_path
    db_manager.init_db()
    
    # Yield control to run tests
    yield
    
    # Cleanup: Remove temporary database file after tests complete
    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.fixture(autouse=True)
def clear_db():
    """Clear database before each test.
    
    This fixture:
    - Runs before EVERY test (function scope)
    - Deletes all messages from the database
    - Ensures tests are isolated from each other
    
    The 'autouse=True' means it runs automatically without being imported.
    
    Example:
    - Test 1 inserts message "m1"
    - clear_db runs after Test 1
    - Message "m1" is deleted from database
    - Test 2 starts with empty database
    
    Yields:
        The test runs between setup and cleanup
    """
    # Get database connection
    conn = db_manager._get_connection()
    cursor = conn.cursor()
    
    # Delete all messages from database
    # This ensures each test starts with an empty database
    cursor.execute("DELETE FROM messages")
    
    # Commit the deletion
    conn.commit()
    conn.close()
    
    # Yield control to run the test
    yield
    
    # Cleanup happens automatically after test completes
    # (next iteration will clear again before next test)
