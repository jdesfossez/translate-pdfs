"""Job data models for the PDF translation service."""

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import Column, DateTime
from sqlalchemy import Enum as SQLEnum
from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func
from sqlalchemy.types import CHAR, TypeDecorator

Base = declarative_base()


class GUID(TypeDecorator):
    """Platform-independent GUID type.

    Uses PostgreSQL's UUID type, otherwise uses CHAR(36), storing as stringified hex values.
    """
    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            return dialect.type_descriptor(UUID())
        else:
            return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        elif dialect.name == 'postgresql':
            return str(value)
        else:
            if not isinstance(value, UUID):
                return str(UUID(value))
            else:
                return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        else:
            if not isinstance(value, UUID):
                return UUID(value)
            return value


class DocumentType(str, Enum):
    """Types of documents that can be processed."""
    TEXT_PDF = "text_pdf"
    TEXT_IMAGE_PDF = "text_image_pdf"  # needs OCR but clean pages
    SCAN = "scan"  # needs OCR and cleanup


class JobStatus(str, Enum):
    """Job processing status."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ProcessingStage(str, Enum):
    """Current processing stage."""
    UPLOADED = "uploaded"
    OCR_PROCESSING = "ocr_processing"
    DOCLING_CONVERSION = "docling_conversion"
    TRANSLATION = "translation"
    PDF_GENERATION = "pdf_generation"
    COMPLETED = "completed"


class JobCreate(BaseModel):
    """Request model for creating a new job."""
    document_type: DocumentType
    filename: str


class JobResponse(BaseModel):
    """Response model for job information."""
    id: UUID
    filename: str
    document_type: DocumentType
    status: JobStatus
    stage: ProcessingStage
    progress: float = Field(ge=0.0, le=100.0, description="Progress percentage")
    created_at: datetime
    updated_at: datetime
    error_message: Optional[str] = None
    output_files: list[str] = Field(default_factory=list)

    model_config = {"from_attributes": True, "arbitrary_types_allowed": True}

    @field_validator('id', mode='before')
    @classmethod
    def validate_id(cls, v):
        """Convert any UUID-like value to standard UUID."""
        if isinstance(v, UUID):
            return v
        if isinstance(v, str):
            return UUID(v)
        # Handle SQLAlchemy UUID types
        return UUID(str(v))


class Job(Base):
    """SQLAlchemy model for jobs."""
    __tablename__ = "jobs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    filename = Column(String(255), nullable=False)
    document_type = Column(SQLEnum(DocumentType), nullable=False)
    status = Column(SQLEnum(JobStatus), nullable=False, default=JobStatus.PENDING)
    stage = Column(SQLEnum(ProcessingStage), nullable=False, default=ProcessingStage.UPLOADED)
    progress = Column(String(10), nullable=False, default="0.0")
    error_message = Column(Text, nullable=True)
    output_files = Column(Text, nullable=True)  # JSON string of file paths
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def to_response(self) -> JobResponse:
        """Convert to response model."""
        import json
        output_files = []
        if self.output_files:
            try:
                output_files = json.loads(self.output_files)
            except json.JSONDecodeError:
                pass

        # Ensure UUID is properly converted
        job_id = self.id
        if not isinstance(job_id, UUID):
            job_id = UUID(str(job_id))

        return JobResponse(
            id=job_id,
            filename=self.filename,
            document_type=self.document_type,
            status=self.status,
            stage=self.stage,
            progress=float(self.progress),
            created_at=self.created_at,
            updated_at=self.updated_at,
            error_message=self.error_message,
            output_files=output_files
        )
