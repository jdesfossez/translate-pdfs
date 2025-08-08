"""Security utilities for file upload validation and path protection."""

import hashlib
import logging
import mimetypes
import os
import re
from pathlib import Path
from typing import List, Optional, Tuple

from fastapi import HTTPException, UploadFile

logger = logging.getLogger(__name__)

# Allowed file extensions and MIME types
ALLOWED_EXTENSIONS = {".pdf"}
ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/x-pdf",
    "application/acrobat",
    "applications/vnd.pdf",
    "text/pdf",
    "text/x-pdf",
}

# Maximum file sizes (in bytes)
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
MAX_FILENAME_LENGTH = 255

# Dangerous filename patterns
DANGEROUS_PATTERNS = [
    r"\.\./",  # Path traversal
    r"\.\.\\",  # Windows path traversal
    r"^/",  # Absolute path
    r"^\\",  # Windows absolute path
    r"^\w:",  # Windows drive letter
    r'[<>:"|?*]',  # Windows forbidden characters
    r"[\x00-\x1f]",  # Control characters
]

# Reserved filenames (Windows)
RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    "COM1",
    "COM2",
    "COM3",
    "COM4",
    "COM5",
    "COM6",
    "COM7",
    "COM8",
    "COM9",
    "LPT1",
    "LPT2",
    "LPT3",
    "LPT4",
    "LPT5",
    "LPT6",
    "LPT7",
    "LPT8",
    "LPT9",
}


class SecurityError(Exception):
    """Security-related error."""

    pass


def validate_filename(filename: str) -> str:
    """
    Validate and sanitize filename.

    Args:
        filename: Original filename

    Returns:
        Sanitized filename

    Raises:
        SecurityError: If filename is invalid or dangerous
    """
    if not filename:
        raise SecurityError("Filename cannot be empty")

    if len(filename) > MAX_FILENAME_LENGTH:
        raise SecurityError(f"Filename too long (max {MAX_FILENAME_LENGTH} characters)")

    # Check for dangerous patterns
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, filename, re.IGNORECASE):
            raise SecurityError(f"Filename contains dangerous pattern: {pattern}")

    # Check for reserved names
    name_without_ext = Path(filename).stem.upper()
    if name_without_ext in RESERVED_NAMES:
        raise SecurityError(f"Filename uses reserved name: {name_without_ext}")

    # Sanitize filename
    sanitized = re.sub(r"[^\w\-_\.]", "_", filename)

    # Ensure it has a valid extension
    if not any(sanitized.lower().endswith(ext) for ext in ALLOWED_EXTENSIONS):
        raise SecurityError(
            f"File extension not allowed. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    return sanitized


def validate_file_content(file_content: bytes) -> Tuple[bool, str]:
    """
    Validate file content by checking magic bytes.

    Args:
        file_content: File content as bytes

    Returns:
        Tuple of (is_valid, detected_type)
    """
    if not file_content:
        return False, "Empty file"

    # Check PDF magic bytes
    pdf_signatures = [
        b"%PDF-",  # Standard PDF signature
        b"\x25\x50\x44\x46\x2d",  # PDF signature in hex
    ]

    for signature in pdf_signatures:
        if file_content.startswith(signature):
            return True, "application/pdf"

    return False, "Not a valid PDF file"


def validate_upload_file(file: UploadFile) -> Tuple[str, bytes]:
    """
    Comprehensive validation of uploaded file.

    Args:
        file: FastAPI UploadFile object

    Returns:
        Tuple of (sanitized_filename, file_content)

    Raises:
        HTTPException: If validation fails
    """
    try:
        # Validate filename
        if not file.filename:
            raise HTTPException(status_code=400, detail="No filename provided")

        sanitized_filename = validate_filename(file.filename)

        # Read and validate file content
        file_content = file.file.read()

        # Check file size
        if len(file_content) == 0:
            raise HTTPException(status_code=400, detail="File is empty")

        if len(file_content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"File too large. Maximum size: {MAX_FILE_SIZE // (1024*1024)}MB",
            )

        # Validate MIME type
        if file.content_type and file.content_type not in ALLOWED_MIME_TYPES:
            logger.warning(
                f"Suspicious MIME type: {file.content_type} for file: {sanitized_filename}"
            )

        # Validate file content
        is_valid, detected_type = validate_file_content(file_content)
        if not is_valid:
            raise HTTPException(status_code=400, detail=detected_type)

        logger.info(
            f"File validation successful: {sanitized_filename} ({len(file_content)} bytes)"
        )
        return sanitized_filename, file_content

    except SecurityError as e:
        logger.warning(f"Security validation failed for file {file.filename}: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error during file validation: {e}")
        raise HTTPException(status_code=500, detail="File validation failed")


def secure_path_join(base_path: Path, *paths: str) -> Path:
    """
    Securely join paths, preventing directory traversal attacks.

    Args:
        base_path: Base directory path
        *paths: Path components to join

    Returns:
        Secure joined path

    Raises:
        SecurityError: If path traversal is detected
    """
    result = base_path

    for path in paths:
        if not path:
            continue

        # Normalize and check for traversal
        normalized = os.path.normpath(path)
        if normalized.startswith("..") or os.path.isabs(normalized):
            raise SecurityError(f"Path traversal detected: {path}")

        result = result / normalized

    # Ensure the result is still within the base path
    try:
        result.resolve().relative_to(base_path.resolve())
    except ValueError:
        raise SecurityError(f"Path outside base directory: {result}")

    return result


def generate_secure_filename(original_filename: str, job_id: str) -> str:
    """
    Generate a secure filename using job ID and hash.

    Args:
        original_filename: Original filename
        job_id: Job ID for uniqueness

    Returns:
        Secure filename
    """
    # Sanitize original filename
    sanitized = validate_filename(original_filename)

    # Get file extension
    ext = Path(sanitized).suffix

    # Create hash of original filename for uniqueness
    filename_hash = hashlib.md5(sanitized.encode()).hexdigest()[:8]

    # Combine job ID and hash
    secure_name = f"{job_id}_{filename_hash}{ext}"

    return secure_name


def check_disk_space(path: Path, required_bytes: int) -> bool:
    """
    Check if there's enough disk space for the operation.

    Args:
        path: Path to check
        required_bytes: Required space in bytes

    Returns:
        True if enough space is available
    """
    try:
        stat = os.statvfs(path)
        available_bytes = stat.f_bavail * stat.f_frsize
        return available_bytes >= required_bytes
    except Exception as e:
        logger.warning(f"Could not check disk space: {e}")
        return True  # Assume OK if we can't check


def sanitize_log_data(data: str) -> str:
    """
    Sanitize data for logging to prevent log injection.

    Args:
        data: Data to sanitize

    Returns:
        Sanitized data
    """
    if not data:
        return ""

    # Remove control characters and newlines
    sanitized = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", str(data))

    # Limit length
    if len(sanitized) > 1000:
        sanitized = sanitized[:1000] + "..."

    return sanitized


class RateLimiter:
    """Simple in-memory rate limiter."""

    def __init__(self, max_requests: int = 10, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = {}

    def is_allowed(self, identifier: str) -> bool:
        """
        Check if request is allowed for the identifier.

        Args:
            identifier: Unique identifier (e.g., IP address)

        Returns:
            True if request is allowed
        """
        import time

        now = time.time()
        window_start = now - self.window_seconds

        # Clean old entries
        self.requests = {
            k: [t for t in v if t > window_start] for k, v in self.requests.items()
        }

        # Check current requests
        current_requests = self.requests.get(identifier, [])

        if len(current_requests) >= self.max_requests:
            return False

        # Add current request
        current_requests.append(now)
        self.requests[identifier] = current_requests

        return True


# Global rate limiter instance
upload_rate_limiter = RateLimiter(
    max_requests=5, window_seconds=300
)  # 5 uploads per 5 minutes
