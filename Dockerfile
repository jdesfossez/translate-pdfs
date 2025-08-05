# Multi-stage build for PDF Translation Service
FROM python:3.10-slim as base

# Set environment variables
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
# CPU-only build for CI/CD compatibility

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    wget \
    git \
    software-properties-common \
    netcat-traditional \
    # OCR dependencies
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-fra \
    ghostscript \
    unpaper \
    poppler-utils \
    # Pandoc for PDF generation
    pandoc \
    texlive-latex-base \
    texlive-latex-recommended \
    texlive-latex-extra \
    texlive-fonts-recommended \
    texlive-xetex \
    # Additional utilities
    supervisor \
    nginx \
    redis-server \
    # Cleanup
    && rm -rf /var/lib/apt/lists/*

# Install latest Docling from source (if needed)
RUN pip3 install --no-cache-dir docling

# Install Python dependencies
COPY requirements.txt /tmp/requirements.txt
RUN pip3 install --no-cache-dir -r /tmp/requirements.txt

# Create app user and directories
RUN useradd -m -u 1000 appuser && \
    mkdir -p /app /app/uploads /app/outputs /app/logs /app/data \
             /var/log/supervisor /etc/supervisor/conf.d

# Set working directory
WORKDIR /app

# Copy application code
COPY . /app/

# Copy configuration files
COPY docker/supervisor.conf /etc/supervisor/conf.d/app.conf
COPY docker/nginx.conf /etc/nginx/sites-available/default
COPY docker/entrypoint.sh /entrypoint.sh

# Copy debug scripts
COPY debug_worker.py test_queue.py test_worker_startup.py check_gpu.py startup_debug.py /app/

# Set permissions
RUN chown -R appuser:appuser /app && \
    chmod +x /entrypoint.sh && \
    chmod +x run_tests.py && \
    chmod +x /app/*.py

# Create model cache directory
RUN mkdir -p /home/appuser/.cache && \
    chown -R appuser:appuser /home/appuser/.cache

# Expose ports
EXPOSE 8000 80

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Use entrypoint script
ENTRYPOINT ["/entrypoint.sh"]
CMD ["app"]
