# 🔌 REST API Documentation

`OpenLocalRagAgents` exposes a high-performance REST API built on **FastAPI** to enable turnkey integration with enterprise portals, CRM, ERP, and internal workplace bots.

The interactive OpenAPI Swagger UI is available at `http://localhost:8000/docs` whenever the server is running.

---

## 📋 Endpoints Overview

| Method | Endpoint | Required Role | Description |
| :--- | :--- | :---: | :--- |
| `POST` | `/api/v1/auth/login` | Public | Obtain signed JWT Bearer access token and refresh token |
| `POST` | `/api/v1/auth/refresh` | Public | Exchange refresh token for fresh access and refresh token pair |
| `GET` | `/api/v1/auth/me` | Authenticated | View current authenticated user profile |
| `POST` | `/api/v1/auth/register` | `admin` | Register new user account with password policy enforcement |
| `GET` | `/api/v1/auth/users` | `admin` | List all registered enterprise user accounts |
| `PATCH` | `/api/v1/auth/users/{username}` | `admin` | Update user status (disable/enable), role, or reset password |
| `DELETE` | `/api/v1/auth/users/{username}` | `admin` | Permanently delete a registered user account |
| `GET` | `/api/v1/stats` | Authenticated | Hardware acceleration, active models, backend info, and index counts |
| `GET` | `/api/v1/documents` | Authenticated | List uploaded and indexed enterprise documents with chunk stats |
| `POST` | `/api/v1/upload-file` | `admin`, `editor` | Upload new PDF, DOCX, or TXT document and auto-index into ChromaDB |
| `DELETE` | `/api/v1/documents/{filename}` | `admin`, `editor` | Permanently delete document from disk and purge chunks from vector store |
| `POST` | `/api/v1/query` | Authenticated | Batch question answering with multi-turn session memory |
| `POST` | `/api/v1/query-stream` | Authenticated | Stage event streaming (NDJSON protocol) with dynamic rewrite and final answer |
| `POST` | `/api/v1/feedback` | Authenticated | Submit thumbs-up/down evaluation on agent answers |
| `GET` | `/api/v1/database/status` | Authenticated | Database connection status, dialect type, and schema summary |
| `POST` | `/api/v1/database/test-query` | `admin` | Execute safe read-only SELECT queries |
| `POST` | `/api/v1/database/sync-table` | `admin` | Convert database table rows into ChromaDB vector chunks |
| `GET` | `/api/v1/admin/audit-logs` | `admin` | Filter and inspect compliance audit trail logs |
| `GET` | `/api/v1/admin/audit-stats` | `admin` | Metrics summary (queries, uploads, logins, errors, feedback) |
| `POST` | `/api/v1/admin/cleanup-sessions`| `admin` | Prune conversation sessions older than specified age |
| `POST` | `/api/v1/admin/backup` | `admin` | Create timestamped ChromaDB vector database snapshot |
| `GET` | `/api/v1/admin/backups` | `admin` | List available ChromaDB backup snapshots |
| `POST` | `/api/v1/admin/restore` | `admin` | Restore ChromaDB vector database from an existing snapshot |

> [!NOTE]
> All protected endpoints require the HTTP header:  
> `Authorization: Bearer <your_access_token>`

---

## 🔐 1. Authentication & User Management Endpoints

### 1.1 User Login (`POST /api/v1/auth/login`)
Authenticates credentials and issues a signed JWT Bearer access token valid for `ACCESS_TOKEN_EXPIRE_MINUTES` (default: 60 minutes) and a long-lived refresh token valid for `REFRESH_TOKEN_EXPIRE_DAYS` (default: 7 days).

```bash
curl -X POST "http://localhost:8000/api/v1/auth/login" \
     -H "Content-Type: application/json" \
     -d '{
       "username": "admin",
       "password": "admin123"
     }'
```

**Example Response (HTTP 200):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "role": "admin",
  "username": "admin",
  "expires_in": 3600
}
```

---

### 1.2 Refresh Access Token (`POST /api/v1/auth/refresh`)
Exchange a valid refresh token for a fresh access token and rotated refresh token pair without re-entering credentials.

```bash
curl -X POST "http://localhost:8000/api/v1/auth/refresh" \
     -H "Content-Type: application/json" \
     -d '{
       "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
     }'
```

**Example Response (HTTP 200):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "role": "admin",
  "username": "admin",
  "expires_in": 3600
}
```

---

### 1.3 Current User Profile (`GET /api/v1/auth/me`)
Returns the profile and role of the caller identified by the JWT token.

```bash
curl -X GET "http://localhost:8000/api/v1/auth/me" \
     -H "Authorization: Bearer <token>"
```

**Example Response:**
```json
{
  "username": "admin",
  "role": "admin",
  "disabled": false,
  "created_at": "2026-09-18T10:00:00"
}
```

---

### 1.4 Register User (`POST /api/v1/auth/register`)
Registers a new enterprise user. Restricted to `admin` role.

* **Roles Available:** `admin`, `editor`, `viewer`
* **Password Policy:** Passwords must meet configurable enterprise security rules (minimum 8 characters, uppercase, lowercase, and digit required by default).

```bash
curl -X POST "http://localhost:8000/api/v1/auth/register" \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{
       "username": "jane_analyst",
       "password": "SecurePassword123!",
       "role": "editor"
     }'
```

**Example Response (HTTP 201):**
```json
{
  "username": "jane_analyst",
  "role": "editor",
  "disabled": false,
  "created_at": "2026-09-18T11:20:00"
}
```

---

### 1.5 List All Users (`GET /api/v1/auth/users`)
Lists all registered enterprise users. Restricted to `admin` role.

```bash
curl -X GET "http://localhost:8000/api/v1/auth/users" \
     -H "Authorization: Bearer <token>"
```

---

### 1.6 Update User (`PATCH /api/v1/auth/users/{username}`)
Modifies a user's role, status (enable/disable), or resets their password. Restricted to `admin` role.

```bash
curl -X PATCH "http://localhost:8000/api/v1/auth/users/jane_analyst" \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{
       "role": "admin",
       "disabled": false
     }'
```

---

### 1.7 Delete User (`DELETE /api/v1/auth/users/{username}`)
Deletes a user account. The primary default administrator cannot be deleted. Restricted to `admin` role.

```bash
curl -X DELETE "http://localhost:8000/api/v1/auth/users/jane_analyst" \
     -H "Authorization: Bearer <token>"
```

---

## 📄 2. Document & System Endpoints

### 2.1 System Statistics (`GET /api/v1/stats`)
Returns hardware acceleration status, active embedding/LLM models, backend architecture (HuggingFace/Ollama), and vector collection statistics.

```bash
curl -X GET "http://localhost:8000/api/v1/stats" \
     -H "Authorization: Bearer <token>"
```

**Example Response:**
```json
{
  "status": "success",
  "device": "CUDA (NVIDIA GPU)",
  "llm_backend": "huggingface",
  "embedding_model": ".../models/bge-m3",
  "llm_model": ".../models/qwen2.5-1.5b",
  "ollama_base_url": null,
  "total_chunks": 42,
  "total_documents": 3,
  "documents": {
    "NovaTech_Security_Policy.pdf": 14,
    "IT_Support_Runbook.docx": 18,
    "Company_FAQ.txt": 10
  },
  "database": {
    "status": "connected",
    "dialect": "sqlite",
    "table_count": 3
  }
}
```

---

### 2.2 List Documents (`GET /api/v1/documents`)
Returns file metadata and vector chunk counts for all uploaded files in `data/`.

```bash
curl -X GET "http://localhost:8000/api/v1/documents" \
     -H "Authorization: Bearer <token>"
```

**Example Response:**
```json
{
  "status": "success",
  "count": 1,
  "documents": [
    {
      "filename": "NovaTech_Security_Policy.pdf",
      "size_kb": 124.5,
      "chunk_count": 14,
      "modified_at": "2026-09-18 10:15:22"
    }
  ]
}
```

---

### 2.3 Upload Document (`POST /api/v1/upload-file`)
Accepts multipart file upload, applies contextual chunking, and persists vectors to ChromaDB.

* **Required Role:** `admin` or `editor`
* **Supported Formats:** `.pdf`, `.docx`, `.txt`
* **Maximum Size:** Default 50 MB (`MAX_UPLOAD_SIZE_MB`)
* **Security:** Enforces filename sanitization (`os.path.basename`) and prevents path traversal.

```bash
curl -X POST "http://localhost:8000/api/v1/upload-file" \
     -H "Authorization: Bearer <token>" \
     -F "file=@NovaTech_Security_Policy.pdf"
```

**Example Response (HTTP 200):**
```json
{
  "status": "success",
  "message": "'NovaTech_Security_Policy.pdf' successfully uploaded and indexed.",
  "filename": "NovaTech_Security_Policy.pdf",
  "chunk_count": 14
}
```

---

### 2.4 Delete Document (`DELETE /api/v1/documents/{filename}`)
Permanently deletes the file from `data/` and purges its vector embeddings from ChromaDB.

* **Required Role:** `admin` or `editor`

```bash
curl -X DELETE "http://localhost:8000/api/v1/documents/NovaTech_Security_Policy.pdf" \
     -H "Authorization: Bearer <token>"
```

---

## 🤖 3. AI Query Endpoints

### 3.1 Batch Query (`POST /api/v1/query`)
Executes the full LangGraph Self-RAG workflow (`retrieve` -> `generate` -> `grade` -> [optional `refine`] -> `END`).

* **Request Parameters:**
  * `question` *(string, required)*: The enterprise user question (1-4000 characters).
  * `session_id` *(string, optional)*: Alphanumeric identifier to maintain multi-turn conversational memory in `data/conversations.db`.

```bash
curl -X POST "http://localhost:8000/api/v1/query" \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{
       "question": "What is the password rotation policy for workstations?",
       "session_id": "session-user-123"
     }'
```

**Example Response:**
```json
{
  "status": "success",
  "answer": "According to the company information security policy, user passwords must be updated at least every 90 days.",
  "sources": [
    {
      "source": "NovaTech_Security_Policy.pdf",
      "chunk_index": 2,
      "content": "[Document: NovaTech Information Security | CODE: SEC-04]\nClause 3: User passwords must be updated every 90 days...",
      "distance": 0.421,
      "reranker_score": 4.812
    }
  ],
  "hallucination_grade": "yes",
  "is_refined": false
}
```

---

### 3.2 Event Streaming Query (`POST /api/v1/query-stream`)
Streams real-time node stage transitions and final answer via newline-delimited JSON (**NDJSON**).

```bash
curl -X POST "http://localhost:8000/api/v1/query-stream" \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{
       "question": "How does the hardware replacement approval process work?",
       "session_id": "session-user-123"
     }'
```

**Delivered NDJSON Event Sequence:**
```json
{"type": "status", "message": "🔄 Optimizing search query...", "node": "rewrite"}
{"type": "status", "message": "🔍 Searching relevant enterprise documents...", "node": "retrieve"}
{"type": "sources", "sources": [{"source": "IT_Support_Runbook.docx", "chunk_index": 1, ...}]}
{"type": "status", "message": "✍️ Preparing response...", "node": "generate"}
{"type": "status", "message": "🛡️ Verifying factual accuracy...", "node": "grade"}
{"type": "grade", "grade": "yes", "passed": true, "is_refined": false}
{"type": "done", "answer": "...", "sources": [...], "is_refined": false}
```
*(If unverified, emits a `"node": "refine"` stage and re-evaluates before emitting `"type": "done"`).*

---

### 3.3 Answer Evaluation Feedback (`POST /api/v1/feedback`)
Records user thumbs-up / thumbs-down evaluation and optional comments for answer quality tracking and governance audits.

* **Required Role:** Authenticated (`admin`, `editor`, `viewer`)

```bash
curl -X POST "http://localhost:8000/api/v1/feedback" \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{
       "question": "How does the hardware replacement approval process work?",
       "feedback": "positive",
       "comment": "Accurate response with exact runbook references."
     }'
```

**Example Response (HTTP 200):**
```json
{
  "status": "success",
  "message": "Feedback recorded."
}
```

---

## 🗄️ 4. Enterprise Database Endpoints

### 4.1 Database Status & Schema (`GET /api/v1/database/status`)
Returns database connection status, dialect type, and formatted schema summary.

```bash
curl -X GET "http://localhost:8000/api/v1/database/status" \
     -H "Authorization: Bearer <token>"
```

**Example Response:**
```json
{
  "status": "success",
  "connection": {
    "status": "connected",
    "dialect": "sqlite",
    "tables": ["urunler", "satislar", "destek_talepleri"]
  },
  "schema_summary": "Table: urunler\n  - id (INTEGER)\n  - urun_adi (VARCHAR)\n  - fiyat (FLOAT)..."
}
```

---

### 4.2 Safe Read-Only Query (`POST /api/v1/database/test-query`)
Executes an ad-hoc read-only `SELECT` query against the connected database. Queries with modification keywords (`DROP`, `DELETE`, `UPDATE`, `INSERT`) or unauthorized tables are blocked.

* **Required Role:** `admin`

```bash
curl -X POST "http://localhost:8000/api/v1/database/test-query" \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{
       "query": "SELECT urun_adi, stok_miktari FROM urunler WHERE stok_miktari < 20"
     }'
```

**Example Response:**
```json
{
  "status": "success",
  "data": {
    "status": "success",
    "columns": ["urun_adi", "stok_miktari"],
    "rows": [
      {"urun_adi": "Laptop Pro 15", "stok_miktari": 7},
      {"urun_adi": "Kablosuz Mouse", "stok_miktari": 12}
    ],
    "count": 2
  }
}
```

---

### 4.3 Table ETL Vectorization (`POST /api/v1/database/sync-table`)
Converts relational database rows into contextual text chunks and indexes them into ChromaDB for dense retrieval.

* **Required Role:** `admin`

```bash
curl -X POST "http://localhost:8000/api/v1/database/sync-table" \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{
       "table_name": "destek_talepleri",
       "text_columns": ["konu", "aciklama", "cozum_notu"],
       "title_column": "konu",
       "id_column": "id"
     }'
```

---

## 📜 5. Compliance & Admin Audit Endpoints

### 5.1 Audit Logs (`GET /api/v1/admin/audit-logs`)
Retrieves compliance audit logs with filtering across user, action, status, and date range.

* **Required Role:** `admin`
* **Query Parameters:**
  * `username` *(optional)*: Filter by username (e.g. `admin`).
  * `action` *(optional)*: Filter by action (`query`, `upload`, `delete`, `login`, `db_query`, `db_sync_table`).
  * `status` *(optional)*: Filter by result status (`success`, `error`, `denied`, `warning`).
  * `start_date` / `end_date` *(optional)*: ISO timestamps.
  * `limit` *(int, default 50)*: Number of logs to retrieve (1-200).
  * `offset` *(int, default 0)*: Offset for pagination.

```bash
curl -X GET "http://localhost:8000/api/v1/admin/audit-logs?action=query&status=success&limit=25" \
     -H "Authorization: Bearer <token>"
```

**Example Response:**
```json
{
  "status": "success",
  "total": 120,
  "count": 25,
  "limit": 25,
  "offset": 0,
  "logs": [
    {
      "id": 1,
      "timestamp": "2026-09-18T10:30:15",
      "username": "jane_analyst",
      "role": "editor",
      "action": "query",
      "detail": "What is the password update policy?",
      "sources": "[\"NovaTech_Security_Policy.pdf\"]",
      "duration_ms": 342,
      "ip_address": "192.168.1.50",
      "status": "success"
    }
  ]
}
```

---

### 5.2 Audit Statistics (`GET /api/v1/admin/audit-stats`)
Returns aggregated governance metrics: total audit records, queries executed, files uploaded, files deleted, logins, and errors.

* **Required Role:** `admin`

```bash
curl -X GET "http://localhost:8000/api/v1/admin/audit-stats" \
     -H "Authorization: Bearer <token>"
```

**Example Response:**
```json
{
  "status": "success",
  "total_records": 150,
  "queries_executed": 112,
  "stream_queries_executed": 45,
  "documents_uploaded": 8,
  "documents_deleted": 2,
  "login_events": 24,
  "error_events": 4,
  "feedback_events": 18
}
```

---

### 5.3 Session Cleanup (`POST /api/v1/admin/cleanup-sessions`)
Removes stale conversation sessions and checkpointer records older than the specified retention window.

* **Required Role:** `admin`
* **Query Parameters:**
  * `max_age_days` *(int, optional, default: 30, range: 1-365)*: Maximum session age in days before pruning.

```bash
curl -X POST "http://localhost:8000/api/v1/admin/cleanup-sessions?max_age_days=14" \
     -H "Authorization: Bearer <admin_token>"
```

**Example Response (HTTP 200):**
```json
{
  "status": "success",
  "message": "Removed 12 expired session records.",
  "deleted_records": 12
}
```

---

### 5.4 Create Vector Database Backup (`POST /api/v1/admin/backup`)
Creates a complete, atomic timestamped archive snapshot of the ChromaDB vector database directory.

* **Required Role:** `admin`

```bash
curl -X POST "http://localhost:8000/api/v1/admin/backup" \
     -H "Authorization: Bearer <admin_token>"
```

**Example Response (HTTP 200):**
```json
{
  "status": "success",
  "message": "Vector database backup created successfully.",
  "backup_path": "backups/vector_db_20260925_220000"
}
```

---

### 5.5 List Vector Database Backups (`GET /api/v1/admin/backups`)
Lists all available ChromaDB backup snapshot archives with timestamp and size metadata.

* **Required Role:** `admin`

```bash
curl -X GET "http://localhost:8000/api/v1/admin/backups" \
     -H "Authorization: Bearer <admin_token>"
```

**Example Response (HTTP 200):**
```json
{
  "status": "success",
  "count": 2,
  "backups": [
    {
      "name": "vector_db_20260925_220000",
      "created_at": "2026-09-25T22:00:00",
      "size_mb": 42.5
    },
    {
      "name": "vector_db_20260924_180000",
      "created_at": "2026-09-24T18:00:00",
      "size_mb": 38.1
    }
  ]
}
```

---

### 5.6 Restore Vector Database (`POST /api/v1/admin/restore`)
Restores the ChromaDB vector database from an existing named snapshot archive.

> [!CAUTION]
> Restoring a backup completely replaces the active vector database. An automatic pre-restore backup of the current database is created before overwriting.

* **Required Role:** `admin`
* **Query Parameters:**
  * `backup_name` *(string, required)*: Directory name of the backup to restore (from `/api/v1/admin/backups`).

```bash
curl -X POST "http://localhost:8000/api/v1/admin/restore?backup_name=vector_db_20260925_220000" \
     -H "Authorization: Bearer <admin_token>"
```

**Example Response (HTTP 200):**
```json
{
  "status": "success",
  "message": "Vector database successfully restored from backup: vector_db_20260925_220000"
}
```

---

## 🛡️ 6. Rate Limiting & Protection

The API implements an in-memory sliding-window per-IP rate limiter to safeguard on-premise hardware against brute-force attacks and resource exhaustion:

* **Configuration:** Configured via `RATE_LIMIT_PER_MINUTE` in `.env` (default: `30` requests/minute/IP).
* **Bypassed Routes:** Documentation endpoints (`/docs`, `/redoc`, `/openapi.json`) are excluded.
* **HTTP 429 Too Many Requests:** When a client exceeds the limit, the API immediately returns HTTP 429:

```json
{
  "detail": "Rate limit exceeded. Maximum 30 requests per minute.",
  "retry_after": 60
}
```

* **Header:** Includes `Retry-After: 60` indicating the number of seconds until the sliding window clears.

---

## 🔒 7. CORS Configuration

CORS origins are configured via the `CORS_ORIGINS` environment variable in `.env`:

```env
# Comma-separated list of allowed web origins
CORS_ORIGINS=http://localhost:8501,http://127.0.0.1:8501
```

Credentials (`allow_credentials=True`), all methods, and all headers are permitted for these trusted origins.
