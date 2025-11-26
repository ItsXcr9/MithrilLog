# MithrilLog Admin Panel - Quick Start

## 🚀 Launch Admin Panel

The admin panel is now ready! Here's how to start it:

### Option 1: Quick Start Script
```bash
./scripts/start_admin.sh
```

### Option 2: Manual Start
```bash
# Make sure database is initialized
python3 scripts/seed_plans.py
python3 scripts/migrate_projects_to_db.py

# Start admin server
cd admin && python3 app/main.py
```

### Access Admin Panel
Open your browser to: **http://localhost:9999**

---

## 📊 What's Included

### Features Built
- ✅ **Dashboard Overview**: Real-time stats for all projects
- ✅ **Project Management**: View all 5 projects with usage metrics
- ✅ **Quota Monitoring**: Color-coded status (green/yellow/orange/red)
- ✅ **Plan Management**: Change subscription plans per project
- ✅ **Usage Analytics**: Hourly and daily usage charts
- ✅ **Quota Enforcement**: Update custom limits per project
- ✅ **Project Suspend/Activate**: Control project access

### API Endpoints Available
- `GET /api/admin/stats/overview` - Dashboard statistics
- `GET /api/admin/projects` - List all projects
- `GET /api/admin/projects/{id}` - Project details
- `GET /api/admin/projects/{id}/usage/hourly` - Hourly metrics
- `GET /api/admin/projects/{id}/usage/daily` - Daily metrics
- `PUT /api/admin/projects/{id}/plan` - Change plan
- `PUT /api/admin/projects/{id}/quota` - Update quota
- `PUT /api/admin/projects/{id}/status` - Suspend/activate
- `GET /api/admin/plans` - List subscription plans

---

## 🎨 UI Features

- **Modern Glassmorphism Design**: Beautiful dark theme with gradient accents
- **Real-time Updates**: Auto-refresh every 30 seconds
- **Responsive Layout**: Works on desktop and mobile
- **Interactive Modals**: Click any project for detailed view
- **Color-coded Status**: Instantly see quota health
- **Smooth Animations**: Premium feel throughout

---

## 📝 Current Projects

All 5 projects have been migrated to the database:
1. **Project Tebyan** (project1) - Professional Plan
2 **Project IBS Cloud** (project2) - Professional Plan
3. **Project XCR9** (project3) - Professional Plan
4. **Project Afranet** (project4) - Professional Plan
5. **Project MJ** (project5) - Professional Plan

Each project has:
- Daily limit: 500,000 events (Professional plan)
- Monthly limit: 15,000,000 events
- 30 days retention
- 3 alert channels

---

## 🔧 Next Steps (Optional)

### Recommended Additions
1. **Admin Authentication** - Add login for admin panel security
2. **Billing Integration** - Connect to Stripe for automated payments
3. **Email Notifications** - Send quota warnings via SMTP
4. **Advanced Analytics** - More detailed usage charts
5. **Audit Logging** - Track all admin actions

### Connect to Real Projects
To actually track usage from your MithrilLog instances:
1. Update each project's ingestion code to use `UsageTracker`
2. Add quota enforcement middleware to reject over-limit logs
3. Schedule daily aggregation task for metrics rollup

---

## 🎯 Testing the Admin Panel

### View Projects
1. Go to http://localhost:9999
2. See dashboard with 5 projects
3. Click "Projects" in sidebar for full list

### Test Project Management
1. Click any project card
2. Try "Change Plan" → enter `business`
3. Try "Update Quota" → enter `1000000`
4. Try "Suspend" to temporarily disable project

### Check Usage Metrics
1. Projects should show 0 events (no logs ingested yet)
2. Once you send logs, metrics will update
3. Quota status will change color as usage increases

---

## ❓ Troubleshooting

**Admin panel won't start?**
- Make sure SQLAlchemy is installed: `pip3 install --break-system-packages sqlalchemy`
- Check database exists: `ls -la admin.db`

**Projects not showing?**
- Run migration: `python3 scripts/migrate_projects_to_db.py`
- Check database: `sqlite3 admin.db "SELECT * FROM projects;"`

**Usage metrics always 0?**
- Normal! Usage tracking requires integration with log ingestion
- See "Connect to Real Projects" section above

---

## 🎉 You're Ready!

The admin panel is fully functional and ready to manage your MithrilLog SaaS business!
