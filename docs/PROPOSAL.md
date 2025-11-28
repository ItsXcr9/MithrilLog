# MithrilLog Evolution Proposal

Based on a deep analysis of the current codebase and architecture, this proposal outlines a strategic roadmap to elevate MithrilLog from a functional MVP to a scalable, enterprise-grade SaaS platform.

## 1. Architecture & Scalability (High Impact)

### Current State
- **Per-Tenant Containers**: Good for isolation but resource-intensive (CPU/RAM overhead per tenant).
- **Python Ingestion**: `IngestServer` is easy to modify but hits GIL limitations at high throughput (>10k EPS).
- **SQLite Storage**: Excellent for "local-first" but limits concurrency and complex analytics for the Admin panel.

### Recommendations
1.  **Hybrid Multi-Tenancy**:
    -   **Proposal**: Keep dedicated containers for "Enterprise" plans but implement a **Shared Ingestion Cluster** for "Starter/Pro" plans.
    -   **Benefit**: Reduces infrastructure costs by 60-80% for smaller tenants.
    -   **Tech**: Use a `tenant_id` field in a shared ClickHouse or partitioned SQLite setup.

2.  **Rust/Go Ingestion Layer**:
    -   **Proposal**: Rewrite the `IngestServer` (UDP/TCP listener + Bloom Filter) in Rust. Keep Python for the "Smart" layer (LLM summarization).
    -   **Benefit**: 10x throughput increase; handles traffic spikes without dropping packets.

3.  **Database Migration**:
    -   **Proposal**: Migrate `admin.db` to **PostgreSQL**.
    -   **Benefit**: Handles concurrent admin actions, complex billing queries, and ensures data integrity for financial records.

## 2. Future Technology Strategy (Rust vs. Python)

We have successfully migrated the **Ingestion Layer** to Rust. The current architecture is a "Hybrid" model:
*   **Rust**: High-volume, "dumb" data shoveling (Ingest, Dedupe, Storage).
*   **Python**: Low-volume, "smart" data analysis (LLM, Orchestration, API).

### What to Keep in Python?
*   **Orchestrator & LLM**: Python is the native language of AI. The bottleneck here is the LLM API latency, not CPU. Moving this to Rust adds complexity with zero performance gain.
*   **API (FastAPI)**: Unless you have 10k+ concurrent users viewing the dashboard, FastAPI is sufficient.

### What to Move to Rust Next?
1.  **Log Query Engine (Search)**:
    *   **Problem**: As logs grow (GBs/day), searching them via Python (grep/scan) will become slow.
    *   **Solution**: Implement a small Rust service (or FFI binding) to perform indexed searches or fast scans on the `.ndjson` files.
    *   **Impact**: Sub-second search results for "Live Tail" and "History" even with millions of logs.

## 3. Feature Enhancements (User Value)

### Current State
- **Live Tail**: Uses SSE/Polling (resource heavy on client/server).
- **Alerting**: Limited to Telegram.
- **Search**: Linear scan of daily buckets (slow for long time ranges).

### Recommendations
1.  **Real-Time WebSockets**:
    -   **Proposal**: Replace SSE with a WebSocket server (using FastAPI or a dedicated Go microservice) for Live Tail.
    -   **Benefit**: Bi-directional communication, lower latency, less connection overhead.

2.  **Advanced Alerting & Webhooks**:
    -   **Proposal**: Add a generic **Webhook** destination.
    -   **Benefit**: Allows users to integrate with Slack, Discord, PagerDuty, or custom internal tools without you writing specific integrations for each.

3.  **Indexed Log Search**:
    -   **Proposal**: Implement a lightweight inverted index (e.g., using `Tantivy` or `Bleve` bindings) alongside the raw logs.
    -   **Benefit**: Sub-second search results over 30-day windows, enabling a "Google-like" log search experience.

## 3. Security & Compliance (Enterprise Ready)

### Current State
- **Auth**: Custom cookie-based session management.
- **Ingestion**: Relies on IP/Port accessibility.

### Recommendations
1.  **API Key Ingestion Auth**:
    -   **Proposal**: Require an `x-api-key` header or structured token in syslog metadata for ingestion.
    -   **Benefit**: Prevents log spoofing and allows easy revocation of compromised credentials.

2.  **Role-Based Access Control (RBAC)**:
    -   **Proposal**: Add "Viewer", "Editor", and "Admin" roles within tenant projects.
    -   **Benefit**: Critical for selling to larger teams where not everyone should change billing or retention settings.

3.  **Audit Logs**:
    -   **Proposal**: Expose the `AdminAction` table in the UI.
    -   **Benefit**: Compliance requirement for Enterprise customers (SOC2/GDPR).

## 4. Operational Excellence (DevOps)

### Current State
- **Deployment**: `docker-compose` with manual syncs.
- **Monitoring**: Self-monitoring via remote logging (good start!).

### Recommendations
1.  **CI/CD Pipeline**:
    -   **Proposal**: GitHub Actions workflow to build Docker images, run tests, and deploy to a staging environment automatically.
    -   **Benefit**: Prevents regressions and speeds up release cycles.

2.  **Centralized Metrics (Prometheus/Grafana)**:
    -   **Proposal**: Expose `/metrics` endpoint on all services. Aggregate into a central Grafana dashboard.
    -   **Benefit**: Visualizes "Global Ingestion Rate", "Total Active Tenants", and "Error Rates" in one pane of glass.

## Roadmap Summary

| Phase | Focus | Key Deliverables |
| :--- | :--- | :--- |
| **Phase 1 (Foundation)** | Stability | PostgreSQL for Admin, CI/CD Pipeline, Webhook Alerts |
| **Phase 2 (Performance)** | Scale | Rust Ingestion Shim, WebSocket Live Tail |
| **Phase 3 (Growth)** | Enterprise | RBAC, API Key Auth, Shared Multi-tenancy |

---
*Prepared by Antigravity Agent*
