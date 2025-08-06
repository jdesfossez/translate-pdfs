"""Configuration management for the PDF translation service."""

import os
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings with environment variable support."""
    
    # Application
    app_name: str = "PDF Translation Service"
    debug: bool = Field(default=False, description="Enable debug mode")
    
    # Server
    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8000, description="Server port")
    
    # File handling
    upload_dir: Path = Field(default=Path("uploads"), description="Upload directory")
    output_dir: Path = Field(default=Path("outputs"), description="Output directory")
    max_file_size: int = Field(default=100 * 1024 * 1024, description="Max file size in bytes (100MB)")
    cleanup_after_hours: int = Field(default=24, description="Hours to keep files before cleanup")
    
    # Queue
    redis_url: str = Field(default="redis://localhost:6379/0", description="Redis URL for queue")
    queue_name: str = Field(default="pdf_translation", description="Queue name")
    
    # Database
    database_url: str = Field(default="sqlite:///./jobs.db", description="Database URL for job metadata")
    
    # Translation
    model_name: str = Field(
        default="facebook/nllb-200-3.3B",
        description="Translation model name"
    )
    model_revision: Optional[str] = Field(default="refs/pr/17", description="Model revision")
    use_safetensors: bool = Field(default=True, description="Use safetensors format")
    cpu_load_then_gpu: bool = Field(default=True, description="Load on CPU then move to GPU")
    max_input_tokens: int = Field(default=950, description="Max input tokens per chunk")
    max_new_tokens: int = Field(default=400, description="Max new tokens per generation")
    num_beams: int = Field(default=1, description="Number of beams for generation")
    batch_size: int = Field(default=48, description="Batch size for translation")
    max_tokens_per_batch: int = Field(default=64000, description="Max tokens per batch")
    
    # OCR
    ocr_language: str = Field(default="eng", description="OCR language")

    # Logging
    log_level: str = Field(default="INFO", description="Logging level")

    # Translation languages
    source_language: str = Field(default="auto", description="Source language for translation")
    target_language: str = Field(default="fr_XX", description="Target language for translation")

    # GPU/NVIDIA settings (optional, for Docker environments)
    nvidia_visible_devices: Optional[str] = Field(default=None, description="NVIDIA visible devices")
    nvidia_driver_capabilities: Optional[str] = Field(default=None, description="NVIDIA driver capabilities")

    class Config:
        env_file = ".env"
        env_prefix = "PDF_TRANSLATE_"
        extra = "ignore"  # Allow extra environment variables


# Global settings instance
settings = Settings()


def get_settings() -> Settings:
    """Get application settings."""
    return settings


def ensure_directories():
    """Ensure required directories exist."""
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    settings.output_dir.mkdir(parents=True, exist_ok=True)
