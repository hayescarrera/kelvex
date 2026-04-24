# ColdGrid Edge Agent — Multi-stage Docker build
#
# Builds a minimal container for ARM64 gateway devices.
# The final image is ~15MB with just the binary + CA certs.
#
# Build:
#   docker build --platform linux/arm64 -t coldgrid/edge-agent .
#
# Run:
#   docker run -d \
#     --name coldgrid-agent \
#     --restart unless-stopped \
#     --network host \
#     -v /etc/coldgrid:/etc/coldgrid:ro \
#     -v /var/lib/coldgrid:/var/lib/coldgrid \
#     -p 8080:8080 \
#     coldgrid/edge-agent

# ── Build stage ──────────────────────────────────────
FROM golang:1.22-bookworm AS builder

# Install cross-compilation deps for SQLite (CGO)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc-aarch64-linux-gnu \
    libc6-dev-arm64-cross \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download

COPY . .

ARG VERSION=dev
ARG GIT_COMMIT=unknown

RUN CGO_ENABLED=1 go build \
    -ldflags "-s -w -X main.Version=${VERSION} -X main.GitCommit=${GIT_COMMIT} -X main.BuildTime=$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    -o /coldgrid-agent \
    ./cmd/coldgrid-agent

# ── Runtime stage ────────────────────────────────────
FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create directories
RUN mkdir -p /etc/coldgrid /var/lib/coldgrid

COPY --from=builder /coldgrid-agent /usr/local/bin/coldgrid-agent

# Local dashboard port
EXPOSE 8080

# Health check via the local API
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8080/api/status || exit 1

ENTRYPOINT ["/usr/local/bin/coldgrid-agent"]
CMD ["-config", "/etc/coldgrid/agent.yaml"]
