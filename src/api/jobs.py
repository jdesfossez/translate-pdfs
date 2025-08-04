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
settings = get_settings()


@router.post("/jobs", response_model=JobResponse)
async def create_job(
    file: UploadFile = File(...),
    document_type: DocumentType = Form(...),
    db: Session = Depends(get_db)
):
    """Create a new translation job."""
    # Validate file
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
    
    if file.size > settings.max_file_size:
        raise HTTPException(status_code=400, detail="File too large")
    
    # Save uploaded file
    job_id = uuid.uuid4()
    upload_path = settings.upload_dir / str(job_id) / file.filename
    upload_path.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        content = await file.read()
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
        job_service.queue_job(job_id, str(upload_path), document_type)
        logger.info(f"Job queued: {job_id}")
    except Exception as e:
        logger.error(f"Failed to queue job: {e}")
        # Update job status to failed
        job.status = JobStatus.FAILED
        job.error_message = f"Failed to queue job: {e}"
        db.commit()
        raise HTTPException(status_code=500, detail="Failed to queue job")
    
    return job.to_response()


@router.get("/jobs", response_model=List[JobResponse])
async def list_jobs(db: Session = Depends(get_db)):
    """List all jobs."""
    jobs = db.query(Job).order_by(Job.created_at.desc()).all()
    return [job.to_response() for job in jobs]


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: uuid.UUID, db: Session = Depends(get_db)):
    """Get a specific job."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.to_response()


@router.delete("/jobs/{job_id}")
async def cancel_job(job_id: uuid.UUID, db: Session = Depends(get_db)):
    """Cancel a job."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
        raise HTTPException(status_code=400, detail="Job cannot be cancelled")
    
    # Cancel the job
    job_service = JobService()
    try:
        job_service.cancel_job(job_id)
        job.status = JobStatus.CANCELLED
        db.commit()
        logger.info(f"Job cancelled: {job_id}")
    except Exception as e:
        logger.error(f"Failed to cancel job: {e}")
        raise HTTPException(status_code=500, detail="Failed to cancel job")
    
    return {"message": "Job cancelled"}


@router.get("/jobs/{job_id}/download/{filename}")
async def download_file(job_id: uuid.UUID, filename: str, db: Session = Depends(get_db)):
    """Download a job output file."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.status != JobStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Job not completed")
    
    # Find the file
    output_dir = settings.output_dir / str(job_id)
    file_path = output_dir / filename
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    return FileResponse(
        path=file_path,
        filename=filename,
        media_type='application/octet-stream'
    )
