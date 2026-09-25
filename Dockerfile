# ==============================================================================
# OpenLocalRagAgents — Enterprise Production Dockerfile
# Multi-stage optimized build for Python 3.11 with CUDA / CPU PyTorch
# ==============================================================================

# ────────────── Stage 1: Builder ──────────────
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

# Install build tools needed for compiling Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install PyTorch with CUDA 12.1 support
RUN pip install --no-cache-dir torch torchvision torchaudio \
    --index-url https://download.pytorch.org/whl/cu121

# Install project dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ────────────── Stage 2: Runtime ──────────────
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive \
    HF_HUB_DISABLE_TELEMETRY=1 \
    TOKENIZERS_PARALLELISM=false

WORKDIR /app

# Install only runtime OS dependencies (curl for healthchecks)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder stage
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Create necessary persistent volume mount directories
RUN mkdir -p /app/data /app/models /app/vector_db /app/backups

# Copy project source code
COPY . /app

# Expose backend API (8000) and frontend Streamlit (8501) ports
EXPOSE 8000 8501

# Healthcheck monitoring the FastAPI backend
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/stats || exit 1

# Default command launches the FastAPI gateway
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
