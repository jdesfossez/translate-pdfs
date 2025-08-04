# Deployment Guide

This guide covers deploying the PDF Translation Service on a production server with NVIDIA GH200 GPU.

## Server Requirements

### Hardware
- NVIDIA GH200 GPU (or compatible CUDA GPU)
- 32GB+ RAM (64GB recommended)
- 100GB+ SSD storage
- 8+ CPU cores

### Software
- Ubuntu 22.04 LTS
- Docker 24.0+
- NVIDIA Container Runtime
- CUDA 12.1+

## Pre-deployment Setup

### 1. Install Docker

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Add user to docker group
sudo usermod -aG docker $USER
newgrp docker
```

### 2. Install NVIDIA Container Runtime

```bash
# Add NVIDIA package repository
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | sudo tee /etc/apt/sources.list.d/nvidia-docker.list

# Install nvidia-docker2
sudo apt update
sudo apt install -y nvidia-docker2

# Restart Docker
sudo systemctl restart docker

# Test GPU access
docker run --rm --gpus all nvidia/cuda:12.1-base-ubuntu22.04 nvidia-smi
```

### 3. Verify Docker Compose

```bash
# Docker Compose is included with Docker Desktop and recent Docker installations
# Verify installation (note: using 'docker compose' not 'docker-compose')
docker compose version
```

**Note**: This project uses the modern `docker compose` command (without hyphen) which is the current standard. If you have an older installation that only supports `docker-compose` (with hyphen), please update Docker to a recent version.

## Production Deployment

### 1. Clone and Configure

```bash
# Clone repository
git clone <repository-url> /opt/pdf-translator
cd /opt/pdf-translator

# Create environment file
cp .env.example .env

# Edit configuration
nano .env
```

### 2. Key Production Settings

```bash
# .env file for production
PDF_TRANSLATE_DEBUG=false
PDF_TRANSLATE_HOST=0.0.0.0
PDF_TRANSLATE_PORT=8000

# Use production model
PDF_TRANSLATE_MODEL_NAME=facebook/nllb-200-3.3B
PDF_TRANSLATE_MODEL_REVISION=refs/pr/17
PDF_TRANSLATE_USE_SAFETENSORS=true
PDF_TRANSLATE_CPU_LOAD_THEN_GPU=true

# Optimize for GH200
PDF_TRANSLATE_MAX_TOKENS_PER_BATCH=64000
PDF_TRANSLATE_BATCH_SIZE=48

# File limits
PDF_TRANSLATE_MAX_FILE_SIZE=104857600  # 100MB
PDF_TRANSLATE_CLEANUP_AFTER_HOURS=24

# Database and queue
PDF_TRANSLATE_DATABASE_URL=sqlite:///./data/jobs.db
PDF_TRANSLATE_REDIS_URL=redis://localhost:6379/0
```

### 3. Deploy Service

```bash
# Make deployment script executable
chmod +x scripts/deploy.sh

# Deploy (builds, tests, and starts service)
./scripts/deploy.sh deploy
```

### 4. Verify Deployment

```bash
# Check service status
./scripts/deploy.sh status

# Check logs
./scripts/deploy.sh logs

# Test health endpoint
curl http://localhost/health

# Test GPU detection
curl http://localhost/health | jq '.gpu_available'
```

## SSL/TLS Setup (Optional)

### Using Let's Encrypt with Nginx

1. **Install Certbot**:
```bash
sudo apt install certbot python3-certbot-nginx
```

2. **Update Nginx configuration**:
```bash
# Edit docker/nginx.conf to include your domain
server_name your-domain.com;
```

3. **Obtain certificate**:
```bash
sudo certbot --nginx -d your-domain.com
```

4. **Rebuild and redeploy**:
```bash
./scripts/deploy.sh update
```

## Monitoring Setup

### 1. Log Rotation

```bash
# Create logrotate configuration
sudo tee /etc/logrotate.d/pdf-translator << EOF
/opt/pdf-translator/logs/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    copytruncate
}
EOF
```

### 2. System Service (Optional)

Create a systemd service for automatic startup:

```bash
sudo tee /etc/systemd/system/pdf-translator.service << EOF
[Unit]
Description=PDF Translation Service
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/pdf-translator
ExecStart=/opt/pdf-translator/scripts/deploy.sh deploy
ExecStop=/opt/pdf-translator/scripts/deploy.sh stop
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
EOF

# Enable and start service
sudo systemctl enable pdf-translator.service
sudo systemctl start pdf-translator.service
```

### 3. Health Monitoring Script

```bash
#!/bin/bash
# /opt/pdf-translator/scripts/health-check.sh

HEALTH_URL="http://localhost/health"
LOG_FILE="/opt/pdf-translator/logs/health-check.log"

if ! curl -f -s "$HEALTH_URL" > /dev/null; then
    echo "$(date): Health check failed, restarting service" >> "$LOG_FILE"
    cd /opt/pdf-translator
    ./scripts/deploy.sh stop
    sleep 10
    ./scripts/deploy.sh deploy
else
    echo "$(date): Health check passed" >> "$LOG_FILE"
fi
```

Add to crontab:
```bash
# Check every 5 minutes
*/5 * * * * /opt/pdf-translator/scripts/health-check.sh
```

## Performance Optimization

### 1. GPU Memory Optimization

Monitor GPU memory usage:
```bash
# Watch GPU utilization
watch -n 1 nvidia-smi

# Adjust batch sizes if needed
# Edit .env and restart service
```

### 2. Disk Space Management

```bash
# Set up automatic cleanup
# Add to crontab
0 2 * * * find /opt/pdf-translator/uploads -type f -mtime +1 -delete
0 2 * * * find /opt/pdf-translator/outputs -type f -mtime +7 -delete
```

### 3. Model Caching

```bash
# Pre-download models to avoid startup delays
docker run --rm --gpus all \
  -v model_cache:/home/appuser/.cache \
  pdf-translator:latest \
  python3 -c "from src.services.translation_service import TranslationService; s = TranslationService(); s.load_model()"
```

## Backup and Recovery

### 1. Backup Script

```bash
#!/bin/bash
# /opt/pdf-translator/scripts/backup.sh

BACKUP_DIR="/backup/pdf-translator"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p "$BACKUP_DIR"

# Backup database
cp /opt/pdf-translator/data/jobs.db "$BACKUP_DIR/jobs_$DATE.db"

# Backup configuration
cp /opt/pdf-translator/.env "$BACKUP_DIR/env_$DATE"

# Backup important outputs (last 7 days)
find /opt/pdf-translator/outputs -type f -mtime -7 | \
  tar -czf "$BACKUP_DIR/outputs_$DATE.tar.gz" -T -

# Clean old backups (keep 30 days)
find "$BACKUP_DIR" -type f -mtime +30 -delete
```

### 2. Recovery Process

```bash
# Stop service
./scripts/deploy.sh stop

# Restore database
cp /backup/pdf-translator/jobs_YYYYMMDD_HHMMSS.db /opt/pdf-translator/data/jobs.db

# Restore configuration
cp /backup/pdf-translator/env_YYYYMMDD_HHMMSS /opt/pdf-translator/.env

# Restart service
./scripts/deploy.sh deploy
```

## Troubleshooting

### Common Production Issues

1. **Service won't start**:
   ```bash
   # Check Docker daemon
   sudo systemctl status docker
   
   # Check GPU access
   docker run --rm --gpus all nvidia/cuda:12.1-base-ubuntu22.04 nvidia-smi
   
   # Check logs
   ./scripts/deploy.sh logs
   ```

2. **Out of GPU memory**:
   ```bash
   # Reduce batch size in .env
   PDF_TRANSLATE_MAX_TOKENS_PER_BATCH=32000
   PDF_TRANSLATE_BATCH_SIZE=24
   
   # Restart service
   ./scripts/deploy.sh update
   ```

3. **Queue not processing**:
   ```bash
   # Check Redis
   docker exec -it $(docker ps -q -f name=redis) redis-cli ping
   
   # Check worker logs
   ./scripts/deploy.sh logs worker

   # Restart worker
   docker compose -f docker-compose.prod.yml restart worker
   ```

### Performance Monitoring

```bash
# Monitor system resources
htop

# Monitor GPU
nvidia-smi -l 1

# Monitor disk usage
df -h

# Monitor service logs
tail -f /opt/pdf-translator/logs/app.log
```

## Security Considerations

1. **Firewall Configuration**:
   ```bash
   # Allow only necessary ports
   sudo ufw allow 22    # SSH
   sudo ufw allow 80    # HTTP
   sudo ufw allow 443   # HTTPS (if using SSL)
   sudo ufw enable
   ```

2. **File Upload Security**:
   - Service validates file types and sizes
   - Files are processed in isolated containers
   - Automatic cleanup prevents disk filling

3. **Network Security**:
   - Use reverse proxy with SSL
   - Consider VPN for internal access
   - Monitor access logs

## Maintenance

### Regular Tasks

1. **Weekly**:
   - Check disk space
   - Review error logs
   - Update system packages

2. **Monthly**:
   - Update Docker images
   - Review and clean old files
   - Check backup integrity

3. **Quarterly**:
   - Update service code
   - Review security settings
   - Performance optimization review
