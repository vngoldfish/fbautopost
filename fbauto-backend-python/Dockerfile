# ==============================================================================
# Production Dockerfile for fbauto-backend-python
# Multi-Stage Build with Hardened Non-Root Security (Python 3.11-slim)
# ==============================================================================

# ------------------------------------------------------------------------------
# STAGE 1: Builder (Compiles wheels and prepares dependencies)
# ------------------------------------------------------------------------------
FROM python:3.11-slim AS builder

WORKDIR /build

# Install minimal build tools if required by binary extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Install packages into user local directory to easily copy to runner
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --user -r requirements.txt

# ------------------------------------------------------------------------------
# STAGE 2: Lean Production Runner (No compilers, hardened non-root user)
# ------------------------------------------------------------------------------
FROM python:3.11-slim AS runner

# Install curl for healthcheck and runtime diagnostics
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create dedicated non-root user and group
RUN groupadd -g 1001 appuser && \
    useradd -u 1001 -g appuser -s /bin/bash -m appuser

WORKDIR /app

# Copy Python packages from builder stage
COPY --from=builder /root/.local /home/appuser/.local

# Create persistent storage directories with non-root ownership
RUN mkdir -p /app/data /app/uploads /app/logs && \
    chown -R appuser:appuser /app/data /app/uploads /app/logs

# Copy application source code with non-root ownership
COPY --chown=appuser:appuser . .

# Setup environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH=/home/appuser/.local/bin:$PATH \
    PORT=19823 \
    HOST=0.0.0.0

# Switch to non-root execution
USER appuser

EXPOSE 19823

# Built-in Container Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:19823/health || python -c "import urllib.request; urllib.request.urlopen('http://localhost:19823/health', timeout=5)" || exit 1

# Production Entrypoint
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "19823", "--workers", "1"]
