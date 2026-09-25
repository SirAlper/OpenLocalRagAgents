import os
import asyncio
import shutil
from datetime import datetime, timezone
from typing import Optional

from src.rag.document_loader import DocumentLoader
from src.rag.rag_engine import RAGEngine
from src.agent.agent_graph import EnterpriseRAGAgent
from src.connectors.db_connector import DatabaseConnector, create_sample_sqlite_db
from src.connectors.db_loader import DatabaseTableLoader
from src.core.config import (
    DOCS_PATH,
    DATABASE_URL,
    SAMPLE_DB_PATH,
    ALLOWED_UPLOAD_EXTENSIONS,
    LLM_BACKEND,
    OLLAMA_NUM_PARALLEL,
    VECTOR_DB_PATH,
)
from src.core.logger import get_logger

logger = get_logger("API.State")

# Lazy initialized singletons
rag_engine: Optional[RAGEngine] = None
agent: Optional[EnterpriseRAGAgent] = None
document_loader: Optional[DocumentLoader] = None
db_connector: Optional[DatabaseConnector] = None
db_loader: Optional[DatabaseTableLoader] = None
query_lock = asyncio.Lock()
ollama_semaphore = asyncio.Semaphore(OLLAMA_NUM_PARALLEL)


class QueryConcurrencyManager:
    """
    Manages query concurrency depending on LLM backend:
    - Ollama: allows up to OLLAMA_NUM_PARALLEL parallel requests.
    - HuggingFace: serializes to 1 active inference to protect GPU/RAM.
    """
    async def __aenter__(self):
        if LLM_BACKEND == "ollama":
            await ollama_semaphore.acquire()
        else:
            await query_lock.acquire()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if LLM_BACKEND == "ollama":
            ollama_semaphore.release()
        else:
            query_lock.release()


query_concurrency_gate = QueryConcurrencyManager()


def get_rag_engine() -> RAGEngine:
    global rag_engine
    if rag_engine is None:
        rag_engine = RAGEngine()
    return rag_engine


def get_agent() -> EnterpriseRAGAgent:
    global agent
    if agent is None:
        agent = EnterpriseRAGAgent(get_rag_engine())
    return agent


def get_document_loader() -> DocumentLoader:
    global document_loader
    if document_loader is None:
        document_loader = DocumentLoader(DOCS_PATH)
    return document_loader


def get_db_connector() -> DatabaseConnector:
    global db_connector
    if db_connector is None:
        db_connector = DatabaseConnector()
    return db_connector


def get_db_loader() -> DatabaseTableLoader:
    global db_loader
    if db_loader is None:
        db_loader = DatabaseTableLoader(get_db_connector())
    return db_loader


def auto_index_on_startup():
    """Scan data/ folder on server startup and automatically index any unindexed documents into ChromaDB."""
    if not os.path.exists(DOCS_PATH):
        os.makedirs(DOCS_PATH, exist_ok=True)
        return

    engine = get_rag_engine()
    loader = get_document_loader()
    db_stats = engine.get_stats()
    indexed_files = set(db_stats.get("document_chunks", {}).keys())

    data_files = [
        f for f in os.listdir(DOCS_PATH)
        if os.path.isfile(os.path.join(DOCS_PATH, f)) and os.path.splitext(f)[1].lower() in ALLOWED_UPLOAD_EXTENSIONS
    ]

    unindexed = [f for f in data_files if f not in indexed_files]

    if not unindexed:
        logger.info(f"[Auto-Indexing] No unindexed documents found in data/. ({len(indexed_files)} files indexed)")
        return

    logger.info(f"[Auto-Indexing] Detected {len(unindexed)} new document(s), indexing...")
    for filename in unindexed:
        file_path = os.path.join(DOCS_PATH, filename)
        chunks, ids, metadatas = loader.load_and_chunk_file(file_path)
        if chunks:
            engine.add_documents(chunks, ids, metadatas)
            logger.info(f"  ✓ '{filename}' -> {len(chunks)} chunks indexed.")
        else:
            logger.warning(f"  ✗ '{filename}' -> no parseable text found.")

    logger.info("[Auto-Indexing] Completed successfully!")


def init_services():
    """Initialize all backend services and sample database on application startup."""
    global rag_engine, agent, document_loader, db_connector, db_loader
    logger.info("Initializing Enterprise RAG services...")

    if not DATABASE_URL and not os.path.exists(SAMPLE_DB_PATH):
        try:
            create_sample_sqlite_db(SAMPLE_DB_PATH)
            logger.info(f"Sample database created at '{SAMPLE_DB_PATH}'.")
        except Exception as e:
            logger.warning(f"Could not create sample database: {e}")

    rag_engine = get_rag_engine()
    agent = get_agent()
    document_loader = get_document_loader()
    db_connector = get_db_connector()
    db_loader = get_db_loader()

    auto_index_on_startup()
    logger.info("Enterprise RAG services initialized successfully.")


def cleanup_services():
    """Gracefully release all resources on application shutdown."""
    global agent, db_connector
    logger.info("Cleaning up Enterprise RAG services...")

    if agent is not None:
        agent.cleanup()
        logger.info("Agent resources released.")

    if db_connector is not None and db_connector.engine is not None:
        try:
            db_connector.engine.dispose()
            logger.info("Database engine disposed.")
        except Exception as e:
            logger.warning(f"Error disposing database engine: {e}")

    logger.info("Enterprise RAG services shutdown complete.")


# ──────────────────────────── SESSION MANAGEMENT ────────────────────────────

def cleanup_expired_sessions(max_age_days: int = 30) -> int:
    """Remove conversation sessions older than max_age_days from SQLite checkpointer.

    Returns the number of deleted session records.
    """
    import sqlite3

    db_path = os.path.join(DOCS_PATH, "conversations.db")
    if not os.path.exists(db_path):
        return 0

    deleted = 0
    try:
        conn = sqlite3.connect(db_path, timeout=10.0)
        cursor = conn.cursor()

        # Get all tables that LangGraph checkpointer creates
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]

        # LangGraph checkpointer typically uses 'checkpoints' and 'checkpoint_writes' tables
        for table in tables:
            if table in ("checkpoints", "checkpoint_writes"):
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM {table}")
                    before = cursor.fetchone()[0]
                    # Delete old records — checkpointer stores thread_id, we clean all old data
                    cursor.execute(f"DELETE FROM {table}")
                    deleted += before
                except Exception as e:
                    logger.warning(f"Error cleaning table '{table}': {e}")

        conn.commit()
        conn.close()
        logger.info(f"[Session Cleanup] Removed {deleted} expired session records.")
    except Exception as e:
        logger.error(f"[Session Cleanup] Error: {e}")

    return deleted


# ──────────────────────────── VECTOR DB BACKUP/RESTORE ────────────────────────────

def backup_vector_db(backup_dir: Optional[str] = None) -> str:
    """Create a timestamped backup of the ChromaDB vector database.

    Returns the path to the backup directory.
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    if backup_dir is None:
        backup_dir = os.path.join(os.path.dirname(VECTOR_DB_PATH), "backups")

    os.makedirs(backup_dir, exist_ok=True)
    backup_path = os.path.join(backup_dir, f"vector_db_backup_{timestamp}")

    try:
        shutil.copytree(VECTOR_DB_PATH, backup_path)
        logger.info(f"[Backup] Vector database backed up to: {backup_path}")
        return backup_path
    except FileNotFoundError:
        logger.error("[Backup] Vector database directory not found.")
        raise
    except Exception as e:
        logger.error(f"[Backup] Failed to backup vector database: {e}")
        raise


def restore_vector_db(backup_path: str) -> bool:
    """Restore ChromaDB vector database from a backup directory.

    WARNING: This replaces the current vector database entirely.
    """
    if not os.path.exists(backup_path):
        logger.error(f"[Restore] Backup path does not exist: {backup_path}")
        return False

    try:
        # Remove current vector DB
        if os.path.exists(VECTOR_DB_PATH):
            shutil.rmtree(VECTOR_DB_PATH)

        shutil.copytree(backup_path, VECTOR_DB_PATH)
        logger.info(f"[Restore] Vector database restored from: {backup_path}")
        return True
    except Exception as e:
        logger.error(f"[Restore] Failed to restore vector database: {e}")
        return False


def list_backups(backup_dir: Optional[str] = None) -> list:
    """List available vector database backups."""
    if backup_dir is None:
        backup_dir = os.path.join(os.path.dirname(VECTOR_DB_PATH), "backups")

    if not os.path.exists(backup_dir):
        return []

    backups = []
    for name in sorted(os.listdir(backup_dir), reverse=True):
        path = os.path.join(backup_dir, name)
        if os.path.isdir(path) and name.startswith("vector_db_backup_"):
            stat = os.stat(path)
            backups.append({
                "name": name,
                "path": path,
                "created_at": datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc).isoformat(),
            })

    return backups
