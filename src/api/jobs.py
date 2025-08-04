"""Job management API endpoints."""

import logging
import uuid
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from src.config import get_settings
from src.database import get_db
from src.models.job import Job, JobCreate, JobResponse, DocumentType, JobStatus
from src.services.job_service import JobService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/jobs")
async def create_job(
    file: UploadFile = File(...),
    document_type: DocumentType = Form(...),
    db: Session = Depends(get_db)
):
    """Create a new translation job."""
    settings = get_settings()

    # Validate file
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    # Read file content to check size
    try:
        content = await file.read()
    except Exception as e:
        logger.error(f"Failed to read uploaded file: {e}")
        raise HTTPException(status_code=500, detail="Failed to read file")

    # Check file size
    if len(content) > settings.max_file_size:
        raise HTTPException(status_code=400, detail="File too large")

    # Save uploaded file
    job_id = str(uuid.uuid4())
    upload_path = settings.upload_dir / job_id / file.filename
    upload_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        upload_path.write_bytes(content)
        logger.info(f"Uploaded file saved: {upload_path}")
    except Exception as e:
        logger.error(f"Failed to save uploaded file: {e}")
        raise HTTPException(status_code=500, detail="Failed to save file")
    
    # Create job record
    job = Job(
        id=job_id,
        filename=file.filename,
        document_type=document_type,
        status=JobStatus.PENDING
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
        "output_files": response.output_files
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
            "output_files": job.output_files.split(',') if job.output_files else []
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
        "output_files": job.output_files.split(',') if job.output_files else []
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


@router.get("/jobs/{job_id}/download/{filename}")
async def download_file(job_id: str, filename: str, db: Session = Depends(get_db)):
    """Download a job output file."""
    settings = get_settings()
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status != JobStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Job not completed")

    # Find the file
    output_dir = settings.output_dir / job_id  # job_id is already a string
    file_path = output_dir / filename
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    return FileResponse(
        path=file_path,
        filename=filename,
        media_type='application/octet-stream'
    )
