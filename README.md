# MithrilLog

**Multi-tenant, local-first log analysis platform backed by small-footprint LLMs.**

MithrilLog is designed for SaaS deployment with three core components:
1.  **Core Engine**: High-performance ingestion and LLM summarization (per-tenant).
2.  **Gateway**: Secure reverse proxy and authentication layer.
3.  **Admin Panel**: Centralized management for tenants, plans, and billing (High-performance Go implementation).

📚 **Documentation**:
- [Architecture Overview](docs/architecture.md)
- [Admin Panel Guide](docs/admin_panel.md)
- [Log Forwarding](docs/LOG_FORWARDING.md)

## Prerequisites

- Python 3.11+
- Docker & Docker Compose v2 (optional but recommended for production)
- `pipx` or `uv` for local virtualenv management
- GGUF model weights compatible with `llama.cpp` (e.g. `TinyLlama-1.1B-Chat-v1.0.Q4_0`)

Download a model and place it under `./models/`:

```bash
mkdir -p models
curl -L -o models/tinyllama-1.1b-chat-v1.0-q4_0.gguf \
  https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF/resolve/main/tinyllama-1.1b-chat-v1.0.Q4_0.gguf
```

`configs/default.yaml` already points to this filename; adjust if you pick another model.

## Local Development (UV / pip)

```bash
uv sync               # or python -m venv .venv && source .venv/bin/activate && pip install -e .
uv run scripts/run_orchestrator.py --config configs/default.yaml
# separate shell for the API
uv run uvicorn app.main:app --reload --port 9000
```

Ports exposed:

- UDP `5514` / TCP `5614` – syslog ingestion
- HTTP `9000` – FastAPI (`/health`, `/summaries/hourly`, `/summaries/daily`)

## Pipeline

- Syslog-ng forwards to UDP/TCP (`5514`/`5614`).
- `IngestServer` dedupes with a Bloom filter and keeps representative samples per host/severity.
- Minute buckets land under `data/buckets/YYYY/MM/DD/HH/mm.ndjson` plus metadata sidecars.
- Hourly and daily summarizers read metadata, compile highlights, and ask the local LLM via prompt templates in `prompts/`.
- Summaries and anomaly notes land in `data/reports/hourly/` and `data/reports/daily/`.
- FastAPI (`app/main.py`) exposes `/summaries/hourly` and `/summaries/daily`.

See `docs/architecture.md` for the big-picture design.  
See `docs/LOG_FORWARDING.md` for details on log forwarding mechanisms.

## Docker Compose

Build and launch both services in the background:

```bash
docker compose up --build -d
```

Mounts:

- `./data` → `/app/data` for buckets and reports
- `./configs`, `./prompts` → in-container config overrides
- `./models` → `/app/models` for GGUF weights (drop `*.gguf` here)

Open the dashboard at `http://localhost:9000/` to browse hourly/daily summaries in the browser. Tail logs via:

```bash
docker compose logs -f orchestrator
```

## Step-by-Step Tutorial

### 1. Prepare the environment

```bash
git clone <repo-url> && cd MithrilLog
python3.11 -m pip install uv  # optional helper
mkdir -p data models
# download model if you haven't already
curl -L -o models/tinyllama-1.1b-chat-v1.0-q4_0.gguf \
  https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF/resolve/main/tinyllama-1.1b-chat-v1.0.Q4_0.gguf
```

### 2. Start the stack

```bash
docker compose up --build -d
docker compose ps
```

You should see `api` and `orchestrator` containers `Up` with ports `5514/udp`, `5614/tcp`, and `9000/tcp` mapped to the host.

### 3. Send manual test logs

From the host running Docker:

```bash
logger --server 127.0.0.1 --port 5514 --udp "manual UDP test"
logger --server 127.0.0.1 --port 5614 "manual TCP test"
```

Or via `nc`:

```bash
echo "<134>$(date '+%b %d %H:%M:%S') testhost app[123]: hello UDP" | nc -w1 -u 127.0.0.1 5514
echo "<134>$(date '+%b %d %H:%M:%S') testhost app[123]: hello TCP" | nc -w1 127.0.0.1 5614
```

### 4. Inspect ingestion results

```bash
ls data/buckets/$(date -u +%Y/%m/%d/%H)/
cat data/buckets/$(date -u +%Y/%m/%d/%H/%M).ndjson
```

Once a minute bucket rolls, view the metadata sidecar:

```bash
cat data/buckets/$(date -u +%Y/%m/%d/%H/%M).meta.json
```

### 5. Verify the LLM summaries

After the hourly job runs (defaults to `HH:05`), inspect the generated report:

```bash
cat data/reports/hourly/$(date -u +%Y/%m/%d)/$(date -u +%H).json
```

Trigger an on-demand run from inside the orchestrator container if needed:

```bash
docker compose exec orchestrator python scripts/run_orchestrator.py --config configs/default.yaml
```

### 6. Query the API

```bash
curl http://localhost:9000/health
curl http://localhost:9000/summaries/hourly
curl http://localhost:9000/summaries/daily
```

Or just visit `http://localhost:9000/` for the built-in dashboard.

### 7. Wire up syslog-ng (example)

```
destination d_mithril_log {
    udp("127.0.0.1" port(5514));
};
log {
    source(s_src);
    destination(d_mithril_log);
};
```

Switch to TCP by changing `udp()` to `tcp()` and adjusting the port to `5614`.

### 8. Maintenance & operations

- Restart services after config changes: `docker compose restart orchestrator api`
- Rotate or prune raw buckets: `find data/buckets -mtime +7 -delete`
- Update models: drop new `*.gguf` files into `models/` and run `docker compose restart orchestrator`
- Monitor logs: `docker compose logs -f orchestrator api`

## Configuration

- `configs/default.yaml` controls listener ports, Bloom filter targets, reservoir size, schedule times, and prompt paths.
- Swap LLM implementations by editing `llm.backend` (`llama_cpp`/`local`, `openai`, `gemini`) and supplying the matching API keys or model path.
- Prompt text uses `{placeholder}` tokens; keep them in sync with variables passed by summarizers.

### Environment secrets

Keep API keys outside of tracked config files by creating a `.env` file in the project root (or point `MITHRILLOG_ENV_FILE` to another path). Any variables defined there are loaded automatically at startup; for example:

```
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
GEMINI_API_KEY=...
DISABLE_CONFIG_TABS=true  # Set to true to hide Settings/Configs tabs in Admin Panel
```

Environment values override the matching entries under `llm` in YAML configs, so you can keep the current profile while activating OpenAI just by setting `OPENAI_API_KEY`.

## Operations

- Daemonize via systemd: point `ExecStart` to `scripts/run_orchestrator.py --config /etc/mithrillog.yaml`.
- Health: ensure `/health` returns `{"status": "ok"}`; metrics hook stubbed in `_watchdog`.
- Storage hygiene: prune `data/buckets` after hourly summaries ship; add lifecycle tools under `scripts/`.

## Next Steps

- Swap ingestion loop for Rust/Go when throughput >50k EPS.
- Persist metadata in SQLite/Parquet for BI workloads.
- Add Prometheus exporter and Grafana dashboards.
- Extend anomaly detection with embedding clustering or rules.



          Syslog Senders
               │
   ┌───────────▼───────────┐
   │ UDP 5514 / TCP 5614   │
   │  Orchestrator (Ingest)│
   └───────────┬───────────┘
               │ parsed events
   ┌───────────▼───────────┐
   │ Deduper + Sampler     │
   └──────┬────────┬───────┘
          │        │
   raw uniques  stats/samples
          │        │
   ┌──────▼────────▼──────┐
   │ data/buckets/YYYY/...│
   │   *.ndjson + meta    │
   └──────┬────────┬──────┘
          │        │
          │   Scheduler (hourly/daily)
          │        │
          │   ┌────▼────┐
          │   │  LLM    │
          │   └────┬────┘
          │        │ summaries
          └────────▼
        data/reports/...
               │
          FastAPI /summaries
               │
           Clients / UI

## License & Enterprise

This software is licensed under the **Xcr9 Community License** - See [LICENSE](LICENSE)

- ✅ **Free** for personal and non-commercial use
- ✅ **Free** for small teams (up to 5 monitored servers)
- 🏢 **Enterprise License** required for commercial use with more than 5 servers

### Get Enterprise License

Visit **[xcr9.site/pricing](https://xcr9.site/pricing.html)** to purchase an Enterprise license which includes:

- Unlimited servers
- Priority support
- Custom integrations
- SLA guarantees
- Professional services

## Part of Xcr9 Platform

MithrilLog is part of the [Xcr9](https://xcr9.site) AI infrastructure suite:

- **[MithrilLog](https://xcr9.site/mithrillog.html)** — AI-powered log management
- **[AncientReport](https://xcr9.site/ancientreport.html)** — Autonomous observability (eBPF)
- **[MetalHive](https://xcr9.site/metalhive.html)** — Bare-metal Docker orchestration

### Contact

- 🌐 Website: [xcr9.site](https://xcr9.site)
- 📧 Sales: [xcr9.site/contact](https://xcr9.site/contact.html)

---

*© 2025 Xcr9. Building the future of AI infrastructure.*

           