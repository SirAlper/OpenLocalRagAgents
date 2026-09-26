import time
import json
import re
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from langchain_core.messages import SystemMessage, HumanMessage
from src.agent.multi_agent.base import BaseSubAgent
from src.agent.multi_agent.registry import register_agent
from src.agent.llm import create_chat_model
from src.connectors.db_connector import DatabaseConnector
from src.core.logger import get_logger

logger = get_logger("MultiAgent.DbAgent")

SQL_GENERATOR_SYSTEM_PROMPT = """Sen uzman bir SQL analisti ve veritabanı uzmanısın.
Görevin, kullanıcının sorusunu yanıtlamak için ilişkisel veritabanında çalışacak güvenli, salt-okunur (read-only) tek bir SQL sorgusu üretmektir.

Kullanılabilir Veritabanı Şeması:
{schema_summary}

GÜVENLİK VE ÇALIŞMA KURALLARI:
1. YALNIZCA 'SELECT' veya 'WITH ... SELECT' sorgusu üret.
2. Kesinlikle INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE veya DDL/DML komutları KULLANMA.
3. Yalnızca şemada listelenen tablolardan sorgu yap.
4. Yanıtında kod blokları (```sql ... ```) veya ek açıklama yazma. SADECE çalıştırılabilir saf SQL sorgusunu yaz.
5. Sonuç satır sayısını sınırlandırmak için gerekirse LIMIT kullan.
"""

SQL_EXPLAINER_SYSTEM_PROMPT = """Sen profesyonel bir iş zekası ve veri analisti asistanısın.
Kullanıcının sorusu ve veritabanından dönen SQL sorgu sonuçları aşağıda verilmiştir.
Sonuçları kullanıcıya açık, anlaşılır, profesyonel ve gerekirse Markdown tablosu veya maddeleme kullanarak özetle.
Eğer sonuç kümesi boşsa, veritabanında ilgili kaydın bulunamadığını nazikçe belirt.
"""


@register_agent
class DatabaseAgent(BaseSubAgent):
    """Specialist sub-agent for querying relational databases with strict AST read-only guards."""

    name: str = "db_agent"
    display_name: str = "SQL & Veritabanı Ajanı"
    description: str = (
        "İlişkisel veritabanı tablolarındaki (ürünler, stoklar, satışlar, siparişler, destek talepleri vb.) "
        "yapılandırılmış sayısal ve operasyonel verileri güvenli SQL ile sorgulamak ve raporlamak için kullanılır."
    )

    def __init__(self, chat_model=None, db_connector: Optional[DatabaseConnector] = None):
        super().__init__(chat_model=chat_model)
        self._db_connector = db_connector

    def _get_connector(self) -> DatabaseConnector:
        if self._db_connector is None:
            from src.api.state import get_db_connector
            self._db_connector = get_db_connector()
        return self._db_connector

    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Generate, validate, and execute read-only SQL queries to answer operational data questions."""
        start_time = time.time()
        question = state.get("question", "").strip()
        connector = self._get_connector()

        if not connector.is_connected:
            duration_ms = int((time.time() - start_time) * 1000)
            msg = "Veritabanı bağlantısı şu anda aktif değil veya yapılandırılmamış."
            trace_entry = {
                "agent": self.name,
                "display_name": self.display_name,
                "action": "db_connection_check",
                "duration_ms": duration_ms,
                "status": "not_connected",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            return {
                "final_answer": msg,
                "sources": [],
                "agent_trace": list(state.get("agent_trace", [])) + [trace_entry],
            }

        # 1. Fetch available schema
        schema_summary = connector.get_schema_summary()

        # 2. Generate SQL via LLM
        prompt = SQL_GENERATOR_SYSTEM_PROMPT.format(schema_summary=schema_summary)
        try:
            sql_response = self.chat_model.invoke([
                SystemMessage(content=prompt),
                HumanMessage(content=question),
            ])
            generated_sql = sql_response.content.strip()

            # Clean markdown code blocks if present
            sql_cleaned = re.sub(r"^```(?:sql)?\s*", "", generated_sql, flags=re.IGNORECASE)
            sql_cleaned = re.sub(r"\s*```$", "", sql_cleaned).strip()
            # Take only the first query if multiple lines with semicolon
            if ";" in sql_cleaned:
                sql_cleaned = sql_cleaned.split(";")[0].strip()

            logger.info(f"[{self.name}] Generated SQL: '{sql_cleaned}'")
        except Exception as e:
            logger.error(f"[{self.name}] Error during SQL generation: {e}")
            duration_ms = int((time.time() - start_time) * 1000)
            return {
                "final_answer": f"Veritabanı sorgusu oluşturulurken bir hata oluştu: {e}",
                "sources": [],
                "agent_trace": list(state.get("agent_trace", [])) + [{
                    "agent": self.name,
                    "action": "sql_generation",
                    "status": "error",
                    "duration_ms": duration_ms,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }],
            }

        # 3. Execute safe query via DatabaseConnector AST security guards
        query_result = connector.execute_query(sql_cleaned)

        if query_result.get("status") == "error":
            duration_ms = int((time.time() - start_time) * 1000)
            err_msg = query_result.get("error", "Bilinmeyen veritabanı hatası")
            return {
                "final_answer": f"Veritabanı sorgusu güvenlik veya sözdizimi nedeniyle çalıştırılamadı:\n`{err_msg}`",
                "sources": [],
                "agent_trace": list(state.get("agent_trace", [])) + [{
                    "agent": self.name,
                    "action": "sql_execution",
                    "sql": sql_cleaned,
                    "status": "rejected",
                    "error": err_msg,
                    "duration_ms": duration_ms,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }],
            }

        rows = query_result.get("rows", [])
        columns = query_result.get("columns", [])
        count = query_result.get("count", 0)

        # 4. Synthesize tabular result into user-friendly explanation
        explain_prompt = (
            f"Kullanıcı Sorusu: {question}\n\n"
            f"Çalıştırılan SQL: {sql_cleaned}\n"
            f"Dönen Kolonlar: {', '.join(columns)}\n"
            f"Dönen Satır Sayısı: {count}\n"
            f"Veri (JSON):\n{json.dumps(rows[:30], ensure_ascii=False, indent=2)}"
        )

        try:
            summary_response = self.chat_model.invoke([
                SystemMessage(content=SQL_EXPLAINER_SYSTEM_PROMPT),
                HumanMessage(content=explain_prompt),
            ])
            answer = summary_response.content.strip()
        except Exception as e:
            logger.error(f"[{self.name}] Error synthesizing SQL results: {e}")
            answer = f"Sorgu başarıyla çalıştırıldı ({count} kayıt bulundu):\n\n```json\n{json.dumps(rows[:10], ensure_ascii=False, indent=2)}\n```"

        duration_ms = int((time.time() - start_time) * 1000)
        trace_entry = {
            "agent": self.name,
            "display_name": self.display_name,
            "action": "sql_query_and_explain",
            "sql": sql_cleaned,
            "row_count": count,
            "duration_ms": duration_ms,
            "status": "success",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Format sources as database table metadata
        sources = [{
            "source": f"Database: {connector.dialect}",
            "chunk_index": 0,
            "content": f"Executed SQL: {sql_cleaned} ({count} rows returned)",
        }]

        return {
            "final_answer": answer,
            "sources": sources,
            "agent_trace": list(state.get("agent_trace", [])) + [trace_entry],
        }
