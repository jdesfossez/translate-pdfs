#!/bin/bash
set -e

# Function to wait for a service
wait_for_service() {
    local host=$1
    local port=$2
    local service_name=$3

    echo "Waiting for $service_name to be ready..."
    while ! nc -z $host $port; do
        sleep 1
    done
    echo "$service_name is ready!"
}

# Run startup debug if in debug mode
if [ "$PDF_TRANSLATE_DEBUG" = "true" ]; then
    echo "🔍 Running startup diagnostics..."
    python3 /app/startup_debug.py
fi

# Initialize database
echo "Initializing database..."
cd /app
python3 -c "from src.database import create_tables; create_tables()"

# Ensure directories exist
mkdir -p /app/uploads /app/outputs /app/logs /app/data
chown -R appuser:appuser /app/uploads /app/outputs /app/logs /app/data

# Create supervisor log directory
mkdir -p /var/log/supervisor
chown -R appuser:appuser /var/log/supervisor

case "$1" in
    app)
        echo "Starting full application stack..."
        exec supervisord -c /etc/supervisor/conf.d/app.conf
        ;;
    worker)
        echo "Starting worker only..."
        echo "🔍 Testing worker startup..."
        python3 /app/test_worker_startup.py
        echo "🚀 Starting worker..."
        exec su-exec appuser python3 -m src.workers.translation_worker
        ;;
    web)
        echo "Starting web server only..."
        exec su-exec appuser python3 main.py
        ;;
    test)
        echo "Running tests..."
        exec su-exec appuser python3 run_tests.py
        ;;
    debug)
        echo "Running debug checks..."
        python3 /app/startup_debug.py
        echo "Starting bash shell for debugging..."
        exec bash
        ;;
    bash)
        echo "Starting bash shell..."
        exec bash
        ;;
    *)
        echo "Usage: $0 {app|worker|web|test|debug|bash}"
        echo "  app    - Start full application with supervisor"
        echo "  worker - Start worker process only"
        echo "  web    - Start web server only"
        echo "  test   - Run test suite"
        echo "  debug  - Run diagnostics and start shell"
        echo "  bash   - Start bash shell"
        exit 1
        ;;
esac
