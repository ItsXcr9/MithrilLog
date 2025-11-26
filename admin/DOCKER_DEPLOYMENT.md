# MithrilLog Admin Panel - Docker Deployment Guide

## 🎯 Benefits of Docker Deployment

Running the admin panel with Docker alongside the gateway provides:

1. **Consistency** - Same deployment method as gateway
2. **Isolation** - Clean environment with all dependencies
3. **Easy Updates** - Just rebuild and restart
4. **Persistence** - Database stored in mounted volume
5. **Networking** - Easy integration with gateway on same network
6. **Production Ready** - Health checks and auto-restart

---

## 📁 File Structure

```
/home/MithrilLog-xcr9/
├── gateway/
│   ├── gateway-compose.yml
│   └── config.yaml
└── admin/
    ├── Dockerfile            # Container definition
    ├── docker-compose.yml    # Service configuration
    ├── deploy.sh            # Deployment script
    ├── requirements.txt      # Python dependencies
    ├── app/
    │   ├── main.py
    │   ├── models.py
    │   ├── static/
    │   └── templates/
    └── data/                 # Persistent database (created automatically)
        └── admin.db
```

---

## 🚀 Quick Start

### 1. Copy Files to Server

```bash
# From your local machine
rsync -avz admin/ root@65.109.200.75:/home/MithrilLog-xcr9/admin/
```

### 2. Deploy on Server

```bash
ssh root@65.109.200.75

cd /home/MithrilLog-xcr9/admin
chmod +x deploy.sh
./deploy.sh
```

That's it! The script will:
- Build the Docker image
- Initialize database
- Seed subscription plans
- Migrate existing projects
- Start the container
- Verify it's healthy

### 3. Access Admin Panel

- **Admin Dashboard**: http://mithrillog.xcr9.site:9999
- **API Docs**: http://mithrillog.xcr9.site:9999/docs
- **Health Check**: http://mithrillog.xcr9.site:9999/health

---

## 🔧 Configuration

### Environment Variables

Edit `docker-compose.yml` to configure:

```yaml
environment:
  - DATABASE_URL=sqlite:////app/data/admin.db
  - CONFIG_PATH=/app/config.yaml
  # Add more as needed:
  # - ADMIN_SECRET_KEY=your-secret-key
  # - SMTP_HOST=smtp.gmail.com
  # - SMTP_PORT=587
```

### Volumes

```yaml
volumes:
  - ./data:/app/data                    # Database persistence
  - ../gateway/config.yaml:/app/config.yaml:ro  # Read-only config
```

### Networking

The admin panel joins the same Docker network as the gateway:

```yaml
networks:
  mithrillog-network:
    external: true
    name: mithrillog_default
```

This allows admin panel to communicate with gateway services using container names.

---

## 📊 Management Commands

### View Logs
```bash
cd /home/MithrilLog-xcr9/admin
docker-compose logs -f admin
```

### Restart Service
```bash
docker-compose restart admin
```

### Stop Service
```bash
docker-compose down
```

### Update Code
```bash
# Pull latest changes
git pull

# Rebuild and restart
docker-compose up -d --build
```

### Access Container Shell
```bash
docker-compose exec admin /bin/bash
```

### Database Operations
```bash
# Backup database
docker-compose exec admin cp /app/data/admin.db /app/data/admin.db.backup

# Run migration
docker-compose exec admin python scripts/migrate_projects_to_db.py

# Access SQLite
docker-compose exec admin sqlite3 /app/data/admin.db
```

---

## 🌐 Nginx Configuration

Add admin panel to your nginx config:

```nginx
# /home/xcr9-site/nginx.conf

server {
    listen 80;
    server_name mithrillog.xcr9.site;
    
    # Existing gateway proxy...
    
    # Admin panel
    location /admin/ {
        proxy_pass http://127.0.0.1:9999/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Then reload nginx:
```bash
nginx -t
nginx -s reload
```

Access at: **https://mithrillog.xcr9.site/admin/**

---

## 🔒 Security Recommendations

### 1. Add Authentication
The admin panel currently has no authentication. Add before production:

```python
# In admin/app/main.py
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

security = HTTPBasic()

def verify_admin(credentials: HTTPBasicCredentials = Depends(security)):
    if credentials.username != "admin" or credentials.password != "your-secret":
        raise HTTPException(status_code=401, detail="Unauthorized")
    return credentials.username

# Add to protected routes:
@app.get("/api/admin/projects", dependencies=[Depends(verify_admin)])
```

### 2. Use Environment Variables for Secrets
```yaml
environment:
  - ADMIN_USERNAME=${ADMIN_USERNAME}
  - ADMIN_PASSWORD=${ADMIN_PASSWORD}
```

### 3. Restrict Network Access
```nginx
# Only allow from specific IPs
location /admin/ {
    allow 1.2.3.4;  # Your IP
    deny all;
    proxy_pass http://127.0.0.1:9999/;
}
```

### 4. Enable HTTPS
Use Cloudflare or Let's Encrypt for SSL termination.

---

## 📈 Monitoring

### Health Checks

Docker automatically monitors via healthcheck:
```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:9999/health"]
  interval: 30s
  timeout: 10s
  retries: 3
```

Check status:
```bash
docker ps
# Look for "healthy" status
```

### Resource Usage
```bash
# CPU and memory
docker stats mithrillog-admin

# Disk usage
du -sh /home/MithrilLog-xcr9/admin/data/
```

---

## 🔄 Backup & Recovery

### Automated Backup
Create a cron job:

```bash
# /etc/cron.daily/backup-admin-db
#!/bin/bash
BACKUP_DIR="/home/backups/mithrillog-admin"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR
docker-compose -f /home/MithrilLog-xcr9/admin/docker-compose.yml \
    exec -T admin \
    sqlite3 /app/data/admin.db ".backup /app/data/backup_${DATE}.db"

cp /home/MithrilLog-xcr9/admin/data/backup_${DATE}.db $BACKUP_DIR/

# Keep only last 7 days
find $BACKUP_DIR -name "backup_*.db" -mtime +7 -delete
```

### Restore from Backup
```bash
docker-compose down
cp /home/backups/mithrillog-admin/backup_YYYYMMDD.db ./data/admin.db
docker-compose up -d
```

---

## 🐛 Troubleshooting

### Container Won't Start
```bash
# Check logs
docker-compose logs admin

# Try interactive mode
docker-compose run --rm admin /bin/bash
```

### Database Errors
```bash
# Reset database
rm -f ./data/admin.db
docker-compose down
./deploy.sh
```

### Port Already in Use
```bash
# Find what's using port 9999
lsof -i :9999

# Kill it or change port in docker-compose.yml
```

### Can't Connect to Admin Panel
```bash
# Check if container is running
docker ps | grep admin

# Check if port is exposed
docker port mithrillog-admin

# Test locally on server
curl http://localhost:9999/health
```

---

## ✅ Production Checklist

Before going live:

- [ ] Add admin authentication
- [ ] Configure HTTPS/SSL
- [ ] Set up automated backups
- [ ] Configure monitoring/alerts
- [ ] Restrict network access
- [ ] Use environment variables for secrets
- [ ] Set up log rotation
- [ ] Document admin credentials securely
- [ ] Test disaster recovery procedure
- [ ] Configure firewall rules

---

## 🎯 Next Steps

1. **Deploy**: Run `./deploy.sh` on server
2. **Secure**: Add authentication
3. **Integrate**: Update nginx to proxy /admin/
4. **Monitor**: Set up health check alerts
5. **Backup**: Configure automated backups
6. **Document**: Share credentials with team securely

**Your admin panel will be production-ready and running alongside the gateway!** 🚀
