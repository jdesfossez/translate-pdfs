"""Health check endpoints."""

import logging
from datetime import datetime

import torch
from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()


class HealthResponse(BaseModel):
    """Health check response model."""
    status: str
    timestamp: datetime
    gpu_available: bool
    gpu_count: int
    version: str = "1.0.0"


@router.get("/", response_model=HealthResponse)
async def health_check():
    """Basic health check endpoint."""
    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow(),
        gpu_available=torch.cuda.is_available(),
        gpu_count=torch.cuda.device_count() if torch.cuda.is_available() else 0
    )


@router.get("/ready")
async def readiness_check():
    """Readiness check for container orchestration."""
    # Add more sophisticated checks here if needed
    # e.g., database connectivity, model loading status
    return {"status": "ready", "timestamp": datetime.utcnow()}
