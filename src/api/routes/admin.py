"""Admin and Audit Trail API Routes.

Exposes endpoints for compliance audit log querying, audit statistics,
session cleanup, and vector database backup/restore operations.
"""
import os
import asyncio
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query

from src.auth.dependencies import require_role
from src.auth.models import User
from src.core.audit import audit_logger
from src.core.config import VECTOR_DB_PATH
from src.api.state import (
    cleanup_expired_sessions,
    backup_vector_db,
    restore_vector_db,
    list_backups,
)
from src.core.logger import get_logger

logger = get_logger("API.Admin")
router = APIRouter(prefix="/api/v1/admin", tags=["Admin & Audit Trail"])


@router.get("/audit-logs", summary="List and Filter Compliance Audit Logs")
async def get_audit_logs(
    username: Optional[str] = Query(None, description="Filter by user"),
    action: Optional[str] = Query(None, description="Filter by action (query, upload, delete, login, etc.)"),
    status: Optional[str] = Query(None, description="Filter by status (success, error, denied)"),
    start_date: Optional[str] = Query(None, description="Filter from ISO timestamp"),
    end_date: Optional[str] = Query(None, description="Filter to ISO timestamp"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _: User = Depends(require_role("admin")),
):
    """Retrieve tamper-evident audit logs with multi-parameter filtering (Admin only)."""
    total = await audit_logger.acount_logs(username=username, action=action, status=status)
    logs = await audit_logger.aquery_logs(
        username=username,
        action=action,
        status=status,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )
    return {
        "status": "success",
        "total": total,
        "count": len(logs),
        "limit": limit,
        "offset": offset,
        "logs": logs,
    }


@router.get("/audit-stats", summary="Audit Trail Metrics and Compliance Summary")
async def get_audit_stats(_: User = Depends(require_role("admin"))):
    """Summary of enterprise actions, queries processed, and compliance indicators (Admin only)."""
    total_logs = await audit_logger.acount_logs()
    total_queries = await audit_logger.acount_logs(action="query")
    total_stream_queries = await audit_logger.acount_logs(action="query_stream")
    total_uploads = await audit_logger.acount_logs(action="upload")
    total_deletions = await audit_logger.acount_logs(action="delete")
    total_logins = await audit_logger.acount_logs(action="login")
    total_errors = await audit_logger.acount_logs(status="error")
    total_feedback = await audit_logger.acount_logs(action="feedback")

    return {
        "status": "success",
        "total_records": total_logs,
        "queries_executed": total_queries,
        "stream_queries_executed": total_stream_queries,
        "documents_uploaded": total_uploads,
        "documents_deleted": total_deletions,
        "login_events": total_logins,
        "error_events": total_errors,
        "feedback_events": total_feedback,
    }


# ──────────────────────────── SESSION MANAGEMENT ────────────────────────────

@router.post("/cleanup-sessions", summary="Cleanup Expired Conversation Sessions")
async def cleanup_sessions(
    max_age_days: int = Query(30, ge=1, le=365, description="Maximum session age in days"),
    current_admin: User = Depends(require_role("admin")),
):
    """Remove conversation sessions older than the specified number of days (Admin only)."""
    deleted = await asyncio.to_thread(cleanup_expired_sessions, max_age_days=max_age_days)

    await audit_logger.alog(
        username=current_admin.username,
        role=current_admin.role,
        action="session_cleanup",
        detail=f"Cleaned up sessions older than {max_age_days} days ({deleted} records removed)",
        status="success",
    )

    return {
        "status": "success",
        "message": f"Removed {deleted} expired session records.",
        "deleted_records": deleted,
    }


# ──────────────────────────── VECTOR DB BACKUP/RESTORE ────────────────────────────

@router.post("/backup", summary="Create Vector Database Backup")
async def create_backup(current_admin: User = Depends(require_role("admin"))):
    """Create a timestamped backup of the ChromaDB vector database (Admin only)."""
    try:
        backup_path = await asyncio.to_thread(backup_vector_db)
        await audit_logger.alog(
            username=current_admin.username,
            role=current_admin.role,
            action="backup_create",
            detail=f"Vector database backed up to: {backup_path}",
            status="success",
        )
        return {
            "status": "success",
            "message": "Vector database backup created successfully.",
            "backup_path": backup_path,
        }
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Vector database directory not found.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Backup failed: {e}")


@router.get("/backups", summary="List Available Backups")
async def get_backups(_: User = Depends(require_role("admin"))):
    """List all available vector database backups (Admin only)."""
    backups = await asyncio.to_thread(list_backups)
    return {
        "status": "success",
        "count": len(backups),
        "backups": backups,
    }


@router.post("/restore", summary="Restore Vector Database from Backup")
async def restore_backup(
    backup_name: str = Query(..., description="Name of the backup directory to restore"),
    current_admin: User = Depends(require_role("admin")),
):
    """
    Restore ChromaDB vector database from a named backup (Admin only).
    WARNING: This replaces the current vector database entirely.
    """
    backup_dir = os.path.join(os.path.dirname(VECTOR_DB_PATH), "backups")
    backup_path = os.path.join(backup_dir, backup_name)

    # Security: prevent path traversal
    real_backup = os.path.realpath(backup_path)
    real_backup_dir = os.path.realpath(backup_dir)
    if not real_backup.startswith(real_backup_dir):
        raise HTTPException(status_code=400, detail="Invalid backup name.")

    success = await asyncio.to_thread(restore_vector_db, backup_path)
    if not success:
        raise HTTPException(status_code=400, detail=f"Restore failed. Backup '{backup_name}' may not exist.")

    await audit_logger.alog(
        username=current_admin.username,
        role=current_admin.role,
        action="backup_restore",
        detail=f"Vector database restored from: {backup_name}",
        status="success",
    )

    return {
        "status": "success",
        "message": f"Vector database restored from '{backup_name}'. Restart the server for changes to take effect.",
    }
