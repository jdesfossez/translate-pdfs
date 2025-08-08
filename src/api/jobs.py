"""Job management API endpoints."""

import json
import logging
import uuid
from pathlib import Path
from typing import List

from fastapi import (APIRouter, Depends, File, Form, HTTPException, Request,
                     UploadFile)
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from src.config import get_settings
from src.database import get_db
from src.models.job import DocumentType, Job, JobCreate, JobResponse, JobStatus
from src.services.job_service import JobService
from src.utils.logging_config import StructuredLogger
from src.utils.security import (check_disk_space, secure_path_join,
                                upload_rate_limiter, validate_upload_file)

logger = logging.getLogger(__name__)
structured_logger = StructuredLogger(__name__)

router = APIRouter()


def _parse_output_files(output_files_str: str) -> list:
    """Parse output files JSON string with error handling."""
    if not output_files_str:
        return []
    try:
        return json.loads(output_files_str)
    except json.JSONDecodeError:
        # Fallback to comma-separated for backward compatibility
        return output_files_str.split(",") if output_files_str else []


@router.post("/jobs")
async def create_job(
    request: Request,
    file: UploadFile = File(...),
    document_type: DocumentType = Form(...),
    db: Session = Depends(get_db),
):
    """Create a new translation job with enhanced security validation."""
    settings = get_settings()

    # Rate limiting
    client_ip = request.client.host
    if not upload_rate_limiter.is_allowed(client_ip):
        structured_logger.log_error(
            "rate_limit_exceeded", f"Too many uploads from {client_ip}"
        )
        raise HTTPException(
            status_code=429, detail="Too many upload requests. Please try again later."
        )

    # Comprehensive file validation
    try:
        sanitized_filename, content = validate_upload_file(file)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"File validation error: {e}")
        raise HTTPException(status_code=500, detail="File validation failed")

    # Check disk space (require 3x file size for processing)
    required_space = len(content) * 3
    if not check_disk_space(settings.upload_dir, required_space):
        structured_logger.log_error(
            "insufficient_disk_space", f"Required: {required_space} bytes"
        )
        raise HTTPException(status_code=507, detail="Insufficient disk space")

    # Create job ID and secure directories
    job_id = str(uuid.uuid4())

    try:
        # Use secure path joining to prevent directory traversal
        upload_dir = secure_path_join(settings.upload_dir, job_id)
        upload_dir.mkdir(parents=True, exist_ok=True)

        # Save uploaded file with sanitized filename
        upload_path = secure_path_join(upload_dir, sanitized_filename)

        upload_path.write_bytes(content)

        structured_logger.log_job_event(
            job_id,
            "file_uploaded",
            filename=sanitized_filename,
            size=len(content),
            client_ip=client_ip,
        )

        logger.info(f"Uploaded file saved: {upload_path}")

    except Exception as e:
        logger.error(f"Failed to save uploaded file: {e}")
        structured_logger.log_error("file_save_failed", str(e), job_id=job_id)
        raise HTTPException(status_code=500, detail="Failed to save file")

    # Create job record
    job = Job(
        id=job_id,
        filename=sanitized_filename,  # Use sanitized filename
        document_type=document_type,
        status=JobStatus.PENDING,
    )

    db.add(job)
    db.commit()
    db.refresh(job)

    # Queue the job for processing
    job_service = JobService()
    try:
        job_service.queue_job(uuid.UUID(job_id), str(upload_path), document_type)
        logger.info(f"Job queued: {job_id}")
    except Exception as e:
        logger.error(f"Failed to queue job: {e}")
        # Update job status to failed
        job.status = JobStatus.FAILED
        job.error_message = f"Failed to queue job: {e}"
        db.commit()
        raise HTTPException(status_code=500, detail="Failed to queue job")

    # Return as dict to avoid Pydantic serialization issues
    response = job.to_response()
    return {
        "id": job_id,  # Already a string
        "filename": response.filename,
        "document_type": response.document_type.value,
        "status": response.status.value,
        "stage": response.stage.value,
        "progress": response.progress,
        "created_at": response.created_at.isoformat(),
        "updated_at": response.updated_at.isoformat(),
        "error_message": response.error_message,
        "output_files": response.output_files,
    }


@router.get("/jobs")
async def list_jobs(db: Session = Depends(get_db)):
    """List all jobs."""
    jobs = db.query(Job).order_by(Job.created_at.desc()).all()
    return [
        {
            "id": job.id,  # Now it's already a string
            "filename": job.filename,
            "document_type": job.document_type.value,
            "status": job.status.value,
            "stage": job.stage.value,
            "progress": float(job.progress),
            "created_at": job.created_at.isoformat(),
            "updated_at": job.updated_at.isoformat(),
            "error_message": job.error_message,
            "output_files": _parse_output_files(job.output_files),
        }
        for job in jobs
    ]


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, db: Session = Depends(get_db)):
    """Get a specific job."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return {
        "id": job.id,  # Now it's already a string
        "filename": job.filename,
        "document_type": job.document_type.value,
        "status": job.status.value,
        "stage": job.stage.value,
        "progress": float(job.progress),
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
        "error_message": job.error_message,
        "output_files": _parse_output_files(job.output_files),
    }


@router.delete("/jobs/{job_id}")
async def cancel_job(job_id: str, db: Session = Depends(get_db)):
    """Cancel a job."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
        raise HTTPException(status_code=400, detail="Job cannot be cancelled")

    # Cancel the job
    job_service = JobService()
    try:
        job_service.cancel_job(uuid.UUID(job_id))  # Convert to UUID for job service
        job.status = JobStatus.CANCELLED
        db.commit()
        logger.info(f"Job cancelled: {job_id}")
    except Exception as e:
        logger.error(f"Failed to cancel job: {e}")
        raise HTTPException(status_code=500, detail="Failed to cancel job")

    return {"message": "Job cancelled"}


@router.post("/jobs/{job_id}/retry")
async def retry_job(job_id: str, db: Session = Depends(get_db)):
    """Retry a failed job."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status not in [JobStatus.FAILED, JobStatus.CANCELLED]:
        raise HTTPException(
            status_code=400, detail="Only failed or cancelled jobs can be retried"
        )

    # Reset job status and re-queue
    job_service = JobService()
    try:
        # Reset job status
        job.status = JobStatus.PENDING
        job.stage = ProcessingStage.QUEUED
        job.progress = "0.0"
        job.error_message = None

        # Re-queue the job
        job_service.queue_job(
            uuid.UUID(job_id), f"uploads/{job_id}/{job.filename}", job.document_type
        )

        db.commit()
        logger.info(f"Job retried: {job_id}")

    except Exception as e:
        logger.error(f"Failed to retry job: {e}")
        raise HTTPException(status_code=500, detail="Failed to retry job")

    return {"message": "Job queued for retry"}


@router.get("/jobs/{job_id}/download/{filename:path}")
async def download_file(job_id: str, filename: str, db: Session = Depends(get_db)):
    """Download a job output file."""
    settings = get_settings()
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status != JobStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Job not completed")

    # Verify the file is in the output_files list for security
    output_files = _parse_output_files(job.output_files)
    if filename not in output_files:
        raise HTTPException(status_code=404, detail="File not found in job outputs")

    # Find the file
    output_dir = settings.output_dir / job_id  # job_id is already a string
    file_path = output_dir / filename

    # Security check: ensure the resolved path is within the output directory
    try:
        file_path = file_path.resolve()
        output_dir = output_dir.resolve()
        if not str(file_path).startswith(str(output_dir)):
            raise HTTPException(status_code=403, detail="Access denied")
    except Exception:
        raise HTTPException(status_code=404, detail="File not found")

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    # Extract just the filename for the download
    download_filename = Path(filename).name

    return FileResponse(
        path=file_path,
        filename=download_filename,
        media_type="application/octet-stream",
    )
