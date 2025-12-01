## Architecture Overview

MithrilLog is a **multi-tenant, local-first log analysis platform** designed for SaaS deployment. It consists of three main subsystems:

1.  **Core MithrilLog**: The log ingestion and summarization engine (one instance per tenant).
2.  **Gateway**: A reverse proxy and authentication layer that routes traffic to tenant instances.
3.  **Admin Panel**: A centralized dashboard for managing tenants, plans, and billing.

---

### 1. Core MithrilLog (Per-Tenant)

Each tenant gets a dedicated MithrilLog instance (containerized) responsible for their data.

-   **Ingestion**: `IngestServer` accepts RFC 5424 logs over UDP/TCP (default `:5514`/`:5614`) and writes newline-delimited JSON events into `data/buckets/`.
-   **Buffering**: `JournalWriter` batches events into minute buckets (`data/buckets/YYYY/MM/DD/HH/mm.ndjson`).
-   **Deduplication**: `BloomDeduper` uses a Bloom filter per bucket to drop exact duplicates.
-   **Sampling**: `ReservoirSampler` keeps representative examples (exemplars) per host/severity/pattern.
-   **Summarization**:
    -   **Hourly**: `HourlySummarizer` aggregates minute buckets, extracts stats, and uses the local LLM to generate a narrative summary.
    -   **Daily**: `DailySummarizer` aggregates hourly reports into a daily overview.
    -   **Trend**: `TrendSummarizer` compares daily reports to identify long-term patterns and anomalies.
-   **Storage**: Summaries and anomalies stored in `data/reports/`.
-   **Serving**: FastAPI app (`app/main.py`) exposes REST endpoints and a web dashboard.

### 2. Gateway System

The Gateway handles routing and authentication for the multi-tenant SaaS architecture.

-   **Reverse Proxy**: Nginx routes traffic based on URL paths (`/p/{project_id}/`).
-   **Authentication**: FastAPI service (`gateway/app/main.py`) manages sessions via cookies.
-   **Authorization**: Nginx uses the `auth_request` module to query the Gateway's `/auth` endpoint.
    -   The Gateway validates the session and checks if the user has access to the requested project.
    -   It returns the upstream URL (e.g., `http://mithrillog-project1:9000`) in the `X-Target-Upstream` header.
-   **Isolation**: Strict path checking ensures users cannot access other tenants' instances.

### 3. Admin Panel

Centralized management interface for the SaaS platform.

-   **Backend**: Go application using Gin framework (`admin-go/`) with SQLite database (`admin.db`).
-   **Data Models**:
    -   **Projects**: Tenants with configuration, upstream URLs, and assigned plans.
    -   **Plans**: Subscription tiers (Starter, Pro, Business) with resource limits.
    -   **Usage**: Hourly and daily metrics (event counts, storage) tracked per project.
    -   **Invoices**: Billing records generated from usage and plan pricing.
-   **Features**:
    -   Project provisioning and management.
    -   Quota enforcement (events/day limits).
    -   Plan upgrades/downgrades.
    -   System-wide configuration (default prompts, LLM settings).

---

### Data Flow

1.  **Ingestion**: Tenant sends logs to their assigned port (e.g., `5514`).
2.  **Processing**: Core MithrilLog ingests, dedupes, and stores logs in the tenant's volume.
3.  **Access**: User logs in via Gateway (`xcr9.site`).
4.  **Routing**: Gateway authenticates request and routes to the correct tenant container.
5.  **Management**: Admin manages quotas and plans via Admin Panel (`localhost:9999`).

### Scalability Notes

-   **Per-Tenant Isolation**: Each tenant is a separate container, ensuring data isolation and preventing "noisy neighbor" issues affecting ingestion performance.
-   **Storage**: Local filesystem (or mounted volumes) used for simplicity and speed. Can be backed by S3/EBS for durability.
-   **LLM**: Shared or dedicated LLM resources depending on deployment. Currently uses local GGUF models via `llama.cpp`.

### Security & Compliance

-   **Authentication**: Secure cookie-based sessions with strict path scoping.
-   **Data Residency**: Tenant data stays in their dedicated volume.
-   **Audit**: Admin actions are logged for compliance.


