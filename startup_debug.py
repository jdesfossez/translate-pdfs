#!/usr/bin/env python3
"""Comprehensive startup debug script."""

import sys
import os
import time
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_environment():
    """Check environment variables."""
    print("=== Environment Variables ===")
    env_vars = [
        'PDF_TRANSLATE_REDIS_URL',
        'PDF_TRANSLATE_DATABASE_URL', 
        'PDF_TRANSLATE_MODEL_NAME',
        'PDF_TRANSLATE_DEBUG',
        'PYTHONPATH'
    ]
    
    for var in env_vars:
        value = os.environ.get(var, 'NOT SET')
        print(f"{var}: {value}")

def check_directories():
    """Check required directories."""
    print("\n=== Directory Check ===")
    dirs = ['/app', '/app/uploads', '/app/outputs', '/app/logs', '/app/data']
    
    for dir_path in dirs:
        path = Path(dir_path)
        exists = path.exists()
        writable = path.is_dir() and os.access(path, os.W_OK) if exists else False
        print(f"{dir_path}: {'✅' if exists else '❌'} exists, {'✅' if writable else '❌'} writable")

def check_redis():
    """Check Redis connectivity."""
    print("\n=== Redis Check ===")
    try:
        from src.config import get_settings
        settings = get_settings()
        
        import redis
        redis_conn = redis.from_url(settings.redis_url)
        redis_conn.ping()
        print(f"✅ Redis connection successful: {settings.redis_url}")
        
        # Check if Redis is running locally
        try:
            local_redis = redis.Redis(host='redis', port=6379, db=0)
            local_redis.ping()
            print("✅ Local Redis (redis:6379) is running")
        except:
            print("❌ Local Redis (redis:6379) not accessible")
            
        return True
    except Exception as e:
        print(f"❌ Redis error: {e}")
        return False

def check_database():
    """Check database connectivity."""
    print("\n=== Database Check ===")
    try:
        from src.config import get_settings
        from src.database import create_tables
        
        settings = get_settings()
        print(f"Database URL: {settings.database_url}")
        
        create_tables()
        print("✅ Database tables created/verified")
        return True
    except Exception as e:
        print(f"❌ Database error: {e}")
        return False

def check_worker():
    """Check worker setup."""
    print("\n=== Worker Check ===")
    try:
        from src.config import get_settings
        import redis
        from rq import Worker, Queue
        
        settings = get_settings()
        redis_conn = redis.from_url(settings.redis_url)
        
        # Check queue
        queue = Queue(settings.queue_name, connection=redis_conn)
        print(f"✅ Queue '{settings.queue_name}' accessible")
        print(f"  Queue length: {len(queue)}")
        
        # Check workers
        workers = Worker.all(connection=redis_conn)
        print(f"  Active workers: {len(workers)}")
        
        return True
    except Exception as e:
        print(f"❌ Worker check error: {e}")
        return False

def check_model_loading():
    """Check if translation model can be loaded."""
    print("\n=== Model Loading Check ===")
    try:
        from src.services.translation_service import TranslationService
        
        service = TranslationService()
        print(f"Model name: {service.settings.model_name}")
        print("⚠️  Skipping actual model loading (takes too long)")
        print("✅ Translation service can be instantiated")
        return True
    except Exception as e:
        print(f"❌ Model loading error: {e}")
        return False

def main():
    print("🔍 Starting comprehensive system check...\n")
    
    checks = [
        ("Environment", check_environment),
        ("Directories", check_directories), 
        ("Redis", check_redis),
        ("Database", check_database),
        ("Worker", check_worker),
        ("Model", check_model_loading)
    ]
    
    results = {}
    for name, check_func in checks:
        try:
            result = check_func()
            results[name] = result
        except Exception as e:
            print(f"❌ {name} check failed: {e}")
            results[name] = False
    
    print(f"\n=== Summary ===")
    for name, result in results.items():
        status = "✅" if result else "❌"
        print(f"{status} {name}")
    
    all_passed = all(results.values())
    if all_passed:
        print("\n🎉 All checks passed! System should be ready.")
    else:
        print("\n⚠️  Some checks failed. See details above.")
    
    return all_passed

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
