# 🗄️ Enterprise Database Integration (SQLAlchemy)

`OpenLocalRagAgents` features a modular, database-agnostic connector layer (`src/connectors/`) built on **SQLAlchemy**. It enables plug-and-play connectivity to **PostgreSQL, MSSQL, MySQL, Oracle, or SQLite** without coupling to proprietary database vendor APIs.

---

## 🎯 Integration Patterns

The system supports two complementary database workflows:

1. **Live Text-to-SQL Agent Tooling:**
   - Designed for numeric, transactional, and dynamic operational data (sales, inventory, orders).
   - The LLM dynamically inspects accessible database schemas and executes safe read-only `SELECT` queries to formulate answers.
2. **Table-to-Vector ETL Synchronization:**
   - Extracts unstructured or semi-structured text columns (support tickets, CRM meeting notes, product descriptions), enriches them with contextual record headers, and indexes them into the ChromaDB vector store.

---

## ⚙️ Configuration (`.env` or Environment Variables)

Connect any relational database by defining a single `DATABASE_URL` environment variable:

```env
# 1. PostgreSQL
DATABASE_URL=postgresql+psycopg2://user:password@localhost:5432/enterprise_db

# 2. Microsoft SQL Server (MSSQL)
DATABASE_URL=mssql+pyodbc://user:password@host:1433/enterprise_db?driver=ODBC+Driver+17+for+SQL+Server

# 3. MySQL
DATABASE_URL=mysql+pymysql://user:password@localhost:3306/enterprise_db

# 4. Oracle
DATABASE_URL=oracle+cx_oracle://user:password@localhost:1521/?service_name=enterprise_db

# 5. Local Development / SQLite (Default):
DATABASE_URL=sqlite:///./data/sample_enterprise.db
```

### Security & Table Whitelisting:
Protect sensitive enterprise tables (salaries, credentials, PII) using configuration whitelists:

```env
# Allow access only to explicit business tables:
DB_ALLOWED_TABLES=urunler,satislar,destek_talepleri

# Maximum number of rows returned per query (default: 50):
DB_MAX_ROWS=50
```

---

## 🔒 Strict Read-Only Security Guard

To prevent accidental data corruption, privilege escalation, or SQL injection attacks, multi-layer verification is enforced at the code level (`src/connectors/db_connector.py` & `src/connectors/db_loader.py`):

* **AST-Based Lexical Parsing (`sqlparse`):** Rather than relying solely on surface regex patterns, queries are parsed into structured syntax trees via `sqlparse`:
  - **Comment Stripping:** Inline comments (`--`) and block comments (`/* ... */`) are removed prior to analysis to eliminate comment-based obfuscation bypasses.
  - **Stacked / Multi-Query Rejection:** Disallows chained query statements (e.g. `SELECT 1; DROP TABLE users;`) by enforcing exactly one valid statement per payload.
  - **Statement Type Verification:** Rejects any query whose root statement type is not strictly `SELECT` or `WITH`.
* **Prohibited Keyword Guards:** Scans parsed token trees to ensure destructive keywords (`DROP`, `INSERT`, `UPDATE`, `DELETE`, `ALTER`, `TRUNCATE`, `EXEC`, `CREATE`, `GRANT`, `REVOKE`, `INTO OUTFILE`, `LOAD_FILE`, etc.) do not appear in any clause.
* **Table Whitelist Enforcement:** If `DB_ALLOWED_TABLES` is configured, `_validate_sql_safety()` extracts all referenced table identifiers and verifies them against the whitelist. Any attempt to access unauthorized tables (e.g. `salaries`, `users`) is blocked before reaching the database engine.
* **ETL Loader Identifier Sanitization:** `DatabaseTableLoader.load_table_as_chunks()` validates that `table_name` is a valid identifier and exists in the connected database schema (`get_tables()`), eliminating SQL injection vectors.
* **Memory Protection:** Result sets are capped at `max_rows` (configurable via `DB_MAX_ROWS`, default: 50) to prevent server memory exhaustion.

---

## 🛠️ LangChain Agent Database Tools (`src.agent.tools`)

The platform exposes two native LangChain tools allowing agent workflows to safely interact with relational data:

| Tool | Purpose | Security Guardrails |
| :--- | :--- | :--- |
| `sql_db_schema` | Returns accessible database tables and column data types | Filters schemas against `DB_ALLOWED_TABLES` whitelist |
| `sql_db_query` | Executes safe read-only SQL queries and returns JSON rows | Enforces `SELECT`-only prefix, keyword blacklist, row capping |

Both tools can be dynamically bound to supported ChatModels (`ChatHuggingFace`, `ChatOllama`) via tool calling.

---

## 🔄 Table Vectorization (ETL Sync)

Synchronize a relational table into ChromaDB using either the Web UI or REST API:

### Via Streamlit UI:
1. Open the **"🗄️ Database"** section in the left sidebar.
2. Select your target table from the dropdown (e.g., `destek_talepleri`).
3. Click **"🔄 Vectorize Table"**.

### Via REST API:
> [!NOTE]
> Requires `Authorization: Bearer <token>` with `admin` role.

```bash
curl -X POST "http://localhost:8000/api/v1/database/sync-table" \
     -H "Authorization: Bearer <admin_token>" \
     -H "Content-Type: application/json" \
     -d '{
       "table_name": "destek_talepleri",
       "text_columns": ["konu", "aciklama", "cozum_notu"],
       "title_column": "konu",
       "id_column": "id"
     }'
```

---

## 🧪 Zero-Config Sample Database (`sample_enterprise.db`)

To enable immediate testing upon cloning the repository without spinning up an external database, the platform automatically generates `data/sample_enterprise.db` on initial startup.

Pre-populated mock enterprise datasets include:
- **`urunler` (Products):** SKU, categories, unit prices, and inventory stock levels.
- **`satislar` (Sales):** Order numbers, customer names, regions, total amounts, and transaction dates.
- **`destek_talepleri` (Support Tickets):** Issue subjects, problem descriptions, resolution logs, and ticket status.
