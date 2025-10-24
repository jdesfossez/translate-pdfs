"""Health check API endpoints with comprehensive monitoring."""

import logging
import os
import shutil
from datetime import datetime
from typing import Any, Dict

import redis
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from src.config import get_settings
from src.database import get_db
from src.utils.gpu import collect_gpu_info

logger = logging.getLogger(__name__)

router = APIRouter()


class HealthResponse(BaseModel):
    """Health check response model."""

    status: str
    timestamp: str  # Use string instead of datetime for JSON serialization
    gpu_available: bool
    gpu_count: int
    version: str = "1.0.0"
    checks: Dict[str, str] = {}
    metrics: Dict[str, Any] = {}


@router.get("/", response_model=HealthResponse)
async def health_check():
    """Comprehensive health check endpoint."""
    settings = get_settings()
    gpu_info = collect_gpu_info()

    health_status = HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow().isoformat(),
        gpu_available=gpu_info["available"],
        gpu_count=gpu_info.get("device_count", 0),
    )

    if gpu_info["available"]:
        devices = gpu_info.get("devices", [])
        gh200_present = any("GH200" in dev.get("name", "") for dev in devices)
        health_status.metrics["gpu"] = {
            "cuda_version": gpu_info.get("cuda_version"),
            "gh200_detected": gh200_present,
            "devices": devices,
        }
        health_status.checks["gpu"] = "healthy" if devices else "warning: no devices"
    else:
        health_status.checks["gpu"] = "not available"

    # Check database
    try:
        db = next(get_db())
        db.execute(text("SELECT 1"))
        health_status.checks["database"] = "healthy"
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        health_status.checks["database"] = f"unhealthy: {str(e)}"
        health_status.status = "unhealthy"

    # Check Redis
    try:
        redis_client = redis.from_url(settings.redis_url)
        redis_client.ping()
        health_status.checks["redis"] = "healthy"
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        health_status.checks["redis"] = f"unhealthy: {str(e)}"
        health_status.status = "unhealthy"

    # Check disk space
    try:
        upload_space = shutil.disk_usage(settings.upload_dir)
        output_space = shutil.disk_usage(settings.output_dir)

        upload_free_gb = upload_space.free / (1024**3)
        output_free_gb = output_space.free / (1024**3)

        health_status.metrics["disk_space"] = {
            "upload_dir_free_gb": round(upload_free_gb, 2),
            "output_dir_free_gb": round(output_free_gb, 2),
        }

        # Alert if less than 1GB free
        if upload_free_gb < 1 or output_free_gb < 1:
            health_status.checks["disk_space"] = "warning: low disk space"
            if health_status.status == "healthy":
                health_status.status = "degraded"
        else:
            health_status.checks["disk_space"] = "healthy"

    except Exception as e:
        logger.error(f"Disk space check failed: {e}")
        health_status.checks["disk_space"] = f"unhealthy: {str(e)}"
        health_status.status = "unhealthy"

    if health_status.status == "unhealthy":
        raise HTTPException(status_code=503, detail=health_status.model_dump())

    return health_status


@router.get("/ready")
async def readiness_check():
    """Kubernetes-style readiness check."""
    settings = get_settings()

    try:
        # Check if all critical services are ready
        db = next(get_db())
        db.execute(text("SELECT 1"))

        redis_client = redis.from_url(settings.redis_url)
        redis_client.ping()

        return {"status": "ready", "timestamp": datetime.utcnow().isoformat()}

    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        raise HTTPException(
            status_code=503,
            detail={
                "status": "not ready",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            },
        )


@router.get("/live")
async def liveness_check():
    """Kubernetes-style liveness check."""
    return {"status": "alive", "timestamp": datetime.utcnow().isoformat()}
