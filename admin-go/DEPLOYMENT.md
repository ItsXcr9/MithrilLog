# Deployment Guide for Production Server

## Server Details
- **Host**: `root@65.109.200.75`
- **Current Python Admin**: `/home/MithrilLog-xcr9/admin`
- **New Go Admin**: `/home/MithrilLog-xcr9/admin-go`
- **Go Version**: 1.22 (latest stable)

## Quick Deployment

### Option 1: Automated Script (Recommended)

```bash
# From your local machine in admin-go directory
chmod +x deploy.sh
./deploy.sh
```

This script will:
1. ✅ Backup existing Python admin to `/home/MithrilLog-xcr9/admin-python-backup`
2. ✅ Install Go 1.22 if not present
3. ✅ Upload Go admin files
4. ✅ Build binary on server
5. ✅ Migrate database from Python admin
6. ✅ Stop Python admin
7. ✅ Start Go admin
8. ✅ Run health check
9. ✅ Display logs

### Option 2: Manual Deployment

#### Step 1: SSH to Server
```bash
ssh root@65.109.200.75
```

#### Step 2: Backup Python Admin
```bash
mkdir -p /home/MithrilLog-xcr9/admin-python-backup
rsync -av /home/MithrilLog-xcr9/admin/ /home/MithrilLog-xcr9/admin-python-backup/ --exclude data
```

#### Step 3: Install Go 1.22 (if not installed)
```bash
# Check if Go is installed
go version

# If not, install Go 1.22
wget https://go.dev/dl/go1.22.0.linux-amd64.tar.gz
rm -rf /usr/local/go
tar -C /usr/local -xzf go1.22.0.linux-amd64.tar.gz
rm go1.22.0.linux-amd64.tar.gz

# Add to PATH
echo 'export PATH=$PATH:/usr/local/go/bin' >> ~/.bashrc
source ~/.bashrc

# Verify
go version
```

#### Step 4: Upload Go Admin Files
```bash
# From your local machine
rsync -av --progress \
    --exclude='.git' \
    --exclude='data' \
    --exclude='*.db' \
    admin-go/ root@65.109.200.75:/home/MithrilLog-xcr9/admin-go/
```

#### Step 5: Build on Server
```bash
# On server
cd /home/MithrilLog-xcr9/admin-go

# Download dependencies
go mod download

# Build binary
CGO_ENABLED=1 go build -o admin-go .

# Verify binary
./admin-go --help || echo "Binary built successfully"
```

#### Step 6: Prepare Data Directory
```bash
# Create data directory
mkdir -p /home/MithrilLog-xcr9/admin-go/data

# Copy database from Python admin
cp /home/MithrilLog-xcr9/admin/data/admin.db /home/MithrilLog-xcr9/admin-go/data/

# Set permissions
chmod 644 /home/MithrilLog-xcr9/admin-go/data/admin.db
```

#### Step 7: Update Docker Compose (Optional Adjustments)
```bash
cd /home/MithrilLog-xcr9/admin-go
nano docker-compose.yml

# Verify volumes are correct:
# - ./data:/app/data
# - ../configs:/app/configs:ro
# - /home:/home:ro
# - /var/run/docker.sock:/var/run/docker.sock
```

#### Step 8: Stop Python Admin
```bash
cd /home/MithrilLog-xcr9/admin
docker compose down
```

#### Step 9: Start Go Admin
```bash
cd /home/MithrilLog-xcr9/admin-go
docker compose up -d
```

#### Step 10: Verify Deployment
```bash
# Check container is running
docker compose ps

# View logs
docker compose logs -f

# Health check
curl http://localhost:9999/health

# Should return: {"status":"ok","service":"mithrillog-admin-go","time":"..."}
```

## Testing

### Run Automated Tests
```bash
# From your local machine
chmod +x test.sh
./test.sh
```

### Manual API Testing

```bash
# Health check
curl http://65.109.200.75:9999/health

# List projects
curl http://65.109.200.75:9999/api/admin/projects

# Get project details
curl http://65.109.200.75:9999/api/admin/projects/xcr9

# Get limits status
curl http://65.109.200.75:9999/api/admin/limits/status

# Get config templates
curl http://65.109.200.75:9999/api/admin/config/templates

# View suspend page
curl http://65.109.200.75:9999/suspended?project=xcr9
```

## Monitoring

### View Logs
```bash
# Real-time logs
ssh root@65.109.200.75 'cd /home/MithrilLog-xcr9/admin-go && docker compose logs -f'

# Last 100 lines
ssh root@65.109.200.75 'cd /home/MithrilLog-xcr9/admin-go && docker compose logs --tail=100'

# Filter by service
ssh root@65.109.200.75 'cd /home/MithrilLog-xcr9/admin-go && docker compose logs admin-go'
```

### Check Resource Usage
```bash
ssh root@65.109.200.75 'docker stats --no-stream mithrillog-admin-go'
```

### Check Limit Enforcer
```bash
# Trigger manual check
curl -X POST http://65.109.200.75:9999/api/admin/limits/check

# View status
curl http://65.109.200.75:9999/api/admin/limits/status
```

## Rollback to Python Admin

If something goes wrong:

```bash
ssh root@65.109.200.75

# Stop Go admin
cd /home/MithrilLog-xcr9/admin-go
docker compose down

# Start Python admin
cd /home/MithrilLog-xcr9/admin
docker compose up -d

# Verify
curl http://localhost:9999/health
```

## Post-Deployment Checklist

- [ ] Health check responds correctly
- [ ] Can list projects
- [ ] Can view project details
- [ ] Limit enforcer is running (check logs for "Starting limit enforcer")
- [ ] Config templates load correctly
- [ ] Suspend page renders properly
- [ ] Docker operations work (restart a test project)
- [ ] Database queries work
- [ ] Logs show no errors

## Troubleshooting

### Container won't start
```bash
# Check logs
docker compose logs

# Check Docker socket permissions
ls -la /var/run/docker.sock

# Restart Docker daemon
systemctl restart docker
```

### Database errors
```bash
# Check database file
ls -la /home/MithrilLog-xcr9/admin-go/data/admin.db

# Check permissions
chmod 644 /home/MithrilLog-xcr9/admin-go/data/admin.db

# Copy from backup if corrupted
cp /home/MithrilLog-xcr9/admin/data/admin.db /home/MithrilLog-xcr9/admin-go/data/
```

### Config sync not working
```bash
# Check project directory
ls -la /home/MithrilLog-xcr9/configs/

# Check volume mount
docker inspect mithrillog-admin-go | grep -A 10 Mounts

# Manually trigger sync
curl -X POST http://localhost:9999/api/admin/config/xcr9/sync
```

### Docker operations failing
```bash
# Check Docker socket mount
docker inspect mithrillog-admin-go | grep docker.sock

# Test Docker CLI in container
docker exec mithrillog-admin-go docker ps

# Check permissions
docker exec mithrillog-admin-go ls -la /var/run/docker.sock
```

## Performance Comparison

After deployment, compare performance:

```bash
# Python admin (backup)
time curl http://localhost:9998/api/admin/projects  # If running on different port

# Go admin
time curl http://localhost:9999/api/admin/projects
```

Expected Go admin to be **5-10x faster** for most operations.

## Maintenance

### Update Go Admin
```bash
# Pull latest changes
cd /path/to/local/admin-go
git pull

# Deploy
./deploy.sh
```

### View Cron Jobs (Limit Enforcer)
```bash
# Check enforcer logs
docker logs mithrillog-admin-go | grep "limit enforcer"

# Should see: "Starting limit enforcer" and periodic checks
```

### Database Backup
```bash
# Automated daily backup
ssh root@65.109.200.75 '
  cp /home/MithrilLog-xcr9/admin-go/data/admin.db \
     /home/MithrilLog-xcr9/admin-go/data/admin.db.$(date +%Y%m%d)
'
```

## Support

If issues persist:
1. Check logs: `docker compose logs -f`
2. Check health: `curl http://localhost:9999/health`
3. Restart: `docker compose restart`
4. Rollback to Python if critical

## Next Steps

After successful deployment:
1. ✅ Monitor for 24 hours
2. ✅ Verify limit enforcement works at midnight (Tehran time)
3. ✅ Test suspend page when a project hits limits
4. ✅ Verify config sync on settings update
5. ✅ Test Docker restart operations
