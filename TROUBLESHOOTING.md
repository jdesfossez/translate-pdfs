# Troubleshooting Guide

## Common Issues and Solutions

### 1. Jobs Not Processing (Worker Issues)

**Symptoms:**
- Jobs get queued but never start processing
- Worker appears to be running but not picking up jobs
- No progress updates on uploaded PDFs

**Debugging Steps:**

1. **Check worker logs:**
   ```bash
   docker compose -f docker-compose.prod.yml logs pdf-translator
   ```

2. **Run debug mode:**
   ```bash
   docker compose -f docker-compose.debug.yml up
   ```

3. **Check Redis connectivity:**
   ```bash
   docker exec -it translate-pdfs-pdf-translator-1 python3 /app/debug_worker.py
   ```

4. **Test worker startup:**
   ```bash
   docker exec -it translate-pdfs-pdf-translator-1 python3 /app/test_worker_startup.py
   ```

**Common Fixes:**
- Ensure Redis is running: Check supervisor logs
- Verify Redis URL in environment variables
- Check if worker process is actually running
- Restart the container: `docker compose restart`

### 2. Container Build Issues

**Symptoms:**
- Docker build fails
- Missing dependencies
- Permission errors

**Solutions:**

1. **Clean build:**
   ```bash
   docker system prune -a
   docker compose build --no-cache
   ```

2. **Check system requirements:**
   - Docker 20.10+
   - Docker Compose 2.0+
   - For GPU: NVIDIA Docker runtime

3. **Build with specific Dockerfile:**
   ```bash
   # CPU-only
   docker build -f Dockerfile -t translate-pdfs .
   
   # GPU-enabled
   docker build -f Dockerfile.gpu -t translate-pdfs-gpu .
   ```

### 3. GPU Issues

**Symptoms:**
- CUDA not available
- GPU not detected
- Out of memory errors

**Debugging:**

1. **Check GPU availability:**
   ```bash
   docker exec -it translate-pdfs-pdf-translator-1 python3 /app/check_gpu.py
   ```

2. **Verify NVIDIA Docker runtime:**
   ```bash
   docker run --rm --gpus all nvidia/cuda:12.1-base-ubuntu22.04 nvidia-smi
   ```

**Solutions:**
- Install NVIDIA Docker runtime
- Use GPU-enabled compose file: `docker-compose.gpu.yml`
- Reduce batch size if out of memory
- Fall back to CPU-only mode

### 4. Model Loading Issues

**Symptoms:**
- Long startup times
- Model download failures
- Translation errors

**Solutions:**

1. **Use smaller model for testing:**
   ```bash
   export PDF_TRANSLATE_MODEL_NAME=facebook/mbart-large-50-many-to-many-mmt
   ```

2. **Pre-download models:**
   ```bash
   docker exec -it translate-pdfs-pdf-translator-1 python3 -c "
   from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
   model_name = 'facebook/mbart-large-50-many-to-many-mmt'
   AutoTokenizer.from_pretrained(model_name)
   AutoModelForSeq2SeqLM.from_pretrained(model_name)
   "
   ```

3. **Check disk space:**
   Models can be 1-10GB, ensure sufficient space

### 5. Permission Issues

**Symptoms:**
- Cannot write to directories
- Database creation fails
- File upload errors

**Solutions:**

1. **Fix directory permissions:**
   ```bash
   sudo chown -R 1000:1000 uploads outputs logs data
   chmod -R 755 uploads outputs logs data
   ```

2. **Check container user:**
   ```bash
   docker exec -it translate-pdfs-pdf-translator-1 id
   ```

### 6. Memory Issues

**Symptoms:**
- Container killed (OOMKilled)
- Translation fails on large files
- Slow processing

**Solutions:**

1. **Increase Docker memory limit:**
   - Docker Desktop: Settings > Resources > Memory
   - Linux: Modify `/etc/docker/daemon.json`

2. **Reduce batch size:**
   ```bash
   export PDF_TRANSLATE_MAX_TOKENS_PER_BATCH=16000
   ```

3. **Use CPU-only mode:**
   ```bash
   export PDF_TRANSLATE_CPU_LOAD_THEN_GPU=false
   ```

## Debug Commands

### Container Inspection
```bash
# Check running processes
docker exec -it translate-pdfs-pdf-translator-1 ps aux

# Check supervisor status
docker exec -it translate-pdfs-pdf-translator-1 supervisorctl status

# View supervisor logs
docker exec -it translate-pdfs-pdf-translator-1 tail -f /var/log/supervisor/worker.log

# Interactive shell
docker exec -it translate-pdfs-pdf-translator-1 bash
```

### Queue Inspection
```bash
# Check Redis queue
docker exec -it translate-pdfs-pdf-translator-1 python3 -c "
import redis
from rq import Queue
r = redis.from_url('redis://localhost:6379/0')
q = Queue('pdf_translation', connection=r)
print(f'Queue length: {len(q)}')
print(f'Jobs: {[job.id for job in q.jobs]}')
"
```

### Manual Job Testing
```bash
# Test job queue manually
docker exec -it translate-pdfs-pdf-translator-1 python3 /app/test_queue.py
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PDF_TRANSLATE_DEBUG` | `false` | Enable debug mode |
| `PDF_TRANSLATE_REDIS_URL` | `redis://localhost:6379/0` | Redis connection |
| `PDF_TRANSLATE_MODEL_NAME` | `facebook/mbart-large-50-many-to-many-mmt` | Translation model |
| `PDF_TRANSLATE_CPU_LOAD_THEN_GPU` | `true` | Load model on CPU first |
| `PDF_TRANSLATE_MAX_TOKENS_PER_BATCH` | `64000` | Batch size limit |

## Performance Tuning

### For CPU-only environments:
```bash
export PDF_TRANSLATE_CPU_LOAD_THEN_GPU=false
export PDF_TRANSLATE_MAX_TOKENS_PER_BATCH=16000
export PDF_TRANSLATE_MODEL_NAME=facebook/mbart-large-50-many-to-many-mmt
```

### For GPU environments:
```bash
export PDF_TRANSLATE_CPU_LOAD_THEN_GPU=true
export PDF_TRANSLATE_MAX_TOKENS_PER_BATCH=64000
export PDF_TRANSLATE_MODEL_NAME=facebook/nllb-200-3.3B
```

## Getting Help

1. **Check logs first:**
   ```bash
   docker compose logs --tail=100 pdf-translator
   ```

2. **Run comprehensive diagnostics:**
   ```bash
   docker exec -it translate-pdfs-pdf-translator-1 python3 /app/startup_debug.py
   ```

3. **Create issue with:**
   - Docker version: `docker --version`
   - Compose version: `docker compose version`
   - System info: `uname -a`
   - Error logs and diagnostic output
