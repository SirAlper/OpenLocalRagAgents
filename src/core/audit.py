import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.core.config import DOCS_PATH
from src.core.logger import get_logger

logger = get_logger("Core.Audit")


class AuditLogger:
    """
    Thread-safe enterprise audit trail logger.
    Persists structured compliance events (queries, uploads, logins, security alerts)
    into SQLite database for KVKK, ISO 27001, and internal audits.
    """

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            os.makedirs(DOCS_PATH, exist_ok=True)
            db_path = os.path.join(DOCS_PATH, "audit.db")
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    @contextmanager
    def _get_connection(self):
        """Context manager providing thread-safe SQLite connection that is guaranteed to close."""
        conn = sqlite3.connect(self.db_path, timeout=10.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        """Create audit log schema and indexes if not existing."""
        with self._lock:
            dir_name = os.path.dirname(os.path.abspath(self.db_path))
            os.makedirs(dir_name, exist_ok=True)
            with self._get_connection() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS audit_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        username TEXT NOT NULL,
                        user_role TEXT NOT NULL,
                        action TEXT NOT NULL,
                        detail TEXT,
                        sources_used TEXT,
                        answer_preview TEXT,
                        ip_address TEXT,
                        duration_ms INTEGER,
                        status TEXT NOT NULL
                    )
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_logs(timestamp)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_username ON audit_logs(username)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_logs(action)")
                conn.commit()

    def log(
        self,
        username: str,
        role: str,
        action: str,
        detail: Optional[str] = None,
        sources: Optional[List[Any]] = None,
        answer_preview: Optional[str] = None,
        ip_address: Optional[str] = None,
        duration_ms: Optional[int] = None,
        status: str = "success",
    ) -> int:
        """
        Record an immutable audit log entry.
        Returns the inserted record ID.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        sources_json = json.dumps(sources, ensure_ascii=False) if sources is not None else None
        preview = answer_preview[:500] if answer_preview else None

        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.execute(
                        """
                        INSERT INTO audit_logs (
                            timestamp, username, user_role, action,
                            detail, sources_used, answer_preview,
                            ip_address, duration_ms, status
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            now_iso,
                            username,
                            role,
                            action,
                            detail,
                            sources_json,
                            preview,
                            ip_address,
                            duration_ms,
                            status,
                        ),
                    )
                    conn.commit()
                    return cursor.lastrowid or 0
            except Exception as e:
                logger.error(f"Failed to write audit log: {e}")
                return -1

    async def alog(
        self,
        username: str,
        role: str,
        action: str,
        detail: Optional[str] = None,
        sources: Optional[List[Any]] = None,
        answer_preview: Optional[str] = None,
        ip_address: Optional[str] = None,
        duration_ms: Optional[int] = None,
        status: str = "success",
    ) -> int:
        """Asynchronously record an audit log without blocking the asyncio event loop."""
        import asyncio
        return await asyncio.to_thread(
            self.log,
            username=username,
            role=role,
            action=action,
            detail=detail,
            sources=sources,
            answer_preview=answer_preview,
            ip_address=ip_address,
            duration_ms=duration_ms,
            status=status,
        )

    def query_logs(
        self,
        username: Optional[str] = None,
        action: Optional[str] = None,
        status: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        Query and filter audit trail records.
        """
        clauses = []
        params = []

        if username:
            clauses.append("username = ?")
            params.append(username)
        if action:
            clauses.append("action = ?")
            params.append(action)
        if status:
            clauses.append("status = ?")
            params.append(status)
        if start_date:
            clauses.append("timestamp >= ?")
            params.append(start_date)
        if end_date:
            clauses.append("timestamp <= ?")
            params.append(end_date)

        where_str = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query_sql = f"""
            SELECT * FROM audit_logs
            {where_str}
            ORDER BY id DESC
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])

        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.execute(query_sql, params)
                rows = cursor.fetchall()
                results = []
                for row in rows:
                    d = dict(row)
                    if d.get("sources_used"):
                        try:
                            d["sources_used"] = json.loads(d["sources_used"])
                        except Exception:
                            pass
                    results.append(d)
                return results

    def count_logs(
        self,
        username: Optional[str] = None,
        action: Optional[str] = None,
        status: Optional[str] = None,
    ) -> int:
        """Get count of audit logs matching filters."""
        clauses = []
        params = []
        if username:
            clauses.append("username = ?")
            params.append(username)
        if action:
            clauses.append("action = ?")
            params.append(action)
        if status:
            clauses.append("status = ?")
            params.append(status)

        where_str = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query_sql = f"SELECT COUNT(*) FROM audit_logs {where_str}"

        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.execute(query_sql, params)
                return cursor.fetchone()[0]

    async def aquery_logs(
        self,
        username: Optional[str] = None,
        action: Optional[str] = None,
        status: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Asynchronously query audit trail records."""
        import asyncio
        return await asyncio.to_thread(
            self.query_logs,
            username=username,
            action=action,
            status=status,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            offset=offset,
        )

    async def acount_logs(
        self,
        username: Optional[str] = None,
        action: Optional[str] = None,
        status: Optional[str] = None,
    ) -> int:
        """Asynchronously count audit trail records."""
        import asyncio
        return await asyncio.to_thread(
            self.count_logs,
            username=username,
            action=action,
            status=status,
        )


# Singleton instance
audit_logger = AuditLogger()
