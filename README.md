# PDF Translation Service

A comprehensive web service for translating PDF documents from English to French using GPU-accelerated AI models. Built for deployment on NVIDIA GH200 systems with Ubuntu.

## Features

- **Web Interface**: Upload PDFs through a modern web interface
- **Multiple Document Types**: Support for text PDFs, image PDFs (OCR), and scanned documents
- **GPU Acceleration**: Optimized for NVIDIA GH200 with CUDA support
- **Queue Management**: Persistent job queue with Redis backend
- **Progress Tracking**: Real-time progress updates and job status
- **Multiple Output Formats**: Generates translated Markdown, HTML, and PDF
- **Containerized**: Single Docker container with all dependencies
- **Production Ready**: Includes monitoring, logging, and health checks

## Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Web Browser   │───▶│   FastAPI Web    │───▶│   Redis Queue   │
│                 │    │     Server       │    │                 │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                │                        │
                                ▼                        ▼
                       ┌──────────────────┐    ┌─────────────────┐
                       │   SQLite DB      │    │ Background      │
                       │  (Job Metadata)  │    │   Worker        │
                       └──────────────────┘    └─────────────────┘
                                                        │
                                                        ▼
                                               ┌─────────────────┐
                                               │  GPU Translation│
                                               │     Pipeline    │
                                               └─────────────────┘
```

## Processing Pipeline

1. **Upload**: PDF uploaded through web interface
2. **OCR** (if needed): `ocrmypdf` for text extraction and cleanup
3. **Conversion**: `docling` converts PDF to Markdown with images
4. **Translation**: GPU-accelerated translation using NLLB-200 or mBART
5. **PDF Generation**: `pandoc` creates final translated PDF

## Quick Start

### Prerequisites

- Docker with NVIDIA Container Runtime
- NVIDIA GPU with CUDA support
- At least 16GB GPU memory (for NLLB-200-3.3B model)
- 50GB+ disk space for models and processing

### Deployment

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd translate-pdfs
   ```

2. **Configure environment**:
   ```bash
   cp .env.example .env
   # Edit .env with your settings
   ```

3. **Deploy with the deployment script**:
   ```bash
   ./scripts/deploy.sh deploy
   ```

4. **Access the service**:
   - Web Interface: http://localhost
   - API Documentation: http://localhost/docs
   - Health Check: http://localhost/health

### Manual Docker Deployment

```bash
# Build the image
docker build -t pdf-translator .

# Run with Docker Compose
docker compose -f docker-compose.prod.yml up -d

# Or run manually with GPU support
docker run -d \
  --name pdf-translator \
  --gpus all \
  -p 80:80 \
  -p 8000:8000 \
  -v ./uploads:/app/uploads \
  -v ./outputs:/app/outputs \
  -v ./logs:/app/logs \
  pdf-translator
```

## Configuration

Key environment variables (see `.env.example` for full list):

```bash
# Model Configuration
PDF_TRANSLATE_MODEL_NAME=facebook/nllb-200-3.3B
PDF_TRANSLATE_MODEL_REVISION=refs/pr/17
PDF_TRANSLATE_MAX_TOKENS_PER_BATCH=64000

# File Handling
PDF_TRANSLATE_MAX_FILE_SIZE=104857600  # 100MB
PDF_TRANSLATE_CLEANUP_AFTER_HOURS=24

# Queue Configuration
PDF_TRANSLATE_REDIS_URL=redis://localhost:6379/0
PDF_TRANSLATE_DATABASE_URL=sqlite:///./data/jobs.db
```

## API Usage

### Upload a Document

```bash
curl -X POST "http://localhost/api/jobs" \
  -F "file=@document.pdf" \
  -F "document_type=text_pdf"
```

### Check Job Status

```bash
curl "http://localhost/api/jobs/{job_id}"
```

### Download Results

```bash
curl "http://localhost/api/jobs/{job_id}/download/document_fr.pdf" \
  -o translated_document.pdf
```

## Development

### Local Development Setup

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Install external tools**:
   ```bash
   # Ubuntu/Debian
   sudo apt-get install tesseract-ocr pandoc
   pip install ocrmypdf docling
   ```

3. **Start Redis**:
   ```bash
   redis-server
   ```

4. **Run the application**:
   ```bash
   python main.py
   ```

5. **Start worker** (in another terminal):
   ```bash
   python -m src.workers.translation_worker
   ```

### Running Tests

```bash
# Run all tests
python run_tests.py

# Run with linting
python run_tests.py --lint

# Run specific test file
pytest tests/test_api.py -v
```

### Testing Without GPU

The service includes mock implementations for development without GPU:

```bash
# Set environment for CPU testing
export PDF_TRANSLATE_MODEL_NAME=facebook/mbart-large-50-many-to-many-mmt
python run_tests.py
```

## Monitoring and Maintenance

### Service Management

```bash
# Check service status
./scripts/deploy.sh status

# View logs
./scripts/deploy.sh logs

# View specific service logs
./scripts/deploy.sh logs worker

# Update service
./scripts/deploy.sh update

# Stop service
./scripts/deploy.sh stop
```

### Health Monitoring

- **Health Check**: `GET /health` - Basic service health
- **Readiness Check**: `GET /health/ready` - Service readiness
- **Queue Status**: Monitor Redis queue length and failed jobs

### Log Files

- Application: `/app/logs/app.log`
- Worker: `/var/log/supervisor/worker.log`
- Redis: `/var/log/supervisor/redis.log`
- Nginx: `/var/log/nginx/access.log`

## Troubleshooting

### Common Issues

1. **GPU Memory Issues**:
   - Reduce `PDF_TRANSLATE_MAX_TOKENS_PER_BATCH`
   - Use smaller model (mBART instead of NLLB-3.3B)

2. **OCR Failures**:
   - Check tesseract installation
   - Verify PDF is not corrupted
   - Try different document type

3. **Translation Timeouts**:
   - Increase job timeout in worker
   - Check GPU utilization
   - Monitor memory usage

4. **Queue Issues**:
   - Restart Redis service
   - Check Redis connectivity
   - Clear failed jobs if needed

### Performance Tuning

- **GPU Optimization**: Adjust batch sizes based on GPU memory
- **Concurrent Jobs**: Scale worker processes based on workload
- **Model Selection**: Choose appropriate model size for your hardware
- **Disk I/O**: Use SSD storage for better performance

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Run the test suite
6. Submit a pull request

## License

[Add your license information here]

## Document Types

### Text PDF
- PDFs with selectable text
- No OCR processing needed
- Fastest processing option

### Text Image PDF
- PDFs with images of text (clean scans)
- Requires OCR but pages are clean
- Uses `ocrmypdf --skip-text`

### Scan
- Scanned documents that may need cleanup
- Requires OCR with preprocessing
- Uses `ocrmypdf --rotate-pages --deskew --clean`

## Model Information

### Supported Models

1. **NLLB-200-3.3B** (Recommended for production)
   - Best translation quality
   - Requires 16GB+ GPU memory
   - Slower but more accurate

2. **NLLB-200-1.3B** (Balanced option)
   - Good quality with lower memory requirements
   - Requires 8GB+ GPU memory
   - Good balance of speed and quality

3. **mBART-50** (Development/testing)
   - Fastest option
   - Requires 4GB+ GPU memory
   - Lower quality but good for testing

## Support

For issues and questions:
- Check the troubleshooting section
- Review logs for error details
- Open an issue on the repository
