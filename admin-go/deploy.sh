#!/bin/bash
set -e

# Deployment script for MithrilLog Go Admin
# Target: root@65.109.200.75:/home/MithrilLog-xcr9/admin

SERVER="root@65.109.200.75"
REMOTE_PATH="/home/MithrilLog-xcr9/admin"
BACKUP_DIR="/home/MithrilLog-xcr9/admin-python-backup"

echo "🚀 MithrilLog Go Admin Deployment"
echo "=================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Step 1: Backup existing Python admin
echo -e "${YELLOW}Step 1: Backing up existing Python admin...${NC}"
ssh $SERVER "mkdir -p $BACKUP_DIR && rsync -av $REMOTE_PATH/ $BACKUP_DIR/ --exclude data --exclude __pycache__"
echo -e "${GREEN}✓ Backup created at $BACKUP_DIR${NC}"
echo ""

# Step 2: Create admin-go directory
echo -e "${YELLOW}Step 2: Creating admin-go directory...${NC}"
ssh $SERVER "mkdir -p /home/MithrilLog-xcr9/admin-go"
echo -e "${GREEN}✓ Directory created${NC}"
echo ""

# Step 3: Upload Go admin files
echo -e "${YELLOW}Step 3: Uploading Go admin files...${NC}"
rsync -av --progress \
    --exclude='.git' \
    --exclude='data' \
    --exclude='*.db' \
    --exclude='.DS_Store' \
    ./ $SERVER:/home/MithrilLog-xcr9/admin-go/
echo -e "${GREEN}✓ Files uploaded${NC}"
echo ""

# Step 4: Copy database from Python admin
echo -e "${YELLOW}Step 4: Copying database from Python admin...${NC}"
ssh $SERVER "mkdir -p /home/MithrilLog-xcr9/admin-go/data && \
             cp $REMOTE_PATH/data/admin.db /home/MithrilLog-xcr9/admin-go/data/ 2>/dev/null || true"
echo -e "${GREEN}✓ Database copied${NC}"
echo ""

# Step 5: Stop Python admin
echo -e "${YELLOW}Step 5: Stopping Python admin...${NC}"
ssh $SERVER "cd $REMOTE_PATH && docker compose down || true"
echo -e "${GREEN}✓ Python admin stopped${NC}"
echo ""

# Step 6: Start Go admin (Builds inside Docker)
echo -e "${YELLOW}Step 6: Starting Go admin...${NC}"
ssh $SERVER "cd /home/MithrilLog-xcr9/admin-go && docker compose up -d --build"
echo -e "${GREEN}✓ Go admin started${NC}"
echo ""

# Step 7: Health check
echo -e "${YELLOW}Step 7: Running health check...${NC}"
sleep 3
HEALTH_STATUS=$(ssh $SERVER "curl -s http://localhost:9999/health" || echo "")
if [[ $HEALTH_STATUS == *"ok"* ]]; then
    echo -e "${GREEN}✓ Health check passed!${NC}"
    echo -e "${GREEN}Response: $HEALTH_STATUS${NC}"
else
    echo -e "${RED}✗ Health check failed!${NC}"
    echo -e "${RED}Response: $HEALTH_STATUS${NC}"
    echo -e "${YELLOW}Check logs with: ssh $SERVER 'cd /home/MithrilLog-xcr9/admin-go && docker compose logs'${NC}"
    exit 1
fi
echo ""

# Step 8: View logs
echo -e "${YELLOW}Step 8: Recent logs:${NC}"
ssh $SERVER "cd /home/MithrilLog-xcr9/admin-go && docker compose logs --tail=20"
echo ""

echo -e "${GREEN}=================================="
echo -e "✅ Deployment completed successfully!"
echo -e "==================================${NC}"
echo ""
echo "Access admin panel at: http://65.109.200.75:9999"
echo ""
echo "Useful commands:"
echo "  View logs:    ssh $SERVER 'cd /home/MithrilLog-xcr9/admin-go && docker compose logs -f'"
echo "  Restart:      ssh $SERVER 'cd /home/MithrilLog-xcr9/admin-go && docker compose restart'"
echo "  Stop:         ssh $SERVER 'cd /home/MithrilLog-xcr9/admin-go && docker compose down'"
echo "  Rollback:     ssh $SERVER 'cd $REMOTE_PATH && docker compose up -d'"
echo ""
