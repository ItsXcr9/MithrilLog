## Architecture Overview

- **Ingestion**: `log_ingester` service accepts RFC 5424 logs over UDP/TCP (default `:514`) and writes newline-delimited JSON events into the `data/raw/` queue. A small Rust or Go shim can be added later for higher throughput.
- **Buffering**: `JournalWriter` batches events into minute buckets on disk (`data/buckets/YYYY/MM/DD/HH/mm.ndjson`) while maintaining a dedupe Bloom filter per bucket to drop exact repeats.
- **Sampling**: For near-duplicate patterns the `PatternSampler` keeps a bounded reservoir (per host, per facility/severity) so recurring errors keep at least one exemplar.
- **Feature Extraction**: `LogFeaturizer` normalizes messages (host, severity, hashed body, structured kv pairs) and emits embeddings using the local LLM's encoder interface.
- **Summarization**: `HourlySummarizer` and `DailySummarizer` trigger on schedule, pull the previous window's bucket metadata plus sampled exemplars, and ask the local LLM for:
  - narrative summary of key events
  - anomaly report (new patterns, spikes)
  - action items for SREs (top alerts, failing hosts, remediation hints)
- **Storage**: Summaries and anomalies stored in `data/reports/{hourly,daily}/` and optionally pushed to SQLite for dashboarding.
- **Serving**: Minimal FastAPI app (`app/api.py`) exposes REST endpoints for recent summaries and raw exemplars.
- **Automation**: `orchestrator.py` runs continuous ingestion loop, rotates buckets, schedules hourly/daily jobs, and maintains back-pressure via queue depth metrics.
- **Observability**: Built-in Prometheus metrics for ingest rate, dedupe ratios, model latency, and queue depth; logs reinjected into the pipeline for self-monitoring.

### Local Model Strategy

- Target GGUF models (`LLaMA-3.2-4B-Instruct`, `Qwen2.5-3B-Instruct`) loaded via `llama.cpp` (through `llama-cpp-python` binding). For ARM Macs use Metal acceleration (`LLAMA_METAL=1`).
- Prompt templates kept under `prompts/` with sections for:
  - hourly summary
  - daily summary
  - anomaly detector
- Token budgets enforced: summarizer chunk size tuned so hourly windows stay under ~3k tokens; daily aggregator works off pre-summarized hourlies to reduce cost.
- Fall back to remote provider (OpenAI, etc.) by swapping `LLM_BACKEND` env var.

### Data Flow

1. Syslog-ng forwards to `udp://<host>:5514`.
2. `log_ingester.py` parses, enriches, writes to minute bucket and dedupe filters.
3. `Sampler` stores exemplars per (host, severity, template hash).
4. Scheduler triggers summarizers at `HH:05` and `00:10`.
5. Summaries stored and optional alert if anomalies exceed thresholds.

### Scalability Notes

- For >50k events/sec switch ingestion to Rust (Tokio) or Go netpoll, but processing & summarization logic remains Python.
- Bloom filter false positive target ~1e-4 with 1M events/min → ~2 MB filter footprint.
- Use `rocksdb` or `lmdb` when minute buckets no longer fit in memory for dedupe metadata.
- Horizontal scale by sharding on hostname or facility; orchestrator coordinates via Redis for distributed locks.

### Security & Compliance

- Logs stored under `data/` with AES-at-rest via `age` or encrypted volume. Metadata (hashes, counts) only for dedupe.
- Provide audit trail: summarizer prompts/responses persisted, include model hash in headers.
- Optionally scrub PII using regex rules before persistence.

