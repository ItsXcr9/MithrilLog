#!/bin/bash

# MithrilLog Admin Panel Startup Script

echo "🚀 Starting MithrilLog Admin Panel..."
echo ""

# Check if database exists
if [ ! -f "admin.db" ]; then
    echo "📦 Database not found. Creating and seeding..."
    python3 admin/app/models.py
    python3 scripts/seed_plans.py --database sqlite:///./admin.db
    python3 scripts/migrate_projects_to_db.py
    echo ""
fi

echo "✅ Database ready"
echo ""

# Start admin server
echo "🌐 Starting admin server on http://localhost:9999"
echo "   (Press Ctrl+C to stop)"
echo ""

cd admin && python3 app/main.py
