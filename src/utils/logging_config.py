"""Enhanced logging configuration for production readiness."""

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Optional

from src.config import get_settings


class ColoredFormatter(logging.Formatter):
    """Colored formatter for console output."""

    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"

    def format(self, record):
        if record.levelname in self.COLORS:
            record.levelname = (
                f"{self.COLORS[record.levelname]}{record.levelname}{self.RESET}"
            )
        return super().format(record)


def setup_logging(
    log_level: str = "INFO",
    log_file: Optional[str] = None,
    enable_console: bool = True,
    enable_file: bool = True,
    max_file_size: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,
):
    """
    Setup comprehensive logging configuration.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Path to log file (defaults to logs/app.log)
        enable_console: Enable console logging
        enable_file: Enable file logging
        max_file_size: Maximum size of log file before rotation
        backup_count: Number of backup files to keep
    """
    settings = get_settings()

    # Create logs directory
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    # Default log file
    if log_file is None:
        log_file = log_dir / "app.log"
    else:
        log_file = Path(log_file)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))

    # Clear existing handlers
    root_logger.handlers.clear()

    # Console handler
    if enable_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_formatter = ColoredFormatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        console_handler.setFormatter(console_formatter)
        console_handler.setLevel(getattr(logging, log_level.upper()))
        root_logger.addHandler(console_handler)

    # File handler with rotation
    if enable_file:
        file_handler = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=max_file_size, backupCount=backup_count, encoding="utf-8"
        )
        file_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler.setFormatter(file_formatter)
        file_handler.setLevel(logging.DEBUG)  # Always log everything to file
        root_logger.addHandler(file_handler)

    # Error file handler (separate file for errors)
    error_file = log_dir / "errors.log"
    error_handler = logging.handlers.RotatingFileHandler(
        error_file, maxBytes=max_file_size, backupCount=backup_count, encoding="utf-8"
    )
    error_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s\n"
        "Exception: %(exc_info)s\n",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    error_handler.setFormatter(error_formatter)
    error_handler.setLevel(logging.ERROR)
    root_logger.addHandler(error_handler)

    # Configure specific loggers
    configure_specific_loggers()

    logging.info(f"Logging configured - Level: {log_level}, File: {log_file}")


def configure_specific_loggers():
    """Configure specific loggers for different components."""

    # Reduce noise from external libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("transformers").setLevel(logging.WARNING)
    logging.getLogger("torch").setLevel(logging.WARNING)
    logging.getLogger("PIL").setLevel(logging.WARNING)

    # Set appropriate levels for our components
    logging.getLogger("src.workers").setLevel(logging.INFO)
    logging.getLogger("src.services").setLevel(logging.INFO)
    logging.getLogger("src.api").setLevel(logging.INFO)

    # RQ logging
    logging.getLogger("rq.worker").setLevel(logging.INFO)
    logging.getLogger("rq.job").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the specified name."""
    return logging.getLogger(name)


def log_function_call(func):
    """Decorator to log function calls with parameters and execution time."""
    import functools
    import time

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        logger = get_logger(func.__module__)
        start_time = time.time()

        # Log function entry
        logger.debug(f"Entering {func.__name__} with args={args}, kwargs={kwargs}")

        try:
            result = func(*args, **kwargs)
            execution_time = time.time() - start_time
            logger.debug(
                f"Exiting {func.__name__} - Execution time: {execution_time:.3f}s"
            )
            return result
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(
                f"Error in {func.__name__} after {execution_time:.3f}s: {e}",
                exc_info=True,
            )
            raise

    return wrapper


def log_performance(operation: str):
    """Context manager to log performance of operations."""
    import time
    from contextlib import contextmanager

    @contextmanager
    def performance_logger():
        logger = get_logger("performance")
        start_time = time.time()
        logger.info(f"Starting {operation}")

        try:
            yield
            execution_time = time.time() - start_time
            logger.info(f"Completed {operation} in {execution_time:.3f}s")
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"Failed {operation} after {execution_time:.3f}s: {e}")
            raise

    return performance_logger()


class StructuredLogger:
    """Structured logger for better log analysis."""

    def __init__(self, name: str):
        self.logger = get_logger(name)

    def log_job_event(self, job_id: str, event: str, **kwargs):
        """Log job-related events with structured data."""
        self.logger.info(
            f"JOB_EVENT job_id={job_id} event={event} {' '.join(f'{k}={v}' for k, v in kwargs.items())}"
        )

    def log_api_request(
        self, method: str, path: str, status_code: int, duration: float, **kwargs
    ):
        """Log API requests with structured data."""
        self.logger.info(
            f"API_REQUEST method={method} path={path} status={status_code} duration={duration:.3f}s {' '.join(f'{k}={v}' for k, v in kwargs.items())}"
        )

    def log_error(self, error_type: str, message: str, **kwargs):
        """Log errors with structured data."""
        self.logger.error(
            f"ERROR type={error_type} message={message} {' '.join(f'{k}={v}' for k, v in kwargs.items())}"
        )


# Initialize logging on import
def init_logging():
    """Initialize logging with default configuration."""
    settings = get_settings()
    setup_logging(log_level=settings.log_level, enable_console=True, enable_file=True)


# Auto-initialize if not in test environment
if "pytest" not in sys.modules:
    init_logging()
