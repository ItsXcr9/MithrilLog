#!/bin/bash
# Deploy MithrilLog updates to server

SERVER="root@65.109.200.75"
REMOTE_PATH="/home/MithrilLog-xcr9"

# Parse arguments
INIT_SCHEMA=false
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --init-schema) INIT_SCHEMA=true ;;
        *) echo "Unknown parameter: $1"; exit 1 ;;
    esac
    shift
done

echo "Syncing app directory..."
rsync -avz --progress ./app/ ${SERVER}:${REMOTE_PATH}/app/

echo "Syncing src directory..."
rsync -avz --progress ./src/ ${SERVER}:${REMOTE_PATH}/src/

echo "Syncing docker-compose.yml..."
rsync -avz --progress ./docker-compose.yml ${SERVER}:${REMOTE_PATH}/

echo "Syncing .env file..."
rsync -avz --progress ./.env ${SERVER}:${REMOTE_PATH}/

# Initialize ClickHouse schema if requested
if [ "$INIT_SCHEMA" = true ]; then
    echo "Initializing ClickHouse schema..."
    
    # Sync schema file
    rsync -avz --progress ./infra/clickhouse/mithrillog_schema.sql ${SERVER}:/tmp/
    
    # Execute schema in ClickHouse (using AncientReport's ClickHouse)
    ssh ${SERVER} "cat /tmp/mithrillog_schema.sql | curl -sS 'http://127.0.0.1:6123/?user=AncientReport&password=AncientReport' --data-binary @-"
    
    echo "Schema initialized!"
fi

echo "Restarting API container..."
ssh ${SERVER} "cd ${REMOTE_PATH} && docker compose up -d --force-recreate api"

echo "Done! Verify at: https://mithrillog.xcr9.site/p/xcr9/"
