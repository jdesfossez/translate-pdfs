#!/usr/bin/env python3
"""
Main entry point for the PDF Translation Service.
"""

import logging
import sys
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.api.jobs import router as jobs_router
from src.api.health import router as health_router
from src.config import get_settings, ensure_directories
from src.database import create_tables

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('logs/app.log', mode='a')
    ]
)

logger = logging.getLogger(__name__)

# Get settings
settings = get_settings()

# Create FastAPI app
app = FastAPI(
    title="PDF Translation Service",
    description="Translate PDF documents from English to French using AI",
    version="1.0.0",
    debug=settings.debug
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Setup templates
templates = Jinja2Templates(directory="templates")

# Include routers
app.include_router(health_router, prefix="/health", tags=["health"])
app.include_router(jobs_router, prefix="/api", tags=["jobs"])


@app.on_event("startup")
async def startup_event():
    """Initialize application on startup."""
    logger.info("Starting PDF Translation Service...")
    
    # Ensure directories exist
    ensure_directories()
    Path("logs").mkdir(exist_ok=True)
    Path("data").mkdir(exist_ok=True)
    
    # Create database tables
    create_tables()
    
    logger.info("Application startup complete")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    logger.info("Shutting down PDF Translation Service...")


@app.get("/")
async def root():
    """Serve the main page."""
    from fastapi import Request
    from fastapi.responses import HTMLResponse
    
    # This is a simple redirect to serve the static HTML
    # In a real implementation, you'd use templates.TemplateResponse
    with open("templates/index.html", "r") as f:
        content = f.read()
    return HTMLResponse(content=content)


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level="info" if not settings.debug else "debug"
    )
