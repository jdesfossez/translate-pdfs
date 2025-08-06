#!/bin/bash
# PDF Translation Service Deployment Script

set -e

echo "[INFO] PDF Translation Service Deployment"
echo "========================================"

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "[ERROR] Docker is not installed. Please install Docker first."
    exit 1
fi

# Check if Docker Compose is installed
if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo "[ERROR] Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

# Function to create .env file
create_env_file() {
    if [ ! -f .env ]; then
        if [ -f .env.example ]; then
            echo "[INFO] Creating .env file from template..."
            cp .env.example .env
            echo "[INFO] .env file created. Please review and modify as needed."
        else
            echo "[WARN] .env.example not found. Creating basic .env file..."
            cat > .env << EOF
PDF_TRANSLATE_DEBUG=false
PDF_TRANSLATE_HOST=0.0.0.0
PDF_TRANSLATE_PORT=8000
PDF_TRANSLATE_DATABASE_URL=sqlite:///./data/jobs.db
PDF_TRANSLATE_REDIS_URL=redis://redis:6379/0
PDF_TRANSLATE_MODEL_NAME=facebook/mbart-large-50-many-to-many-mmt
PDF_TRANSLATE_USE_SAFETENSORS=true
PDF_TRANSLATE_CPU_LOAD_THEN_GPU=true
PDF_TRANSLATE_MAX_TOKENS_PER_BATCH=32000
EOF
            echo "[INFO] Basic .env file created."
        fi
    else
        echo "[INFO] .env file already exists."
    fi
}

# Function to create required directories
create_directories() {
    echo "[INFO] Creating required directories..."
    mkdir -p uploads outputs logs data
    chmod 755 uploads outputs logs data
    echo "[INFO] Directories created."
}

# Function to check system requirements
check_requirements() {
    echo "[INFO] Checking system requirements..."
    
    # Check available memory
    if command -v free &> /dev/null; then
        MEMORY_GB=$(free -g | awk '/^Mem:/{print $2}')
        if [ "$MEMORY_GB" -lt 4 ]; then
            echo "[WARN] System has less than 4GB RAM. Consider using a smaller model."
        fi
    fi
    
    # Check disk space
    if command -v df &> /dev/null; then
        DISK_SPACE_GB=$(df -BG . | awk 'NR==2 {print $4}' | sed 's/G//')
        if [ "$DISK_SPACE_GB" -lt 10 ]; then
            echo "[WARN] Less than 10GB disk space available. Models may require significant space."
        fi
    fi
    
    # Check for GPU
    if command -v nvidia-smi &> /dev/null; then
        echo "[INFO] NVIDIA GPU detected. You can use GPU-enabled deployment."
        GPU_AVAILABLE=true
    else
        echo "[INFO] No NVIDIA GPU detected. Using CPU-only deployment."
        GPU_AVAILABLE=false
    fi
}

# Function to select deployment mode
select_deployment_mode() {
    echo ""
    echo "Select deployment mode:"
    echo "1) Production (CPU-only)"
    echo "2) Debug mode (with diagnostics)"
    echo "3) GPU-enabled (requires NVIDIA Docker)"
    echo "4) Development (local testing)"
    
    read -p "Enter choice [1-4]: " choice
    
    case $choice in
        1)
            COMPOSE_FILE="docker-compose.prod.yml"
            MODE="production"
            ;;
        2)
            COMPOSE_FILE="docker-compose.debug.yml"
            MODE="debug"
            ;;
        3)
            if [ "$GPU_AVAILABLE" = true ]; then
                COMPOSE_FILE="docker-compose.gpu.yml"
                MODE="gpu"
            else
                echo "[ERROR] GPU not available. Please select a different mode."
                select_deployment_mode
                return
            fi
            ;;
        4)
            COMPOSE_FILE="docker-compose.yml"
            MODE="development"
            ;;
        *)
            echo "[ERROR] Invalid choice. Please select 1-4."
            select_deployment_mode
            return
            ;;
    esac
    
    echo "[INFO] Selected $MODE mode using $COMPOSE_FILE"
}

# Function to deploy the service
deploy_service() {
    echo "[INFO] Deploying PDF Translation Service..."
    
    # Build and start services
    if [ -f "$COMPOSE_FILE" ]; then
        echo "[INFO] Building containers..."
        docker-compose -f "$COMPOSE_FILE" build
        
        echo "[INFO] Starting services..."
        docker-compose -f "$COMPOSE_FILE" up -d
        
        echo "[INFO] Waiting for services to start..."
        sleep 10
        
        # Check if services are running
        if docker-compose -f "$COMPOSE_FILE" ps | grep -q "Up"; then
            echo "[SUCCESS] Services started successfully!"
            echo ""
            echo "Service URLs:"
            echo "- Web Interface: http://localhost"
            echo "- API: http://localhost:8000"
            echo "- Health Check: http://localhost:8000/health"
            echo ""
            echo "Useful commands:"
            echo "- View logs: docker-compose -f $COMPOSE_FILE logs -f"
            echo "- Stop services: docker-compose -f $COMPOSE_FILE down"
            echo "- Restart services: docker-compose -f $COMPOSE_FILE restart"
            
            if [ "$MODE" = "debug" ]; then
                echo "- Run diagnostics: docker-compose -f $COMPOSE_FILE exec pdf-translator python3 /app/startup_debug.py"
            fi
        else
            echo "[ERROR] Services failed to start. Check logs:"
            docker-compose -f "$COMPOSE_FILE" logs
            exit 1
        fi
    else
        echo "[ERROR] Compose file $COMPOSE_FILE not found."
        exit 1
    fi
}

# Main deployment flow
main() {
    create_env_file
    create_directories
    check_requirements
    select_deployment_mode
    deploy_service
}

# Run main function
main "$@"
