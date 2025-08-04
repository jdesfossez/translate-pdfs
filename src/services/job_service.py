"""Job service for managing translation jobs and queue operations."""

import json
import logging
import uuid
from typing import Optional

import redis
from rq import Queue
from rq.job import Job as RQJob

from src.config import get_settings
from src.models.job import DocumentType

logger = logging.getLogger(__name__)


class JobService:
    """Service for managing translation jobs and queue operations."""
    
    def __init__(self):
        self.settings = get_settings()
        self.redis_client = redis.from_url(self.settings.redis_url)
        self.queue = Queue(self.settings.queue_name, connection=self.redis_client)
    
    def queue_job(self, job_id: uuid.UUID, file_path: str, document_type: DocumentType) -> str:
        """Queue a translation job for processing."""
        from src.workers.translation_worker import process_translation_job
        
        job_data = {
            "job_id": str(job_id),
            "file_path": file_path,
            "document_type": document_type.value
        }
        
        # Enqueue the job with a timeout of 4 hours
        rq_job = self.queue.enqueue(
            process_translation_job,
            job_data,
            job_timeout=14400,  # 4 hours
            job_id=str(job_id)
        )
        
        logger.info(f"Job queued: {job_id} -> {rq_job.id}")
        return rq_job.id
    
    def cancel_job(self, job_id: uuid.UUID) -> bool:
        """Cancel a queued job."""
        try:
            rq_job = RQJob.fetch(str(job_id), connection=self.redis_client)
            rq_job.cancel()
            logger.info(f"Job cancelled: {job_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel job {job_id}: {e}")
            return False
    
    def get_job_status(self, job_id: uuid.UUID) -> Optional[dict]:
        """Get the status of a job from the queue."""
        try:
            rq_job = RQJob.fetch(str(job_id), connection=self.redis_client)
            return {
                "id": rq_job.id,
                "status": rq_job.get_status(),
                "created_at": rq_job.created_at,
                "started_at": rq_job.started_at,
                "ended_at": rq_job.ended_at,
                "result": rq_job.result,
                "exc_info": rq_job.exc_info
            }
        except Exception as e:
            logger.error(f"Failed to get job status {job_id}: {e}")
            return None
    
    def get_queue_info(self) -> dict:
        """Get information about the job queue."""
        return {
            "name": self.queue.name,
            "length": len(self.queue),
            "failed_count": len(self.queue.failed_job_registry),
            "finished_count": len(self.queue.finished_job_registry),
            "started_count": len(self.queue.started_job_registry),
            "deferred_count": len(self.queue.deferred_job_registry)
        }
