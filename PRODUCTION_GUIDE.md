# Production Deployment Guide

This guide covers deploying the PDF Translation Service in a production environment with all security, monitoring, and reliability features enabled.

## 🚀 Quick Production Deployment

```bash
# 1. Clone and setup
git clone https://github.com/jdesfossez/translate-pdfs.git
cd translate-pdfs

# 2. Configure production environment
cp .env.production .env
# Edit .env with your specific settings

# 3. Deploy with production configuration
./scripts/deploy.sh deploy

# 4. Verify deployment
./scripts/deploy.sh status
curl http://localhost/health
```

## 📋 Pre-Deployment Checklist

### System Requirements
- [ ] Docker 24.0+ installed
- [ ] Docker Compose v2+ installed
- [ ] NVIDIA Container Runtime (for GPU support)
- [ ] 8GB+ RAM available
- [ ] 50GB+ disk space available
- [ ] Ports 80, 8000, 6379 available

### Security Configuration
- [ ] Review and customize `.env` file
- [ ] Set appropriate file size limits
- [ ] Configure rate limiting
- [ ] Review allowed file types
- [ ] Set up log rotation
- [ ] Configure backup strategy

### Performance Tuning
- [ ] Adjust worker count based on hardware
- [ ] Set appropriate batch sizes
- [ ] Configure memory limits
- [ ] Set up monitoring

## 🔧 Configuration

### Environment Variables

Copy `.env.production` to `.env` and customize:

```bash
# Critical Settings
PDF_TRANSLATE_DEBUG=false                    # Disable debug in production
PDF_TRANSLATE_MAX_FILE_SIZE=104857600       # 100MB limit
PDF_TRANSLATE_MAX_CONCURRENT_JOBS=3         # Adjust based on resources
PDF_TRANSLATE_CLEANUP_AFTER_HOURS=168       # 7 days retention

# Security Settings
PDF_TRANSLATE_RATE_LIMIT_REQUESTS=5         # 5 uploads per window
PDF_TRANSLATE_RATE_LIMIT_WINDOW=300         # 5 minute window

# Performance Settings
PDF_TRANSLATE_MAX_TOKENS_PER_BATCH=64000    # Adjust for GPU memory
PDF_TRANSLATE_WORKER_TIMEOUT=14400          # 4 hour job timeout
```

### Resource Limits

Edit `docker-compose.prod.yml` to set resource limits:

```yaml
services:
  pdf-translator:
    deploy:
      resources:
        limits:
          memory: 8G
          cpus: '4'
        reservations:
          memory: 4G
          cpus: '2'
```

## 🛡️ Security Features

### File Upload Security
- ✅ Filename sanitization and validation
- ✅ File content validation (magic byte checking)
- ✅ Path traversal protection
- ✅ File size limits
- ✅ Rate limiting per IP
- ✅ Secure file storage

### System Security
- ✅ Non-root container execution
- ✅ Read-only filesystem where possible
- ✅ Minimal attack surface
- ✅ Input validation and sanitization
- ✅ Comprehensive logging

## 📊 Monitoring and Health Checks

### Health Endpoints

```bash
# Basic health check
curl http://localhost/health

# Detailed system information
curl http://localhost/health/detailed

# Kubernetes-style checks
curl http://localhost/health/ready
curl http://localhost/health/live
```

### Monitoring Metrics

The health endpoints provide:
- System resource usage (CPU, memory, disk)
- Queue statistics (pending, processing, failed jobs)
- Database connectivity
- Redis connectivity
- GPU availability and usage

### Log Files

Logs are stored in `./logs/`:
- `app.log` - Application logs with rotation
- `errors.log` - Error-only logs
- Structured logging for easy parsing

## 🔄 Job Recovery and Persistence

### Automatic Recovery
- Jobs are automatically recovered after container restarts
- Orphaned jobs are re-queued
- Failed jobs can be retried via web interface
- Old completed jobs are automatically cleaned up

### Manual Recovery
```bash
# Check queue status
./scripts/deploy.sh logs worker

# Access recovery tools
docker exec -it pdf-translator-worker-1 python3 -c "
from src.services.job_recovery import JobRecoveryService
recovery = JobRecoveryService()
print('Recovered:', recovery.recover_orphaned_jobs())
print('Cleaned:', recovery.cleanup_old_jobs())
"
```

## 🎛️ Task Management

### Web Interface Features
- ✅ Real-time job progress tracking
- ✅ Cancel pending/processing jobs
- ✅ Retry failed jobs
- ✅ Bulk operations (cancel all pending)
- ✅ Download completed translations
- ✅ Auto-refresh job list

### API Operations
```bash
# List all jobs
curl http://localhost/api/jobs

# Get specific job
curl http://localhost/api/jobs/{job_id}

# Cancel job
curl -X DELETE http://localhost/api/jobs/{job_id}

# Retry failed job
curl -X POST http://localhost/api/jobs/{job_id}/retry
```

## 🚨 Troubleshooting

### Common Issues

1. **Container won't start**
   ```bash
   # Check logs
   ./scripts/deploy.sh logs
   
   # Check system resources
   docker system df
   free -h
   ```

2. **Jobs not processing**
   ```bash
   # Check worker status
   ./scripts/deploy.sh logs worker
   
   # Check Redis connectivity
   docker exec -it pdf-translator-redis-1 redis-cli ping
   ```

3. **High memory usage**
   ```bash
   # Monitor resource usage
   docker stats
   
   # Adjust batch size in .env
   PDF_TRANSLATE_MAX_TOKENS_PER_BATCH=32000
   ```

4. **Disk space issues**
   ```bash
   # Check disk usage
   df -h
   
   # Clean up old files
   ./scripts/deploy.sh cleanup
   
   # Reduce retention period
   PDF_TRANSLATE_CLEANUP_AFTER_HOURS=72  # 3 days
   ```

### Performance Optimization

1. **GPU Optimization**
   ```bash
   # Check GPU usage
   nvidia-smi
   
   # Optimize for your GPU memory
   PDF_TRANSLATE_MAX_TOKENS_PER_BATCH=128000  # For high-memory GPUs
   PDF_TRANSLATE_BATCH_SIZE=64                # Larger batches
   ```

2. **CPU Optimization**
   ```bash
   # For CPU-only deployment
   PDF_TRANSLATE_CPU_LOAD_THEN_GPU=false
   PDF_TRANSLATE_MAX_TOKENS_PER_BATCH=16000   # Smaller batches
   ```

## 📈 Scaling

### Horizontal Scaling
```yaml
# Scale workers
services:
  worker:
    deploy:
      replicas: 3  # Multiple worker instances
```

### Load Balancing
```yaml
# Add nginx load balancer
services:
  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
```

## 🔐 Backup and Recovery

### Database Backup
```bash
# Backup SQLite database
cp ./data/jobs.db ./backups/jobs_$(date +%Y%m%d_%H%M%S).db

# Backup configuration
cp .env ./backups/env_$(date +%Y%m%d_%H%M%S)
```

### Automated Backup Script
```bash
#!/bin/bash
# Add to crontab: 0 2 * * * /path/to/backup.sh

BACKUP_DIR="/backup/pdf-translator"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p "$BACKUP_DIR"
cp ./data/jobs.db "$BACKUP_DIR/jobs_$DATE.db"
cp .env "$BACKUP_DIR/env_$DATE"

# Keep only 30 days of backups
find "$BACKUP_DIR" -type f -mtime +30 -delete
```

## 📞 Support

For production support:
1. Check logs: `./scripts/deploy.sh logs`
2. Verify health: `curl http://localhost/health/detailed`
3. Review configuration: `cat .env`
4. Check resources: `docker stats`

For additional help, refer to the main README.md or create an issue on GitHub.
