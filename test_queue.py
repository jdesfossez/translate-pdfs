#!/usr/bin/env python3
"""Test script to manually queue a job and check processing."""

import uuid
import time
from pathlib import Path
from src.services.job_service import JobService
from src.models.job import DocumentType

def main():
    print("Testing job queue...")
    
    # Create a dummy job
    job_service = JobService()
    job_id = uuid.uuid4()
    
    # Create a dummy file for testing
    test_file = Path("test_dummy.pdf")
    test_file.write_text("dummy content")
    
    try:
        # Queue the job
        print(f"Queuing job: {job_id}")
        rq_job_id = job_service.queue_job(
            job_id=job_id,
            file_path=str(test_file),
            document_type=DocumentType.TEXT_PDF
        )
        print(f"Job queued with RQ ID: {rq_job_id}")
        
        # Check queue info
        queue_info = job_service.get_queue_info()
        print(f"Queue info: {queue_info}")
        
        # Wait and check status
        for i in range(10):
            status = job_service.get_job_status(job_id)
            print(f"Job status (attempt {i+1}): {status}")
            time.sleep(2)
            
            if status and status.get('status') in ['finished', 'failed']:
                break
                
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Cleanup
        if test_file.exists():
            test_file.unlink()

if __name__ == "__main__":
    main()
