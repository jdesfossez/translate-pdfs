"""Tests for API endpoints."""

import io
import uuid
from unittest.mock import patch

import pytest

from src.models.job import DocumentType, JobStatus


class TestHealthAPI:
    """Test health check endpoints."""

    def test_health_check(self, client):
        """Test basic health check."""
        response = client.get("/health/")

        # In test environment, Redis may not be available, so we expect 503
        if response.status_code == 503:
            # Health check failed due to missing services (expected in test)
            data = response.json()
            assert "status" in data
            assert "timestamp" in data
            assert "checks" in data
            # Redis should be marked as unhealthy
            assert "redis" in data["checks"]
            assert "unhealthy" in data["checks"]["redis"]
        else:
            # If all services are available
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert "timestamp" in data
            assert "gpu_available" in data
            assert "gpu_count" in data
            assert data["version"] == "1.0.0"

    def test_readiness_check(self, client):
        """Test readiness check."""
        response = client.get("/health/ready")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "ready"
        assert "timestamp" in data


class TestJobsAPI:
    """Test job management endpoints."""

    def test_create_job_success(self, client, sample_pdf_content):
        """Test successful job creation."""
        with patch("src.services.job_service.JobService.queue_job") as mock_queue:
            mock_queue.return_value = "test-job-id"

            files = {
                "file": ("test.pdf", io.BytesIO(sample_pdf_content), "application/pdf")
            }
            data = {"document_type": DocumentType.TEXT_PDF.value}

            response = client.post("/api/jobs", files=files, data=data)
            assert response.status_code == 200

            job_data = response.json()
            assert job_data["filename"] == "test.pdf"
            assert job_data["document_type"] == DocumentType.TEXT_PDF.value
            assert job_data["status"] == JobStatus.PENDING.value
            assert "id" in job_data

    def test_create_job_invalid_file_type(self, client):
        """Test job creation with invalid file type."""
        files = {"file": ("test.txt", io.BytesIO(b"test content"), "text/plain")}
        data = {"document_type": DocumentType.TEXT_PDF.value}

        response = client.post("/api/jobs", files=files, data=data)
        assert response.status_code == 400
        assert "Only PDF files are supported" in response.json()["detail"]

    def test_create_job_file_too_large(self, client, test_settings):
        """Test job creation with file too large."""
        large_content = b"x" * (test_settings.max_file_size + 1)
        files = {"file": ("large.pdf", io.BytesIO(large_content), "application/pdf")}
        data = {"document_type": DocumentType.TEXT_PDF.value}

        response = client.post("/api/jobs", files=files, data=data)
        assert response.status_code == 400
        assert "File too large" in response.json()["detail"]

    def test_list_jobs_empty(self, client):
        """Test listing jobs when none exist."""
        response = client.get("/api/jobs")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_jobs_with_data(self, client, test_db, sample_pdf_content):
        """Test listing jobs with existing data."""
        from src.models.job import Job

        # Create a test job
        job = Job(
            id=str(uuid.uuid4()),
            filename="test.pdf",
            document_type=DocumentType.TEXT_PDF,
            status=JobStatus.PENDING,
        )
        test_db.add(job)
        test_db.commit()

        response = client.get("/api/jobs")
        assert response.status_code == 200

        jobs = response.json()
        assert len(jobs) == 1
        assert jobs[0]["filename"] == "test.pdf"

    def test_get_job_success(self, client, test_db):
        """Test getting a specific job."""
        from src.models.job import Job

        job_id = str(uuid.uuid4())
        job = Job(
            id=job_id,
            filename="test.pdf",
            document_type=DocumentType.TEXT_PDF,
            status=JobStatus.PENDING,
        )
        test_db.add(job)
        test_db.commit()

        response = client.get(f"/api/jobs/{job_id}")
        assert response.status_code == 200

        job_data = response.json()
        assert job_data["id"] == str(job_id)
        assert job_data["filename"] == "test.pdf"

    def test_get_job_not_found(self, client):
        """Test getting a non-existent job."""
        job_id = str(uuid.uuid4())
        response = client.get(f"/api/jobs/{job_id}")
        assert response.status_code == 404
        assert "Job not found" in response.json()["detail"]

    def test_cancel_job_success(self, client, test_db):
        """Test cancelling a job."""
        from src.models.job import Job

        job_id = str(uuid.uuid4())
        job = Job(
            id=job_id,
            filename="test.pdf",
            document_type=DocumentType.TEXT_PDF,
            status=JobStatus.PENDING,
        )
        test_db.add(job)
        test_db.commit()

        with patch("src.services.job_service.JobService.cancel_job") as mock_cancel:
            mock_cancel.return_value = True

            response = client.delete(f"/api/jobs/{job_id}")
            assert response.status_code == 200
            assert "Job cancelled" in response.json()["message"]

    def test_cancel_job_not_found(self, client):
        """Test cancelling a non-existent job."""
        job_id = str(uuid.uuid4())
        response = client.delete(f"/api/jobs/{job_id}")
        assert response.status_code == 404
        assert "Job not found" in response.json()["detail"]

    def test_cancel_completed_job(self, client, test_db):
        """Test cancelling a completed job."""
        from src.models.job import Job

        job_id = str(uuid.uuid4())
        job = Job(
            id=job_id,
            filename="test.pdf",
            document_type=DocumentType.TEXT_PDF,
            status=JobStatus.COMPLETED,
        )
        test_db.add(job)
        test_db.commit()

        response = client.delete(f"/api/jobs/{job_id}")
        assert response.status_code == 400
        assert "Job cannot be cancelled" in response.json()["detail"]

    def test_download_file_not_found(self, client):
        """Test downloading from a non-existent job."""
        job_id = str(uuid.uuid4())
        response = client.get(f"/api/jobs/{job_id}/download/test.pdf")
        assert response.status_code == 404
        assert "Job not found" in response.json()["detail"]

    def test_download_file_not_completed(self, client, test_db):
        """Test downloading from an incomplete job."""
        from src.models.job import Job

        job_id = str(uuid.uuid4())
        job = Job(
            id=job_id,
            filename="test.pdf",
            document_type=DocumentType.TEXT_PDF,
            status=JobStatus.PROCESSING,
        )
        test_db.add(job)
        test_db.commit()

        response = client.get(f"/api/jobs/{job_id}/download/test.pdf")
        assert response.status_code == 400
        assert "Job not completed" in response.json()["detail"]
