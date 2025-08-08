# Deployment Environment Guide

This document describes the different deployment configurations available for the PDF Translation Service.

## Available Configurations

### 1. Development Environment (`docker-compose.yml`)
**Use case**: Local development and testing
**Hardware**: Any system with Docker
**Model**: facebook/nllb-200-3.3B (with GPU fallback to CPU)

```bash
docker compose up -d
```

**Features**:
- Hot reload enabled
- Debug logging
- GPU acceleration if available
- Automatic CPU fallback

### 2. Production Environment (`docker-compose.prod.yml`)
**Use case**: Production deployment with GPU acceleration
**Hardware**: NVIDIA GPU required
**Model**: facebook/nllb-200-3.3B (optimized for GPU)

```bash
docker compose -f docker-compose.prod.yml up -d
```

**Features**:
- Optimized for performance
- NGINX reverse proxy
- Health checks
- Restart policies
- Large batch sizes (64k tokens)

### 3. CPU-Only Production (`docker-compose.cpu.yml`)
**Use case**: Production deployment on CPU-only systems
**Hardware**: CPU-only servers (minimum 8GB RAM recommended)
**Model**: facebook/nllb-200-distilled-600M (smaller, CPU-optimized)

```bash
docker compose -f docker-compose.cpu.yml up -d
```

**Features**:
- Smaller model for CPU efficiency
- Reduced batch sizes (16k tokens)
- Lower memory requirements
- Suitable for cloud CPU instances

### 4. GPU-Enabled Production (`docker-compose.gpu.yml`)
**Use case**: High-performance GPU deployment
**Hardware**: NVIDIA GPU with 16GB+ VRAM
**Model**: facebook/nllb-200-3.3B (full model)

```bash
docker compose -f docker-compose.gpu.yml up -d
```

**Features**:
- Maximum performance
- Large model with best quality
- High batch sizes
- Requires NVIDIA Docker runtime

### 5. Debug Environment (`docker-compose.debug.yml`)
**Use case**: Troubleshooting and diagnostics
**Hardware**: Any system
**Model**: Same as production

```bash
docker compose -f docker-compose.debug.yml up
```

**Features**:
- Comprehensive system checks
- Debug shell access
- Detailed logging
- Diagnostic tools

## Environment-Specific Settings

### CPU-Only Optimizations
- **Model**: `facebook/nllb-200-distilled-600M` (600M parameters vs 3.3B)
- **Batch Size**: 8 (vs 48 for GPU)
- **Max Tokens per Batch**: 16,000 (vs 64,000 for GPU)
- **Max Input Tokens**: 512 (vs 950 for GPU)
- **Max New Tokens**: 256 (vs 400 for GPU)

### GPU Optimizations
- **Model**: `facebook/nllb-200-3.3B` (full model)
- **Batch Size**: 48
- **Max Tokens per Batch**: 64,000
- **Max Input Tokens**: 950
- **Max New Tokens**: 400
- **GPU Memory**: Requires 12GB+ VRAM

## Deployment Scripts

### Using the Deploy Script
The `scripts/deploy.sh` script provides automated deployment:

```bash
# Interactive deployment
./scripts/deploy.sh deploy

# Specific commands
./scripts/deploy.sh build    # Build images
./scripts/deploy.sh test     # Run tests
./scripts/deploy.sh status   # Check status
./scripts/deploy.sh logs     # View logs
./scripts/deploy.sh cleanup  # Clean up resources
```

### Manual Deployment
For manual control:

```bash
# Build and deploy
docker compose -f docker-compose.cpu.yml build
docker compose -f docker-compose.cpu.yml up -d

# Check status
docker compose -f docker-compose.cpu.yml ps
docker compose -f docker-compose.cpu.yml logs -f
```

## Hardware Requirements

### Minimum Requirements (CPU-only)
- **CPU**: 4 cores
- **RAM**: 8GB
- **Storage**: 20GB
- **Network**: 1Gbps for model downloads

### Recommended Requirements (GPU)
- **CPU**: 8 cores
- **RAM**: 16GB
- **GPU**: NVIDIA with 16GB VRAM (RTX 4090, A100, etc.)
- **Storage**: 50GB SSD
- **Network**: 1Gbps

### Cloud Instance Recommendations
- **AWS**: g4dn.xlarge (GPU) or c5.2xlarge (CPU)
- **GCP**: n1-standard-4 with T4 GPU or n1-highmem-4 (CPU)
- **Azure**: Standard_NC6s_v3 (GPU) or Standard_D4s_v3 (CPU)

## Performance Expectations

### CPU-Only Performance
- **Speed**: ~30 seconds per page
- **Quality**: Good (distilled model)
- **Memory**: ~4-6GB peak usage
- **Concurrent Jobs**: 1-2

### GPU Performance
- **Speed**: ~5-10 seconds per page
- **Quality**: Excellent (full model)
- **Memory**: ~12-16GB GPU VRAM
- **Concurrent Jobs**: 2-4

## Troubleshooting

### Common Issues
1. **Out of Memory**: Use CPU configuration or reduce batch sizes
2. **GPU Not Detected**: Check NVIDIA Docker runtime installation
3. **Slow Performance**: Verify hardware meets requirements
4. **Model Download Fails**: Check internet connection and disk space

### Debug Commands
```bash
# Check system resources
docker exec -it pdf-translator python3 /app/startup_debug.py

# Check GPU availability
docker exec -it pdf-translator python3 /app/check_gpu.py

# Monitor resource usage
docker stats

# View detailed logs
docker compose logs -f worker
```
