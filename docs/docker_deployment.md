# 🐳 Docker Deployment Guide

This guide details how to deploy `OpenLocalRagAgents` using **Docker** and **Docker Compose** for production and on-premise enterprise environments.

---

## 🏗️ Architecture Overview

The containerized deployment supports up to three decoupled services communicating over an internal Docker bridge network:

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                                Host Machine                                 │
│                                                                             │
│   ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────────┐  │
│   │  ./models/       │    │  ./data/         │    │  ./vector_db/        │  │
│   │  (Weights ~6GB)  │    │  (DBs, Audits)   │    │  (ChromaDB vectors)  │  │
│   └────────┬─────────┘    └────────┬─────────┘    └────────┬─────────────┘  │
│            │ (Volume)              │ (Volume)              │ (Volume)       │
│            ▼                       ▼                       ▼                │
│   ┌──────────────────────────────────────────────────────────────────────┐  │
│   │                  rag_agents_backend (Port 8000)                      │  │
│   │            FastAPI + LangGraph + PyTorch (GPU/CPU)                   │  │
│   └──────────────────────▲────────────────────────▲──────────────────────┘  │
│                          │ (Internal: 8000)       │ (Internal: 11434)       │
│   ┌──────────────────────┴───────────────┐ ┌──────┴──────────────────────┐  │
│   │       rag_agents_frontend            │ │     rag_agents_ollama       │  │
│   │      (Streamlit - Port 8501)         │ │   (Optional Profile: ollama)│  │
│   └──────────────────────────────────────┘ └─────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

* **Zero-Bloat Image:** Model weights (`models/`), vector indexes (`vector_db/`), and enterprise documents/databases (`data/`) are mounted dynamically as external host volumes.
* **Multi-Stage Build Optimization:** The production [Dockerfile](file:///c:/Users/hanal/PycharmProjects/OpenLocalEnterpriseRag/Dockerfile) utilizes a two-stage build architecture:
  1. *Builder Stage:* Compiles native extensions and installs dependencies.
  2. *Runtime Stage:* Ultra-lean `python:3.11-slim` runner that copies only installed wheels and includes `curl` for container health checks, minimizing attack surface and disk footprint.
* **Data Persistence:** Rebuilding or updating containers never deletes your documents, audit logs (`audit.db`), user accounts (`users.json`), conversation checkpoints (`conversations.db`), or vector collections.

---

## 📋 Prerequisites

| Requirement | CPU Mode | NVIDIA GPU Mode |
| :--- | :--- | :--- |
| **Docker Engine** | Version 24.0+ | Version 24.0+ |
| **Docker Compose** | Compose v2 (`docker compose`) | Compose v2 (`docker compose`) |
| **NVIDIA Driver** | Not required | Version 525+ |
| **Container Toolkit** | Not required | [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) |

---

## ⚡ Quickstart in 3 Steps

### Step 1: Provision Local Models
Before starting the containers in HuggingFace mode, download the local models to `./models`:
```bash
python download_model.py
```
*(If using the external Ollama serving profile exclusively, HuggingFace model weights are optional).*

### Step 2: Launch the Services

#### Option A: CPU Execution (Default)
```bash
docker compose up -d --build
```

#### Option B: NVIDIA GPU Acceleration (CUDA Passthrough)
Pass host NVIDIA GPUs directly to the backend container:
```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build
```

#### Option C: With Ollama High-Concurrency Serving Profile
To spin up the bundled Ollama server alongside the backend and frontend:
```bash
docker compose --profile ollama up -d --build
```

### Step 3: Access Applications
* **Streamlit Web UI:** `http://localhost:8501`
* **FastAPI Swagger API:** `http://localhost:8000/docs`
* **Healthcheck API:** `http://localhost:8000/api/v1/stats`

> [!NOTE]
> **Default Admin Credentials:**  
> - **Username:** `admin`  
> - **Password:** `admin123`

---

## ⚙️ Custom Configuration (`.env`)

Place a `.env` file in the project root alongside `docker-compose.yml` to customize settings:

```env
# ─── LLM Serving Backend ───
# Options: "huggingface" (local in-process) or "ollama" (external server)
LLM_BACKEND=huggingface
OLLAMA_BASE_URL=http://ollama:11434
OLLAMA_MODEL=qwen2.5:7b
OLLAMA_NUM_PARALLEL=4

# ─── Authentication & RBAC ───
ADMIN_DEFAULT_USERNAME=admin
ADMIN_DEFAULT_PASSWORD=admin123
ACCESS_TOKEN_EXPIRE_MINUTES=60
REFRESH_TOKEN_EXPIRE_DAYS=7
# Optional custom HMAC secret (randomly generated and saved to data/.jwt_secret if empty):
# JWT_SECRET_KEY=your_custom_secret_key

# ─── Password Strength Policy ───
PASSWORD_MIN_LENGTH=8
PASSWORD_REQUIRE_UPPERCASE=true
PASSWORD_REQUIRE_LOWERCASE=true
PASSWORD_REQUIRE_DIGIT=true
PASSWORD_REQUIRE_SPECIAL=false

# ─── Relational Database (Optional) ───
DATABASE_URL=sqlite:///./data/sample_enterprise.db
DB_ALLOWED_TABLES=urunler,satislar,destek_talepleri
DB_MAX_ROWS=50

# ─── API & Security ───
CORS_ORIGINS=http://localhost:8501,http://127.0.0.1:8501,http://frontend:8501
MAX_UPLOAD_SIZE_MB=50
RATE_LIMIT_PER_MINUTE=30
LOG_LEVEL=INFO

# ─── Chunking Configuration ───
CHUNK_SIZE=600
CHUNK_OVERLAP=100
```

---

## 🔍 Useful Operational Commands

### View Logs in Real-time:
```bash
# All services
docker compose logs -f

# Backend API only
docker compose logs -f backend

# Frontend UI only
docker compose logs -f frontend

# Ollama service only (if profile active)
docker compose logs -f ollama
```

### Inspect Container Health:
```bash
docker compose ps
```

### Stop Services:
```bash
docker compose down
```

### Stop and Remove Volumes (Caution: Clears Ollama cache):
```bash
docker compose down -v
```

---

## 🛠️ Troubleshooting

### 1. NVIDIA Container Toolkit Verification:
To confirm GPU passthrough is functional on your Docker host:
```bash
docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi
```

### 2. Port Conflicts:
If port `8000` or `8501` is already in use on your host machine, update the port mapping in `docker-compose.yml`:
```yaml
ports:
  - "8080:8000"  # Changes host backend port to 8080
```

