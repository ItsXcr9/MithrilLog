FROM rust:slim-bookworm AS builder
WORKDIR /usr/src/ingester
COPY src/ingester-rs .
RUN cargo install --path .

FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        cmake \
        ninja-build \
        libopenblas-dev && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src
COPY app ./app
COPY scripts ./scripts
COPY configs ./configs
COPY prompts ./prompts

# Copy Rust binary
COPY --from=builder /usr/local/cargo/bin/ingester-rs /usr/local/bin/ingester-rs

RUN pip install --upgrade pip && \
    pip install .

EXPOSE 9000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9000"]

