#!/bin/bash

# MithrilLog Admin Panel - Production Deployment Script

set -e

echo "🚀 MithrilLog Admin Panel Deployment"
echo "======================================"
echo ""

# Change to admin directory
cd /home/MithrilLog-xcr9/admin

echo "📦 Step 1: Building Docker image..."
docker compose build

echo ""
echo "🗄️  Step 2: Initializing database..."

# Check if database exists
if [ ! -f "./data/admin.db" ]; then
    echo "   Creating database and seeding data..."
    
    # Create data directory
    mkdir -p ./data
    
    # Run initialization in temporary container
    docker run --rm \
        -v $(pwd)/data:/app/data \
        -v /home/MithrilLog-xcr9/gateway/config.yaml:/app/config.yaml \
        -e PYTHONPATH=/app \
        admin-admin \
        /bin/bash -c "
            cd /app && \
            python -c 'from app.models import init_db; init_db(\"sqlite:////app/data/admin.db\")' && \
            cd /app && python scripts/seed_plans.py --database sqlite:////app/data/admin.db && \
            cd /app && python scripts/migrate_projects_to_db.py --config /app/config.yaml --database sqlite:////app/data/admin.db
        "
    
    echo "   ✅ Database initialized and seeded"
else
    echo "   ✅ Database already exists, skipping initialization"
fi

echo ""
echo "🐳 Step 3: Starting admin panel container..."
docker compose up -d

echo ""
echo "⏳ Waiting for service to be healthy..."
sleep 5

# Check if container is running
if docker ps | grep -q mithrillog-admin; then
    echo "   ✅ Container is running"
    
    # Test health endpoint
    if curl -f http://localhost:9999/health &>/dev/null; then
        echo "   ✅ Health check passed"
    else
        echo "   ⚠️  Health check failed, but container is running"
    fi
else
    echo "   ❌ Container failed to start"
    echo ""
    echo "Logs:"
    docker compose logs admin
    exit 1
fi

echo ""
echo "✅ Deployment Complete!"
echo ""
echo "Admin Panel: http://localhost:9999"
echo "API Docs:    http://localhost:9999/docs"
echo ""
echo "Commands:"
echo "  View logs:    docker compose logs -f admin"
echo "  Restart:      docker compose restart admin"
echo "  Stop:         docker compose down"
echo "  Shell:        docker compose exec admin /bin/bash"
echo ""
