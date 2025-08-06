#!/usr/bin/env python3
"""Test Redis connectivity and basic operations."""

import redis
import time
import sys

def test_redis_connection():
    """Test basic Redis connection."""
    try:
        print("Testing Redis connection...")
        
        # Test different Redis URLs
        redis_urls = [
            "redis://localhost:6379/0",
            "redis://127.0.0.1:6379/0",
            "redis://localhost:6379",
        ]
        
        for url in redis_urls:
            try:
                print(f"  Trying {url}...")
                r = redis.from_url(url)
                r.ping()
                print(f"  ✅ Connected to {url}")
                return r, url
            except Exception as e:
                print(f"  ❌ Failed to connect to {url}: {e}")
        
        return None, None
        
    except Exception as e:
        print(f"❌ Redis connection test failed: {e}")
        return None, None

def test_redis_operations(r):
    """Test basic Redis operations."""
    try:
        print("\nTesting Redis operations...")
        
        # Test set/get
        test_key = "test_key"
        test_value = "test_value"
        
        r.set(test_key, test_value)
        retrieved = r.get(test_key)
        
        if retrieved and retrieved.decode() == test_value:
            print("  ✅ Set/Get operations work")
        else:
            print("  ❌ Set/Get operations failed")
            return False
        
        # Test list operations
        list_key = "test_list"
        r.delete(list_key)  # Clean up first
        r.lpush(list_key, "item1", "item2", "item3")
        list_length = r.llen(list_key)
        
        if list_length == 3:
            print("  ✅ List operations work")
        else:
            print(f"  ❌ List operations failed (length: {list_length})")
            return False
        
        # Clean up
        r.delete(test_key, list_key)
        print("  ✅ Cleanup successful")
        
        return True
        
    except Exception as e:
        print(f"  ❌ Redis operations test failed: {e}")
        return False

def check_redis_info(r):
    """Check Redis server information."""
    try:
        print("\nRedis server information:")
        info = r.info()
        
        print(f"  Redis version: {info.get('redis_version', 'Unknown')}")
        print(f"  Used memory: {info.get('used_memory_human', 'Unknown')}")
        print(f"  Connected clients: {info.get('connected_clients', 'Unknown')}")
        print(f"  Total commands processed: {info.get('total_commands_processed', 'Unknown')}")
        
        return True
        
    except Exception as e:
        print(f"  ❌ Failed to get Redis info: {e}")
        return False

def check_redis_process():
    """Check if Redis process is running."""
    try:
        import subprocess
        result = subprocess.run(['pgrep', '-f', 'redis-server'], capture_output=True, text=True)
        
        if result.returncode == 0:
            pids = result.stdout.strip().split('\n')
            print(f"✅ Redis process running (PIDs: {', '.join(pids)})")
            return True
        else:
            print("❌ Redis process not found")
            return False
            
    except Exception as e:
        print(f"❌ Failed to check Redis process: {e}")
        return False

def main():
    print("=== Redis Connectivity Test ===")
    
    # Check if Redis process is running
    process_running = check_redis_process()
    
    # Test connection
    r, url = test_redis_connection()
    
    if r is None:
        print("\n❌ Cannot connect to Redis. Check if Redis is running.")
        
        if not process_running:
            print("\nTroubleshooting steps:")
            print("1. Check supervisor status: supervisorctl status")
            print("2. Check Redis logs: tail -f /var/log/supervisor/redis.log")
            print("3. Start Redis manually: redis-server --port 6379")
            print("4. Check if port is in use: netstat -tlnp | grep 6379")
        
        sys.exit(1)
    
    print(f"\n✅ Successfully connected to Redis at {url}")
    
    # Test operations
    operations_ok = test_redis_operations(r)
    
    # Get server info
    info_ok = check_redis_info(r)
    
    if operations_ok and info_ok:
        print("\n🎉 All Redis tests passed!")
        sys.exit(0)
    else:
        print("\n⚠️ Some Redis tests failed.")
        sys.exit(1)

if __name__ == "__main__":
    main()
