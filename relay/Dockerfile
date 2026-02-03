# Atmosphere Relay Server Dockerfile
# Lightweight Python image for WebSocket relay

FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir \
    fastapi==0.109.0 \
    uvicorn[standard]==0.27.0 \
    websockets==12.0

# Copy server code
COPY server.py .

# Expose WebSocket port
EXPOSE 8765

# Environment variables with defaults
ENV PORT=8765
ENV HOST=0.0.0.0
ENV LOG_LEVEL=info

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8765/health')" || exit 1

# Run the server
CMD ["python", "server.py"]
