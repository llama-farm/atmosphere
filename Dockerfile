# =============================================================================
# Atmosphere - The Internet of Intent
# Multi-stage Docker build for minimal image size
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1: Build UI (optional - uncomment if UI exists)
# -----------------------------------------------------------------------------
# FROM node:20-alpine AS ui-builder
# WORKDIR /app/ui
# COPY ui/package*.json ./
# RUN npm ci --production=false
# COPY ui/ ./
# RUN npm run build

# -----------------------------------------------------------------------------
# Stage 2: Build Python package
# -----------------------------------------------------------------------------
FROM python:3.12-slim AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install dependencies first (better caching)
COPY pyproject.toml README.md LICENSE ./
RUN pip install --no-cache-dir --upgrade pip wheel

# Copy source code
COPY atmosphere/ atmosphere/

# Copy pre-built UI if available
# COPY --from=ui-builder /app/ui/dist atmosphere/ui/dist/

# Install the package
RUN pip install --no-cache-dir .

# -----------------------------------------------------------------------------
# Stage 3: Runtime image (minimal)
# -----------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

# Labels for OCI compliance
LABEL org.opencontainers.image.title="Atmosphere"
LABEL org.opencontainers.image.description="The Internet of Intent - semantic mesh routing for AI"
LABEL org.opencontainers.image.version="1.0.0"
LABEL org.opencontainers.image.source="https://github.com/llama-farm/atmosphere"
LABEL org.opencontainers.image.licenses="Apache-2.0"
LABEL org.opencontainers.image.vendor="Llama Farm"

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash --uid 1000 atmosphere

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Set up data directory
RUN mkdir -p /data && chown atmosphere:atmosphere /data
VOLUME /data

# Switch to non-root user
USER atmosphere
WORKDIR /data

# Default environment variables
ENV ATMOSPHERE_DATA_DIR=/data \
    ATMOSPHERE_HOST=0.0.0.0 \
    ATMOSPHERE_PORT=8000 \
    ATMOSPHERE_LOG_LEVEL=info \
    PYTHONUNBUFFERED=1

# Expose ports
# 8000 - Main API server
# 11450 - Mesh gossip protocol (optional)
EXPOSE 8000 11450

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Entry point
ENTRYPOINT ["atmosphere"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8000"]
