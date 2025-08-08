#!/bin/bash
set -e

# PDF Translation Service Deployment Script

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if Docker is available
check_docker() {
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed or not in PATH"
        exit 1
    fi
    
    if ! docker compose version &> /dev/null; then
        log_error "Docker Compose is not available or not in PATH"
        exit 1
    fi

    log_info "Docker and Docker Compose are available"
}

# Check if NVIDIA Docker runtime is available
check_nvidia_docker() {
    if ! docker info | grep -q nvidia; then
        log_warn "NVIDIA Docker runtime not detected. GPU acceleration may not work."
        log_warn "Install nvidia-docker2 for GPU support."
    else
        log_info "NVIDIA Docker runtime detected"
    fi
}

# Build the Docker image
build_image() {
    log_info "Building Docker image..."
    cd "$PROJECT_DIR"
    
    docker build -t pdf-translator:latest .
    
    if [ $? -eq 0 ]; then
        log_info "Docker image built successfully"
    else
        log_error "Failed to build Docker image"
        exit 1
    fi
}

# Run tests in container
run_tests() {
    log_info "Running tests in container..."
    
    docker run --rm \
        -v "$PROJECT_DIR:/app" \
        pdf-translator:latest test
    
    if [ $? -eq 0 ]; then
        log_info "Tests passed"
    else
        log_error "Tests failed"
        exit 1
    fi
}

# Deploy the service
deploy() {
    log_info "Deploying PDF Translation Service..."
    cd "$PROJECT_DIR"
    
    # Create necessary directories
    mkdir -p uploads outputs logs data
    
    # Copy environment file if it doesn't exist
    if [ ! -f .env ]; then
        log_info "Creating .env file from template..."
        cp .env.example .env
        log_warn "Please review and update .env file with your settings"
    fi
    
    # Start Redis first
    log_info "Starting Redis..."
    docker compose -f docker-compose.prod.yml up -d redis

    # Wait for Redis to be ready
    log_info "Waiting for Redis to be ready..."
    for i in {1..30}; do
        if docker compose -f docker-compose.prod.yml exec -T redis redis-cli ping >/dev/null 2>&1; then
            log_info "Redis is ready"
            break
        fi
        if [ $i -eq 30 ]; then
            log_error "Redis failed to start within 30 seconds"
            docker compose -f docker-compose.prod.yml logs redis
            exit 1
        fi
        sleep 1
    done

    # Start the main application
    log_info "Starting PDF Translator application..."
    docker compose -f docker-compose.prod.yml up -d pdf-translator

    # Wait for application to be ready
    log_info "Waiting for application to be ready..."
    for i in {1..60}; do
        if curl -f http://localhost/health >/dev/null 2>&1; then
            log_info "Application is ready"
            break
        fi
        if [ $i -eq 60 ]; then
            log_warn "Application health check timeout, but continuing..."
            break
        fi
        sleep 2
    done

    # Start the worker
    log_info "Starting worker..."
    docker compose -f docker-compose.prod.yml up -d worker

    # Final status check
    if docker compose -f docker-compose.prod.yml ps | grep -q "Up"; then
        log_info "Service deployed successfully"
        log_info "Access the service at: http://localhost"
        log_info "API documentation at: http://localhost/docs"

        # Show service status
        echo ""
        log_info "Service Status:"
        docker compose -f docker-compose.prod.yml ps
    else
        log_error "Failed to deploy service"
        docker compose -f docker-compose.prod.yml logs
        exit 1
    fi
}

# Stop the service
stop() {
    log_info "Stopping PDF Translation Service..."
    cd "$PROJECT_DIR"

    docker compose -f docker-compose.prod.yml down

    log_info "Service stopped"
}

# Restart the service
restart() {
    log_info "Restarting PDF Translation Service..."
    stop
    sleep 2
    deploy
}

# Show service status
status() {
    log_info "Service Status:"
    cd "$PROJECT_DIR"

    echo "📋 Container Status:"
    docker compose -f docker-compose.prod.yml ps

    echo ""
    echo "📋 Redis Health:"
    if docker compose -f docker-compose.prod.yml exec -T redis redis-cli ping >/dev/null 2>&1; then
        echo "✅ Redis: Healthy"
    else
        echo "❌ Redis: Unhealthy"
    fi

    echo ""
    echo "📋 Application Health:"
    if curl -f http://localhost/health >/dev/null 2>&1; then
        echo "✅ Application: Healthy"
        curl -s http://localhost/health | jq '.' 2>/dev/null || curl -s http://localhost/health
    else
        echo "❌ Application: Unhealthy"
    fi

    echo ""
    echo "📋 Worker Status:"
    WORKER_LOGS=$(docker compose -f docker-compose.prod.yml logs --tail=5 worker 2>/dev/null)
    if echo "$WORKER_LOGS" | grep -q "Starting worker"; then
        echo "✅ Worker: Running"
    else
        echo "❌ Worker: Not running or no recent activity"
    fi
}

# Show service logs
logs() {
    cd "$PROJECT_DIR"

    if [ -n "$1" ]; then
        docker compose -f docker-compose.prod.yml logs -f "$1"
    else
        docker compose -f docker-compose.prod.yml logs -f
    fi
}

# Update the service
update() {
    log_info "Updating PDF Translation Service..."
    
    # Pull latest code (if in git repo)
    if [ -d "$PROJECT_DIR/.git" ]; then
        log_info "Pulling latest code..."
        cd "$PROJECT_DIR"
        git pull
    fi
    
    # Rebuild and redeploy
    build_image
    run_tests
    
    log_info "Restarting service..."
    stop
    deploy
}

# Cleanup old containers and images
cleanup() {
    log_info "Cleaning up old containers and images..."

    # Stop and remove containers
    docker compose -f docker-compose.prod.yml down --remove-orphans

    # Remove old images (including dangling and unused)
    log_info "Removing dangling images..."
    docker image prune -f

    # Remove unused images (more aggressive cleanup)
    log_info "Removing unused images..."
    docker image prune -a -f --filter "until=24h"

    # Remove unused volumes
    log_info "Removing unused volumes..."
    docker volume prune -f

    # Remove unused networks
    log_info "Removing unused networks..."
    docker network prune -f

    log_info "Cleanup completed"
}

# Show help
show_help() {
    echo "PDF Translation Service Deployment Script"
    echo ""
    echo "Usage: $0 [COMMAND]"
    echo ""
    echo "Commands:"
    echo "  build     Build the Docker image"
    echo "  test      Run tests in container"
    echo "  deploy    Deploy the service"
    echo "  stop      Stop the service"
    echo "  restart   Restart the service"
    echo "  status    Show service status"
    echo "  logs      Show service logs (optionally specify service name)"
    echo "  update    Update and redeploy the service"
    echo "  cleanup   Clean up old containers and images"
    echo "  help      Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 deploy          # Deploy the service"
    echo "  $0 logs worker     # Show worker logs"
    echo "  $0 update          # Update and redeploy"
}

# Main script logic
main() {
    case "${1:-help}" in
        build)
            check_docker
            build_image
            ;;
        test)
            check_docker
            build_image
            run_tests
            ;;
        deploy)
            check_docker
            check_nvidia_docker
            build_image
            run_tests
            deploy
            ;;
        stop)
            check_docker
            stop
            ;;
        restart)
            check_docker
            restart
            ;;
        status)
            check_docker
            status
            ;;
        logs)
            check_docker
            logs "$2"
            ;;
        update)
            check_docker
            check_nvidia_docker
            update
            ;;
        cleanup)
            check_docker
            cleanup
            ;;
        help|--help|-h)
            show_help
            ;;
        *)
            log_error "Unknown command: $1"
            show_help
            exit 1
            ;;
    esac
}

# Run main function
main "$@"
