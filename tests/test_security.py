"""Tests for security utilities."""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch

from src.utils.security import (
    validate_filename, 
    validate_file_content, 
    validate_upload_file,
    secure_path_join,
    SecurityError,
    RateLimiter
)


class TestFilenameValidation:
    """Test filename validation."""
    
    def test_valid_filename(self):
        """Test valid filename passes validation."""
        result = validate_filename("document.pdf")
        assert result == "document.pdf"
    
    def test_sanitize_special_characters(self):
        """Test special characters are sanitized."""
        result = validate_filename("my document (1).pdf")
        assert result == "my_document__1_.pdf"
    
    def test_path_traversal_detection(self):
        """Test path traversal attempts are blocked."""
        with pytest.raises(SecurityError, match="dangerous pattern"):
            validate_filename("../../../etc/passwd.pdf")
        
        with pytest.raises(SecurityError, match="dangerous pattern"):
            validate_filename("..\\..\\windows\\system32\\config.pdf")
    
    def test_reserved_names(self):
        """Test Windows reserved names are blocked."""
        with pytest.raises(SecurityError, match="reserved name"):
            validate_filename("CON.pdf")
        
        with pytest.raises(SecurityError, match="reserved name"):
            validate_filename("aux.pdf")
    
    def test_invalid_extension(self):
        """Test invalid file extensions are rejected."""
        with pytest.raises(SecurityError, match="extension not allowed"):
            validate_filename("malware.exe")
        
        with pytest.raises(SecurityError, match="extension not allowed"):
            validate_filename("script.js")
    
    def test_empty_filename(self):
        """Test empty filename is rejected."""
        with pytest.raises(SecurityError, match="cannot be empty"):
            validate_filename("")
    
    def test_long_filename(self):
        """Test overly long filename is rejected."""
        long_name = "a" * 300 + ".pdf"
        with pytest.raises(SecurityError, match="too long"):
            validate_filename(long_name)


class TestFileContentValidation:
    """Test file content validation."""
    
    def test_valid_pdf_content(self):
        """Test valid PDF content is accepted."""
        pdf_content = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
        is_valid, detected_type = validate_file_content(pdf_content)
        assert is_valid is True
        assert detected_type == "application/pdf"
    
    def test_invalid_content(self):
        """Test invalid content is rejected."""
        invalid_content = b"This is not a PDF file"
        is_valid, detected_type = validate_file_content(invalid_content)
        assert is_valid is False
        assert "Not a valid PDF" in detected_type
    
    def test_empty_content(self):
        """Test empty content is rejected."""
        is_valid, detected_type = validate_file_content(b"")
        assert is_valid is False
        assert detected_type == "Empty file"


class TestUploadFileValidation:
    """Test upload file validation."""
    
    def test_valid_upload(self):
        """Test valid file upload."""
        mock_file = Mock()
        mock_file.filename = "test.pdf"
        mock_file.content_type = "application/pdf"
        mock_file.file.read.return_value = b"%PDF-1.4\ntest content"
        
        filename, content = validate_upload_file(mock_file)
        assert filename == "test.pdf"
        assert content == b"%PDF-1.4\ntest content"
    
    def test_no_filename(self):
        """Test upload without filename is rejected."""
        mock_file = Mock()
        mock_file.filename = None
        
        with pytest.raises(Exception, match="No filename provided"):
            validate_upload_file(mock_file)
    
    def test_empty_file(self):
        """Test empty file upload is rejected."""
        mock_file = Mock()
        mock_file.filename = "test.pdf"
        mock_file.file.read.return_value = b""
        
        with pytest.raises(Exception, match="File is empty"):
            validate_upload_file(mock_file)
    
    def test_oversized_file(self):
        """Test oversized file is rejected."""
        mock_file = Mock()
        mock_file.filename = "test.pdf"
        mock_file.file.read.return_value = b"x" * (101 * 1024 * 1024)  # 101MB
        
        with pytest.raises(Exception, match="File too large"):
            validate_upload_file(mock_file)


class TestSecurePathJoin:
    """Test secure path joining."""
    
    def test_valid_path_join(self):
        """Test valid path joining."""
        base = Path("/app/uploads")
        result = secure_path_join(base, "job123", "file.pdf")
        assert result == Path("/app/uploads/job123/file.pdf")
    
    def test_path_traversal_prevention(self):
        """Test path traversal is prevented."""
        base = Path("/app/uploads")
        
        with pytest.raises(SecurityError, match="Path traversal detected"):
            secure_path_join(base, "../../../etc", "passwd")
        
        with pytest.raises(SecurityError, match="Path traversal detected"):
            secure_path_join(base, "/absolute/path")
    
    def test_empty_path_components(self):
        """Test empty path components are handled."""
        base = Path("/app/uploads")
        result = secure_path_join(base, "", "file.pdf", "")
        assert result == Path("/app/uploads/file.pdf")


class TestRateLimiter:
    """Test rate limiting functionality."""
    
    def test_rate_limit_allows_initial_requests(self):
        """Test rate limiter allows initial requests."""
        limiter = RateLimiter(max_requests=3, window_seconds=60)
        
        assert limiter.is_allowed("user1") is True
        assert limiter.is_allowed("user1") is True
        assert limiter.is_allowed("user1") is True
    
    def test_rate_limit_blocks_excess_requests(self):
        """Test rate limiter blocks excess requests."""
        limiter = RateLimiter(max_requests=2, window_seconds=60)
        
        assert limiter.is_allowed("user1") is True
        assert limiter.is_allowed("user1") is True
        assert limiter.is_allowed("user1") is False  # Should be blocked
    
    def test_rate_limit_per_user(self):
        """Test rate limiting is per user."""
        limiter = RateLimiter(max_requests=1, window_seconds=60)
        
        assert limiter.is_allowed("user1") is True
        assert limiter.is_allowed("user2") is True  # Different user
        assert limiter.is_allowed("user1") is False  # Same user blocked
    
    @patch('time.time')
    def test_rate_limit_window_reset(self, mock_time):
        """Test rate limit window resets over time."""
        limiter = RateLimiter(max_requests=1, window_seconds=60)
        
        # Initial request at time 0
        mock_time.return_value = 0
        assert limiter.is_allowed("user1") is True
        assert limiter.is_allowed("user1") is False
        
        # After window expires
        mock_time.return_value = 61
        assert limiter.is_allowed("user1") is True
