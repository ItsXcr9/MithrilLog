# MithrilLog Technical Knowledge Base

## 1. System Summary
- **Purpose**: Local-first log deduplication, sampling, and summarization stack backed by lightweight LLMs.
- **Data Path**: Syslog senders → UDP/TCP listeners → ingestion queue → dedupe/sampler → minute buckets + metadata → hourly/daily summarizers → FastAPI API/UI.
- **Key Components**:
  - `IngestServer` (`src/mithrillog/ingestion/ingest_server.py`)
  - `BloomDeduper` & `ReservoirSampler` (`src/mithrillog/ingestion/dedupe.py`)
  - `JournalWriter` (`src/mithrillog/storage.py`)
  - `HourlySummarizer` & `DailySummarizer` (`src/mithrillog/summarization/`)
  - `LLMClient` (`src/mithrillog/llm/client.py`)
  - `Orchestrator` (`src/mithrillog/orchestrator.py`)
  - FastAPI surface (`app/main.py`)

## 2. Configuration Surface
`src/mithrillog/config.py` defines all runtime knobs (read via YAML configs, e.g. `configs/default.yaml`):

| Section | Keys | Notes |
| --- | --- | --- |
| `LLMConfig` | `backend`, `model_path`, `context_length`, `temperature`, `top_p`, `max_tokens` | Supports `llama_cpp` (local) or `openai`; context budget enforcement happens in `LLMClient.generate`. |
| `IngestConfig` | `host`, `udp_port`, `tcp_port`, `bucket_dir`, `max_bucket_minutes`, `bloom_error_rate`, `reservoir_size` | Drives listener bindings, storage root, dedupe false-positive target, sampler size. |
| `SummaryConfig` | `hourly_at_minute`, `daily_at_hour`, `daily_at_minute`, `report_dir` | Controls scheduler cadence and report directory roots. |
| `PromptsConfig` | `hourly`, `daily`, `anomaly` | Files in `prompts/` with `--system--` / `--user--` markers. |

`Settings.load(path)` resolves/expands YAML to a `Settings` object. The global `default_settings` loads defaults for CLI/API usage.

## 3. Orchestrator Lifecycle
`src/mithrillog/orchestrator.py` is the control plane:
- Instantiates `JournalWriter`, `LLMClient`, `IngestServer`, hourly/daily summarizers from the same `Settings`.
- `start()` launches:
  - UDP/TCP ingestion (`IngestServer.start`).
  - Catch-up task (`_catchup_summaries`) replaying 24h of hourlies + 7d of dailies.
  - Hourly scheduler (`_hourly_scheduler`): waits until configured minute, then runs `summarize_hour(target_hour)`.
  - Daily scheduler (`_daily_scheduler`): similar for configured hour/minute.
  - `_watchdog`: placeholder for health/metrics.
- `stop()` cancels tasks, stops ingestion, and awaits cleanup.
- All summarizers run via `asyncio.to_thread` to isolate blocking file/LLM work from the event loop.

## 4. Ingestion Flow
`IngestServer` handles UDP/TCP intake, parsing, deduplication, sampling, and persistence.

### 4.1 Queue & Transports
- `_queue`: `asyncio.Queue` (50k max) storing `(bytes, host, transport)`.
- `_start_udp()`: creates `DatagramEndpoint`, pushing datagrams into queue; drops packets if queue is full.
- `_start_tcp()`: `asyncio.start_server` with per-connection reader loop; trims line endings and enqueues.

### 4.2 Syslog Parsing (`parse_syslog`)
- Decodes bytes, keeps raw string, best-effort RFC 3164 parsing to pull priority, timestamp, host, app, severity/facility.
- Wraps parsed data into `LogEvent` (Pydantic model) with helper methods:
  - `normalize_message()`: attempts JSON parsing (MongoDB-style logs) to extract stable pattern, replaces numbers, GUIDs, hashes, IPs, MACs, and long quoted strings with canonical placeholders.
  - `dedupe_key()`: JSON blob of `{severity, facility, normalized_message}` (host/app excluded to collapse cross-host repeats) → bytes.
  - `sample_key()`: `host:severity:app` string for reservoir partitioning.
  - `pattern_id()`: SHA1 of dedupe key (hex string).

### 4.3 Per-minute Bucketing
- `_current_bucket` tracks floored minute; on incoming event:
  - Compute `bucket_time = floor_to_minute(event.timestamp)`.
  - If bucket advances: `_flush_bucket()`, reset Bloom filter and sampler, update `_current_bucket`.
- `JournalWriter.append(record)` writes NDJSON line into `data/buckets/YYYY/MM/DD/HH/mm.ndjson`. `record` includes:
  - Base `LogEvent` fields
  - `pattern_id`
  - `occurrences` (sampler total for pattern prior to add + 1)

### 4.4 Deduplication & Sampling
- `BloomDeduper.seen(dedupe_key)` returns `True` if event already witnessed in current bucket; on duplicate, `ReservoirSampler.register_duplicate` increments pattern counter and ingestion stops.
- On first occurrence:
  - `ReservoirSampler.add(sample_key, pattern, record)` performs per-key reservoir sampling (size = `reservoir_size`, default 200) with standard algorithm (replace random index with probability `size/count`).
  - `sampler.totals()` tracks occurrences per `pattern_id`.

### 4.5 Bucket Flush & Metadata
- Triggered when bucket rolls or during shutdown.
- Uses live counters accumulated during the bucket (so duplicates still influence stats even if only one sample is stored) plus the NDJSON samples to build:
  - `severity_counts`, `host_counts`, `app_counts`
  - `patterns`: occurrences per pattern (from sampler + counters)
  - `highlights`: sample event annotated with `occurrences`, `source_hosts`, `source_apps`
  - `total_events`, `unique_events`
- Writes `<bucket>.meta.json` covering bucket window, per-field counts, plus top 50 highlights sorted by occurrences.

## 5. Storage Layout
- `data/buckets/YYYY/MM/DD/HH/mm.ndjson`: raw unique events per minute.
- `.meta.json` sibling: minute-level summaries consumed by hourly summarizer.
- `data/reports/hourly/YYYY/MM/DD/HH.json`: hourly summary documents (LLM narrative, anomaly note, stats, minute rollups, highlights).
- `data/reports/daily/YYYY/MM/DD.json`: daily aggregate summarizing preceding 24h.
- `JournalWriter` ensures directories exist, writes JSON via `write_summary` / `write_metadata`, and exposes `list_buckets()` for iteration.

## 6. Summarization Pipeline

### 6.1 Prompt Handling
- `prompts/*.txt` use:
  ```
  --system--
  <system prompt>
  --user--
  <user prompt>
  ```
- `load_prompt_template` splits and returns `PromptTemplate`.

### 6.2 LLM Client
- Loads `llama_cpp` model if `backend == "llama_cpp"` and `model_path` exists; otherwise logs warnings and falls back.
- `generate(template, variables)`:
  - Renders system/user strings.
  - Applies conservative truncation (context length minus reserved tokens, approx 3 chars/token).
  - If no model, `_fallback_summary` emits deterministic text from stats/highlights.
  - Otherwise calls `create_chat_completion` with configured `temperature`, `top_p`, `max_tokens`.

### 6.3 Hourly Summaries
- Iterates last 60 minute metadata files for target hour.
- Aggregates totals, severity/host/app counters, collects highlights, builds minute rollup list.
- Prepares `variables`:
  - `window_start/end`
  - Text tables for stats, recent minute rollups, highlight table (clipped)
  - Structured `stats` + condensed highlights for fallback
- Invokes:
  - `hourly_summary` prompt for narrative.
  - `anomaly` prompt for anomaly report.
- Persists report JSON (skips if already present to avoid duplication).

### 6.4 Daily Summaries
- Scans 24 hourly JSON reports:
  - Aggregates totals, severity/host/app counts.
  - Captures hourly summary/anomaly snippets for linking.
  - Collects highlight samples (top 30 persisted).
- Builds prompt variables similar to hourly but at day granularity (stats table, last 12 hourly digests, highlight table).
- Generates single LLM narrative, writes daily report JSON, idempotent if file exists.

## 7. Serving Layer
- `app/main.py` spins up FastAPI:
  - `/health`: static `{"status": "ok"}`.
  - `/summaries/hourly`: reads latest hourly JSON files (limit 1–48) from `default_settings.summary.report_dir`.
  - `/summaries/daily`: same for daily reports.
  - Root (`/`): Jinja2 dashboard template; static assets via `/static`.
- `_list_reports(base, limit)` iterates JSON files newest-first (reverse-sorted `rglob`).

## 8. Operations & Tooling
- **Local dev**: `uv sync`, run orchestrator via `scripts/run_orchestrator.py`, API via `uvicorn app.main:app`.
- **Docker**: `docker compose up --build -d` brings up `orchestrator` + `api` containers, mapping data/configs/models as volumes.
- **Testing ingestion**: use `logger` or `nc` to send syslog events to UDP 5514 / TCP 5614.
- **Inspecting outputs**:
  - Buckets: `ls data/buckets/<YYYY>/<MM>/<DD>/<HH>/`
  - Metadata: `cat .../<mm>.meta.json`
  - Hourly: `cat data/reports/hourly/<YYYY>/<MM>/<DD>/<HH>.json`
  - Daily: `cat data/reports/daily/<YYYY>/<MM>/<DD>.json`
- **Maintenance**:
  - Restart after config/model changes: `docker compose restart orchestrator api`
  - Prune buckets older than N days: `find data/buckets -mtime +7 -delete`
  - Drop new GGUF weights into `models/`, restart orchestrator to reload.

## 9. Future & Scalability Notes
- `docs/architecture.md` highlights roadmap:
  - Swap ingestion to Rust/Go when >50k EPS; Python dedupe/summarizer logic remains unchanged.
  - Persist metadata in SQLite/Parquet for BI workloads.
  - Add Prometheus/Grafana, anomaly detection enhancements, PII scrubbing.
- Bloom filter defaults target 1e-4 FP with ~1M events/min (~2 MB footprint).
- Horizontal scaling via host/facility sharding with shared storage and distributed locks (e.g., Redis).

## 10. File Reference Map
- `README.md`: quickstart, pipeline overview, Docker instructions, ops cheatsheet.
- `docs/architecture.md`: high-level architecture and roadmap.
- `docs/knowledge_base.md` (this file): authoritative technical reference for ingestion, storage, summarization, serving, and ops.

