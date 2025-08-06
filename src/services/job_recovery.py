"""Job recovery service for handling container restarts and orphaned jobs."""

import logging
import time
from datetime import datetime, timedelta
from typing import List, Optional

import redis
from rq import Queue, Worker
from rq.job import Job as RQJob
from sqlalchemy.orm import Session

from src.config import get_settings
from src.database import SessionLocal
from src.models.job import Job, JobStatus, ProcessingStage
from src.services.job_service import JobService

logger = logging.getLogger(__name__)


class JobRecoveryService:
    """Service for recovering and managing orphaned jobs."""
    
    def __init__(self):
        self.settings = get_settings()
        self.redis_client = redis.from_url(self.settings.redis_url)
        self.queue = Queue(self.settings.queue_name, connection=self.redis_client)
        self.job_service = JobService()
    
    def recover_orphaned_jobs(self) -> int:
        """
        Recover jobs that were processing when the system went down.
        
        Returns:
            Number of jobs recovered
        """
        logger.info("Starting job recovery process...")
        
        db = SessionLocal()
        recovered_count = 0
        
        try:
            # Find jobs that were processing but have no active RQ job
            processing_jobs = db.query(Job).filter(
                Job.status.in_([JobStatus.PENDING, JobStatus.PROCESSING])
            ).all()
            
            for job in processing_jobs:
                try:
                    # Check if RQ job still exists and is active
                    rq_job = self._get_rq_job(job.id)
                    
                    if rq_job is None:
                        # Job doesn't exist in Redis, re-queue it
                        logger.info(f"Re-queuing orphaned job: {job.id}")
                        self._requeue_job(job, db)
                        recovered_count += 1
                    elif rq_job.get_status() == 'failed':
                        # Job failed in Redis but DB wasn't updated
                        logger.info(f"Updating failed job status: {job.id}")
                        job.status = JobStatus.FAILED
                        job.error_message = "Job failed during system restart"
                        db.commit()
                    elif rq_job.get_status() == 'finished':
                        # Job completed in Redis but DB wasn't updated
                        logger.info(f"Updating completed job status: {job.id}")
                        job.status = JobStatus.COMPLETED
                        job.stage = ProcessingStage.COMPLETED
                        job.progress = "100.0"
                        db.commit()
                        
                except Exception as e:
                    logger.error(f"Error recovering job {job.id}: {e}")
                    continue
            
            logger.info(f"Job recovery completed. Recovered {recovered_count} jobs.")
            return recovered_count
            
        finally:
            db.close()
    
    def cleanup_old_jobs(self, max_age_hours: int = 168) -> int:  # 7 days default
        """
        Clean up old completed/failed jobs and their files.
        
        Args:
            max_age_hours: Maximum age in hours for jobs to keep
            
        Returns:
            Number of jobs cleaned up
        """
        logger.info(f"Starting cleanup of jobs older than {max_age_hours} hours...")
        
        db = SessionLocal()
        cleaned_count = 0
        cutoff_time = datetime.utcnow() - timedelta(hours=max_age_hours)
        
        try:
            # Find old completed/failed jobs
            old_jobs = db.query(Job).filter(
                Job.status.in_([JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]),
                Job.updated_at < cutoff_time
            ).all()
            
            for job in old_jobs:
                try:
                    # Clean up job files
                    self._cleanup_job_files(job)
                    
                    # Remove from Redis if still exists
                    self._cleanup_rq_job(job.id)
                    
                    # Remove from database
                    db.delete(job)
                    cleaned_count += 1
                    
                except Exception as e:
                    logger.error(f"Error cleaning up job {job.id}: {e}")
                    continue
            
            db.commit()
            logger.info(f"Cleanup completed. Removed {cleaned_count} old jobs.")
            return cleaned_count
            
        finally:
            db.close()
    
    def get_queue_health(self) -> dict:
        """Get comprehensive queue health information."""
        try:
            # Queue statistics
            queue_info = {
                "queue_length": len(self.queue),
                "failed_jobs": len(self.queue.failed_job_registry),
                "finished_jobs": len(self.queue.finished_job_registry),
                "started_jobs": len(self.queue.started_job_registry),
                "deferred_jobs": len(self.queue.deferred_job_registry),
                "workers": []
            }
            
            # Worker information
            workers = Worker.all(connection=self.redis_client)
            for worker in workers:
                queue_info["workers"].append({
                    "name": worker.name,
                    "state": worker.get_state(),
                    "current_job": worker.get_current_job_id(),
                    "last_heartbeat": worker.last_heartbeat,
                    "birth_date": worker.birth_date
                })
            
            return queue_info
            
        except Exception as e:
            logger.error(f"Error getting queue health: {e}")
            return {"error": str(e)}
    
    def _get_rq_job(self, job_id: str) -> Optional[RQJob]:
        """Get RQ job by ID."""
        try:
            return RQJob.fetch(job_id, connection=self.redis_client)
        except:
            return None
    
    def _requeue_job(self, job: Job, db: Session):
        """Re-queue a job for processing."""
        try:
            # Reset job status
            job.status = JobStatus.PENDING
            job.stage = ProcessingStage.QUEUED
            job.progress = "0.0"
            job.error_message = None
            
            # Re-queue the job
            self.job_service.queue_job(
                job_id=job.id,
                file_path=f"uploads/{job.id}/{job.filename}",
                document_type=job.document_type
            )
            
            db.commit()
            logger.info(f"Successfully re-queued job: {job.id}")
            
        except Exception as e:
            logger.error(f"Failed to re-queue job {job.id}: {e}")
            job.status = JobStatus.FAILED
            job.error_message = f"Failed to re-queue: {e}"
            db.commit()
    
    def _cleanup_job_files(self, job: Job):
        """Clean up files associated with a job."""
        import shutil
        from pathlib import Path
        
        try:
            # Clean up upload directory
            upload_dir = self.settings.upload_dir / job.id
            if upload_dir.exists():
                shutil.rmtree(upload_dir)
                logger.debug(f"Cleaned up upload directory: {upload_dir}")
            
            # Clean up output directory
            output_dir = self.settings.output_dir / job.id
            if output_dir.exists():
                shutil.rmtree(output_dir)
                logger.debug(f"Cleaned up output directory: {output_dir}")
                
        except Exception as e:
            logger.warning(f"Failed to clean up files for job {job.id}: {e}")
    
    def _cleanup_rq_job(self, job_id: str):
        """Clean up RQ job from Redis."""
        try:
            rq_job = self._get_rq_job(job_id)
            if rq_job:
                rq_job.delete()
                logger.debug(f"Cleaned up RQ job: {job_id}")
        except Exception as e:
            logger.warning(f"Failed to clean up RQ job {job_id}: {e}")


def run_recovery_on_startup():
    """Run job recovery when the application starts."""
    try:
        recovery_service = JobRecoveryService()
        
        # Wait a bit for Redis to be fully ready
        time.sleep(5)
        
        # Recover orphaned jobs
        recovered = recovery_service.recover_orphaned_jobs()
        
        # Clean up old jobs (older than 7 days)
        cleaned = recovery_service.cleanup_old_jobs(max_age_hours=168)
        
        logger.info(f"Startup recovery completed: {recovered} jobs recovered, {cleaned} jobs cleaned up")
        
    except Exception as e:
        logger.error(f"Error during startup recovery: {e}")


if __name__ == "__main__":
    # For testing
    logging.basicConfig(level=logging.INFO)
    run_recovery_on_startup()
