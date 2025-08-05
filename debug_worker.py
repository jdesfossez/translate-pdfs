#!/usr/bin/env python3
"""Debug script to check worker connectivity and queue status."""

import redis
import logging
from rq import Queue, Worker
from src.config import get_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    settings = get_settings()
    
    print(f"Settings:")
    print(f"  Redis URL: {settings.redis_url}")
    print(f"  Queue name: {settings.queue_name}")
    
    try:
        # Test Redis connection
        redis_conn = redis.from_url(settings.redis_url)
        redis_conn.ping()
        print("✅ Redis connection successful")
        
        # Check queue
        queue = Queue(settings.queue_name, connection=redis_conn)
        print(f"✅ Queue '{settings.queue_name}' accessible")
        print(f"  Queue length: {len(queue)}")
        
        # List all jobs in queue
        jobs = queue.jobs
        print(f"  Jobs in queue: {len(jobs)}")
        for i, job in enumerate(jobs[:5]):  # Show first 5 jobs
            print(f"    Job {i+1}: {job.id} - {job.get_status()}")
        
        # Check failed jobs
        failed_registry = queue.failed_job_registry
        print(f"  Failed jobs: {len(failed_registry)}")
        
        # Check workers
        workers = Worker.all(connection=redis_conn)
        print(f"  Active workers: {len(workers)}")
        for worker in workers:
            print(f"    Worker: {worker.name} - {worker.get_state()}")
        
        # Test worker creation
        worker = Worker([settings.queue_name], connection=redis_conn)
        print(f"✅ Worker created successfully: {worker.name}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
