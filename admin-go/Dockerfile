FROM golang:1.23.4 AS builder

WORKDIR /build

# Copy go mod files
COPY go.mod go.sum* ./
RUN go mod tidy && go mod download

# Copy source code (exclude scheduler files)
COPY api/ ./api/
COPY db/ ./db/
COPY config/ ./config/
COPY docker/ ./docker/
COPY enforcer/ ./enforcer/
COPY main.go ./
COPY go.mod go.sum* ./

# Ensure deps are tidy
RUN go mod tidy

# Build the binary
RUN CGO_ENABLED=1 GOOS=linux go build -o admin-go .

# Final stage
FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y ca-certificates curl wget gnupg lsb-release && \
    mkdir -p /etc/apt/keyrings && \
    curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian \
    $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null && \
    apt-get update && apt-get install -y docker-ce-cli docker-compose-plugin && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy binary from builder
COPY --from=builder /build/admin-go .

# Copy templates and static files
COPY templates/ ./templates/
COPY static/ ./static/

# Expose port
EXPOSE 9999

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:9999/health || exit 1

# Run
CMD ["./admin-go"]
