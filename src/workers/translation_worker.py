"""Background worker for processing translation jobs."""

import json
import logging
import uuid
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.config import get_settings
from src.models.job import Job, JobStatus, ProcessingStage, DocumentType
from src.services.document_processor import DocumentProcessor, DocumentProcessingError

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database setup
settings = get_settings()
engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def process_translation_job(job_data: dict) -> dict:
    """
    Process a translation job.
    
    Args:
        job_data: Dictionary containing job_id, file_path, and document_type
    
    Returns:
        Dictionary with processing results
    """
    job_id = uuid.UUID(job_data["job_id"])
    file_path = Path(job_data["file_path"])
    document_type = DocumentType(job_data["document_type"])
    
    logger.info(f"Starting job processing: {job_id}")
    
    # Get database session
    db = SessionLocal()
    
    try:
        # Get job from database
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            raise Exception(f"Job not found: {job_id}")
        
        # Update job status
        job.status = JobStatus.PROCESSING
        job.stage = ProcessingStage.UPLOADED
        job.progress = "0.0"
        db.commit()
        
        # Create output directory
        output_dir = settings.output_dir / str(job_id)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Progress callback to update database
        def update_progress(progress: float, stage_description: str = None):
            try:
                job.progress = str(progress)
                if stage_description:
                    # Map stage description to enum
                    if "OCR" in stage_description:
                        job.stage = ProcessingStage.OCR_PROCESSING
                    elif "Markdown" in stage_description or "Converting" in stage_description:
                        job.stage = ProcessingStage.DOCLING_CONVERSION
                    elif "Translating" in stage_description or "Translation" in stage_description:
                        job.stage = ProcessingStage.TRANSLATION
                    elif "PDF" in stage_description:
                        job.stage = ProcessingStage.PDF_GENERATION
                    elif "completed" in stage_description.lower():
                        job.stage = ProcessingStage.COMPLETED
                
                db.commit()
                logger.info(f"Job {job_id} progress: {progress:.1f}% - {stage_description}")
            except Exception as e:
                logger.error(f"Failed to update progress: {e}")
        
        # Process the document
        processor = DocumentProcessor()
        final_pdf_path = processor.process_pdf(
            file_path, 
            output_dir, 
            document_type,
            progress_callback=update_progress
        )
        
        # Collect output files
        output_files = []
        
        # Add the final PDF
        if final_pdf_path.exists():
            output_files.append(str(final_pdf_path.relative_to(output_dir)))
        
        # Add markdown files
        for md_file in output_dir.glob("**/*.md"):
            if md_file.is_file():
                output_files.append(str(md_file.relative_to(output_dir)))
        
        # Add HTML files if any
        for html_file in output_dir.glob("**/*.html"):
            if html_file.is_file():
                output_files.append(str(html_file.relative_to(output_dir)))
        
        # Update job as completed
        job.status = JobStatus.COMPLETED
        job.stage = ProcessingStage.COMPLETED
        job.progress = "100.0"
        job.output_files = json.dumps(output_files)
        job.error_message = None
        db.commit()
        
        # Cleanup work files
        processor.cleanup_work_files(output_dir / "work")
        
        logger.info(f"Job completed successfully: {job_id}")
        
        return {
            "job_id": str(job_id),
            "status": "completed",
            "output_files": output_files,
            "final_pdf": str(final_pdf_path) if final_pdf_path.exists() else None
        }
        
    except DocumentProcessingError as e:
        logger.error(f"Document processing failed for job {job_id}: {e}")
        
        # Update job as failed
        job.status = JobStatus.FAILED
        job.error_message = str(e)
        db.commit()
        
        return {
            "job_id": str(job_id),
            "status": "failed",
            "error": str(e)
        }
        
    except Exception as e:
        logger.error(f"Unexpected error processing job {job_id}: {e}")
        
        # Update job as failed
        try:
            job.status = JobStatus.FAILED
            job.error_message = f"Unexpected error: {e}"
            db.commit()
        except Exception as db_error:
            logger.error(f"Failed to update job status: {db_error}")
        
        return {
            "job_id": str(job_id),
            "status": "failed",
            "error": str(e)
        }
        
    finally:
        db.close()


if __name__ == "__main__":
    """Run the worker process."""
    import redis
    from rq import Worker

    logger.info(f"Worker starting...")
    logger.info(f"Redis URL: {settings.redis_url}")
    logger.info(f"Queue name: {settings.queue_name}")

    try:
        # Connect to Redis
        logger.info("Connecting to Redis...")
        redis_conn = redis.from_url(settings.redis_url)
        redis_conn.ping()
        logger.info("✅ Redis connection successful")

        # Create worker
        logger.info(f"Creating worker for queue: {settings.queue_name}")
        worker = Worker([settings.queue_name], connection=redis_conn)
        logger.info(f"✅ Worker created: {worker.name}")

        # Start working
        logger.info(f"🚀 Starting worker for queue: {settings.queue_name}")
        worker.work(with_scheduler=True)

    except Exception as e:
        logger.error(f"❌ Worker failed to start: {e}")
        import traceback
        traceback.print_exc()
        raise
