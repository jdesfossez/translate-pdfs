#!/usr/bin/env python3
"""Test worker startup independently."""

import sys
import logging
from pathlib import Path

# Add the app directory to Python path
sys.path.insert(0, '/app')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_imports():
    """Test if all required modules can be imported."""
    try:
        print("Testing imports...")
        
        import redis
        print("✅ redis imported")
        
        from rq import Worker, Queue
        print("✅ rq imported")
        
        from src.config import get_settings
        print("✅ src.config imported")
        
        from src.workers.translation_worker import process_translation_job
        print("✅ translation_worker imported")
        
        return True
    except Exception as e:
        print(f"❌ Import error: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_redis_connection():
    """Test Redis connection."""
    try:
        from src.config import get_settings
        settings = get_settings()
        
        print(f"Testing Redis connection to: {settings.redis_url}")
        
        import redis
        redis_conn = redis.from_url(settings.redis_url)
        redis_conn.ping()
        print("✅ Redis connection successful")
        return True
    except Exception as e:
        print(f"❌ Redis connection error: {e}")
        return False

def test_worker_creation():
    """Test worker creation."""
    try:
        from src.config import get_settings
        import redis
        from rq import Worker
        
        settings = get_settings()
        redis_conn = redis.from_url(settings.redis_url)
        
        print(f"Creating worker for queue: {settings.queue_name}")
        worker = Worker([settings.queue_name], connection=redis_conn)
        print(f"✅ Worker created: {worker.name}")
        return True
    except Exception as e:
        print(f"❌ Worker creation error: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("=== Worker Startup Test ===")
    
    if not test_imports():
        return False
        
    if not test_redis_connection():
        return False
        
    if not test_worker_creation():
        return False
        
    print("✅ All tests passed! Worker should be able to start.")
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
