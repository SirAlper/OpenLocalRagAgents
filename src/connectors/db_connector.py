import re
import os
import sqlite3
from typing import Optional, Dict, Any, List
from src.core.config import DATABASE_URL, DB_ALLOWED_TABLES, DB_MAX_ROWS, SAMPLE_DB_PATH
from src.core.logger import get_logger

logger = get_logger("DatabaseConnector")


class DatabaseConnector:
    """SQLAlchemy-based universal, database-agnostic, and secure database connector.

    Manages relational databases (PostgreSQL, MySQL, SQLite, MSSQL, Oracle)
    through a unified interface with strict read-only security guards.
    """

    def __init__(
        self,
        database_url: Optional[str] = None,
        allowed_tables: Optional[List[str]] = None,
        max_rows: int = DB_MAX_ROWS
    ):
        self.database_url = database_url if database_url is not None else DATABASE_URL
        self.allowed_tables = allowed_tables if allowed_tables is not None else DB_ALLOWED_TABLES
        self.max_rows = max_rows
        self.engine = None
        self.is_connected = False
        self._last_error = None

        if self.database_url:
            self._init_engine()

    def _init_engine(self):
        """Initialize the SQLAlchemy engine."""
        try:
            from sqlalchemy import create_engine
            # SQLite thread safety and path handling
            connect_args = {}
            if self.database_url.startswith("sqlite"):
                connect_args = {"check_same_thread": False}

            self.engine = create_engine(
                self.database_url,
                pool_pre_ping=True,
                connect_args=connect_args
            )
            # Test connection
            with self.engine.connect() as conn:
                pass
            self.is_connected = True
            self._last_error = None
        except Exception as e:
            self.engine = None
            self.is_connected = False
            self._last_error = str(e)
            logger.error(f"Failed to connect to database: {e}")

    def test_connection(self) -> Dict[str, Any]:
        """Test database connection, return dialect and accessible tables."""
        if not self.database_url:
            return {
                "status": "not_configured",
                "message": "Database URL (DATABASE_URL) is not configured.",
                "dialect": None,
                "tables": []
            }

        if not self.is_connected or not self.engine:
            self._init_engine()

        if not self.is_connected:
            return {
                "status": "error",
                "message": f"Connection error: {self._last_error}",
                "dialect": None,
                "tables": []
            }

        try:
            tables = self.get_tables()
            dialect_name = self.engine.dialect.name
            return {
                "status": "connected",
                "message": f"Successfully connected ({dialect_name.upper()}).",
                "dialect": dialect_name,
                "tables": tables,
                "table_count": len(tables)
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Error querying tables: {e}",
                "dialect": self.engine.dialect.name if self.engine else None,
                "tables": []
            }

    def get_tables(self) -> List[str]:
        """Return list of accessible table names (filtered by allowed_tables)."""
        if not self.is_connected or not self.engine:
            return []

        from sqlalchemy import inspect
        inspector = inspect(self.engine)
        all_tables = inspector.get_table_names()

        # Exclude internal / system tables
        ignored_tables = {"sqlite_sequence"}
        tables = [t for t in all_tables if t not in ignored_tables]

        if self.allowed_tables:
            tables = [t for t in tables if t in self.allowed_tables]

        return sorted(tables)

    def get_schema_summary(self) -> str:
        """Generate schema summary (tables, columns, types) as text for LLM prompts."""
        if not self.is_connected or not self.engine:
            return "Database connection is not active."

        try:
            from sqlalchemy import inspect
            inspector = inspect(self.engine)
            tables = self.get_tables()

            if not tables:
                return "No accessible tables found."

            schema_lines = [f"# DATABASE SCHEMA (Dialect: {self.engine.dialect.name.upper()})"]

            for table in tables:
                columns = inspector.get_columns(table)
                pk_constraint = inspector.get_pk_constraint(table)
                pks = set(pk_constraint.get("constrained_columns", []) if pk_constraint else [])

                col_strs = []
                for col in columns:
                    col_name = col["name"]
                    col_type = str(col["type"])
                    is_pk = " [PK]" if col_name in pks else ""
                    col_strs.append(f"{col_name} ({col_type}{is_pk})")

                schema_lines.append(f"Table: {table}")
                schema_lines.append(f"  Columns: {', '.join(col_strs)}")

            return "\n".join(schema_lines)
        except Exception as e:
            return f"Error extracting schema: {e}"

    def _validate_sql_safety(self, query: str) -> tuple[bool, str]:
        """Validate SQL query safety using both regex and AST-based parsing.

        Returns (is_safe, error_message). If is_safe is True, error_message is empty.
        """
        clean_query = query.strip().rstrip(";").strip()

        # 1. Strict Read-Only Guard against data modification keywords
        forbidden_pattern = r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|EXEC|EXECUTE|CREATE|GRANT|REVOKE|REPLACE)\b"
        if re.search(forbidden_pattern, clean_query, re.IGNORECASE):
            return False, "Security Guard: Only read-only (SELECT) queries are allowed."

        # 2. Must start with SELECT or WITH
        if not re.match(r"^(SELECT|WITH)\b", clean_query, re.IGNORECASE):
            return False, "Invalid Query: Query must start with 'SELECT' or 'WITH'."

        # 3. AST-based validation using sqlparse (defense against comment-based bypass)
        try:
            import sqlparse
            parsed = sqlparse.parse(clean_query)
            if not parsed:
                return False, "Invalid Query: Could not parse SQL statement."

            for statement in parsed:
                stmt_type = statement.get_type()
                if stmt_type and stmt_type.upper() not in ("SELECT", "UNKNOWN"):
                    return False, f"Security Guard: Statement type '{stmt_type}' is not permitted. Only SELECT is allowed."

                # Check for dangerous tokens within parsed statement
                flat_tokens = list(statement.flatten())
                for token in flat_tokens:
                    token_upper = str(token).upper().strip()
                    if token_upper in ("INSERT", "UPDATE", "DELETE", "DROP", "ALTER",
                                       "TRUNCATE", "EXEC", "EXECUTE", "CREATE",
                                       "GRANT", "REVOKE", "REPLACE"):
                        return False, f"Security Guard: Forbidden keyword '{token_upper}' detected in parsed query."
        except ImportError:
            # sqlparse not installed, fall back to regex-only validation
            logger.warning("sqlparse not installed, using regex-only SQL validation.")
        except Exception as e:
            logger.warning(f"SQL parsing error, falling back to regex validation: {e}")

        # 4. Table Access Restriction (if allowed_tables is specified)
        if self.allowed_tables:
            referenced_tables = re.findall(r"\b(?:FROM|JOIN)\s+([a-zA-Z0-9_]+)", clean_query, re.IGNORECASE)
            for tbl in referenced_tables:
                if tbl not in self.allowed_tables:
                    logger.warning(f"Unauthorized table access attempt: '{tbl}' in query: '{clean_query}'")
                    return False, f"Security Guard: Access to table '{tbl}' is not permitted."

        return True, ""

    def execute_query(self, query: str) -> Dict[str, Any]:
        """Execute SQL query subject to strict read-only security guards.

        Security Rules:
        1. Only 'SELECT' or 'WITH ... SELECT' queries are permitted.
        2. 'INSERT', 'UPDATE', 'DELETE', 'DROP', 'ALTER', 'TRUNCATE', 'EXEC' are strictly blocked.
        3. AST-based SQL parsing validates query structure beyond simple regex.
        4. Result rows are capped at max_rows.
        """
        if not self.is_connected or not self.engine:
            return {
                "status": "error",
                "message": "Database connection is not active.",
                "columns": [],
                "rows": []
            }

        clean_query = query.strip().rstrip(";").strip()

        # Validate SQL safety
        is_safe, error_msg = self._validate_sql_safety(clean_query)
        if not is_safe:
            return {
                "status": "error",
                "message": error_msg,
                "columns": [],
                "rows": []
            }

        try:
            from sqlalchemy import text
            with self.engine.connect() as conn:
                result = conn.execute(text(clean_query))
                columns = list(result.keys()) if result.returns_rows else []
                raw_rows = result.fetchmany(self.max_rows) if result.returns_rows else []

                # Convert to JSON serializable dictionaries
                formatted_rows = []
                for row in raw_rows:
                    row_dict = {}
                    for col, val in zip(columns, row):
                        if val is None:
                            row_dict[col] = None
                        elif isinstance(val, (int, float, bool, str)):
                            row_dict[col] = val
                        else:
                            row_dict[col] = str(val)
                    formatted_rows.append(row_dict)

                return {
                    "status": "success",
                    "columns": columns,
                    "rows": formatted_rows,
                    "row_count": len(formatted_rows),
                    "query": clean_query
                }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Error executing query: {e}",
                "columns": [],
                "rows": []
            }


def create_sample_sqlite_db(db_path: Optional[str] = None) -> str:
    """Generate sample enterprise SQLite database for instant zero-config testing."""
    target_path = db_path or SAMPLE_DB_PATH
    os.makedirs(os.path.dirname(target_path), exist_ok=True)

    conn = sqlite3.connect(target_path)
    cursor = conn.cursor()

    # 1. Products Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS urunler (
        urun_id INTEGER PRIMARY KEY AUTOINCREMENT,
        sku TEXT UNIQUE NOT NULL,
        urun_adi TEXT NOT NULL,
        kategori TEXT NOT NULL,
        birim_fiyat REAL NOT NULL,
        stok_adedi INTEGER NOT NULL
    );
    """)

    # 2. Sales Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS satislar (
        satis_id INTEGER PRIMARY KEY AUTOINCREMENT,
        siparis_no TEXT NOT NULL,
        musteri_adi TEXT NOT NULL,
        urun_id INTEGER,
        adet INTEGER NOT NULL,
        toplam_tutar REAL NOT NULL,
        bolge TEXT NOT NULL,
        tarih TEXT NOT NULL,
        FOREIGN KEY (urun_id) REFERENCES urunler(urun_id)
    );
    """)

    # 3. Support Requests Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS destek_talepleri (
        talep_id INTEGER PRIMARY KEY AUTOINCREMENT,
        talep_kodu TEXT NOT NULL,
        musteri_adi TEXT NOT NULL,
        konu TEXT NOT NULL,
        detay TEXT NOT NULL,
        cozum TEXT NOT NULL,
        durum TEXT NOT NULL
    );
    """)

    # Populate initial sample records if empty
    cursor.execute("SELECT COUNT(*) FROM urunler;")
    if cursor.fetchone()[0] == 0:
        cursor.executemany("""
        INSERT INTO urunler (sku, urun_adi, kategori, birim_fiyat, stok_adedi) VALUES (?, ?, ?, ?, ?);
        """, [
            ("NT-SRV-01", "NovaTech Enterprise Server X1", "Hardware", 85000.0, 14),
            ("NT-LPT-02", "NovaTech ProBook 15 G3", "Computer", 38500.0, 45),
            ("NT-SEC-03", "NovaShield Enterprise Firewall", "Security", 62000.0, 8),
            ("NT-SFT-04", "NovaERP Cloud License (Annual)", "Software", 120000.0, 100),
            ("NT-MON-05", "NovaView 27-inch 4K Monitor", "Accessory", 9400.0, 60),
        ])

        cursor.executemany("""
        INSERT INTO satislar (siparis_no, musteri_adi, urun_id, adet, toplam_tutar, bolge, tarih) VALUES (?, ?, ?, ?, ?, ?, ?);
        """, [
            ("ORD-2026-001", "Anadolu Logistics Corp.", 1, 2, 170000.0, "Marmara", "2026-01-15"),
            ("ORD-2026-002", "Capital Health Group", 2, 5, 192500.0, "Central", "2026-01-18"),
            ("ORD-2026-003", "Aegean IT Systems", 3, 1, 62000.0, "Aegean", "2026-02-02"),
            ("ORD-2026-004", "Mediterranean Retail Ltd.", 4, 1, 120000.0, "Mediterranean", "2026-02-14"),
            ("ORD-2026-005", "Anadolu Logistics Corp.", 5, 4, 37600.0, "Marmara", "2026-03-01"),
        ])

        cursor.executemany("""
        INSERT INTO destek_talepleri (talep_kodu, musteri_adi, konu, detay, cozum, durum) VALUES (?, ?, ?, ?, ?, ?);
        """, [
            ("SR-2026-101", "Anadolu Logistics Corp.", "Server BIOS Update", "IPMI disconnected after Enterprise Server X1 reboot.", "Applied IPMI firmware 2.14 patch and reset static IP.", "Resolved"),
            ("SR-2026-102", "Capital Health Group", "ERP License Activation Error", "Users receiving 'License Limit Exceeded' warning.", "Terminated stale sessions on license server and cleaned connection pool.", "Resolved"),
            ("SR-2026-103", "Aegean IT Systems", "Firewall VPN Setup", "IKEv2 key mismatch when establishing IPsec tunnel.", "Synchronized Phase-1 and Phase-2 encryption algorithms to AES-256.", "Resolved"),
        ])

    conn.commit()
    conn.close()
    return target_path
