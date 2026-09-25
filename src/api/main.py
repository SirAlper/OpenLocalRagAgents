from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.core.config import CORS_ORIGINS, RATE_LIMIT_PER_MINUTE
from src.core.logger import get_logger
from src.api.state import (
    init_services,
    cleanup_services,
    get_rag_engine,
    get_agent,
    get_document_loader,
    get_db_connector,
    get_db_loader,
    auto_index_on_startup,
    query_lock,
)
from src.api.routes import (
    documents_router,
    query_router,
    database_router,
    auth_router,
    admin_router,
)

logger = get_logger("API")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI Lifespan context manager to initialize models on startup and cleanup on shutdown."""
    init_services()
    yield
    cleanup_services()


app = FastAPI(
    title="OpenLocalRagAgents API",
    description="Privacy-first, on-premise RAG and Agentic AI gateway with zero cloud dependencies.",
    version="2.0.0",
    lifespan=lifespan
)

# CORS configuration (reads allowed origins from config/env)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ──────────────────────────── RATE LIMITING MIDDLEWARE ────────────────────────────

import time
from collections import defaultdict

_rate_limit_store: dict = defaultdict(list)
_RATE_WINDOW = 60  # seconds


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Per-IP rate limiting middleware to prevent API abuse."""
    # Skip rate limiting for docs and health endpoints
    if request.url.path in ("/docs", "/openapi.json", "/redoc"):
        return await call_next(request)

    client_ip = request.client.host if request.client else "unknown"
    now = time.time()

    # Clean old entries
    _rate_limit_store[client_ip] = [
        ts for ts in _rate_limit_store[client_ip] if now - ts < _RATE_WINDOW
    ]

    if len(_rate_limit_store[client_ip]) >= RATE_LIMIT_PER_MINUTE:
        logger.warning(f"Rate limit exceeded for IP: {client_ip}")
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={
                "detail": f"Rate limit exceeded. Maximum {RATE_LIMIT_PER_MINUTE} requests per minute.",
                "retry_after": _RATE_WINDOW,
            },
            headers={"Retry-After": str(_RATE_WINDOW)},
        )

    _rate_limit_store[client_ip].append(now)
    return await call_next(request)


# Include modular API routers
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(documents_router)
app.include_router(query_router)
app.include_router(database_router)

__all__ = [
    "app",
    "get_rag_engine",
    "get_agent",
    "get_document_loader",
    "get_db_connector",
    "get_db_loader",
    "auto_index_on_startup",
    "query_lock",
]

if __name__ == "__main__":
    import uvicorn
    # Use reload=False to prevent reloading model weights on disk modifications
    uvicorn.run("src.api.main:app", host="0.0.0.0", port=8000, reload=False)
