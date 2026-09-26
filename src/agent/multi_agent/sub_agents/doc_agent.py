import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from src.agent.multi_agent.base import BaseSubAgent
from src.agent.multi_agent.registry import register_agent
from src.agent.llm import create_chat_model
from src.agent.prompts import build_rag_messages, build_rewrite_messages, NO_CONTEXT_RESPONSE, FALLBACK_RESPONSE
from src.rag.rag_engine import RAGEngine
from src.core.logger import get_logger

logger = get_logger("MultiAgent.DocAgent")


@register_agent
class DocumentRagAgent(BaseSubAgent):
    """Specialist sub-agent for dense vector search and factual grounding over enterprise documents."""

    name: str = "doc_agent"
    display_name: str = "Belge & Politika RAG Ajanı"
    description: str = (
        "Şirket içi politika, prosedür, yönetmelik, teknik şartname, PDF, DOCX ve metin "
        "dokümanlarından semantik arama yapmak ve belgelere dayalı doğrulanmış yanıtlar üretmek için kullanılır."
    )

    def __init__(self, chat_model=None, rag_engine: Optional[RAGEngine] = None):
        super().__init__(chat_model=chat_model)
        self._rag_engine = rag_engine

    def _get_engine(self) -> RAGEngine:
        if self._rag_engine is None:
            from src.api.state import get_rag_engine
            self._rag_engine = get_rag_engine()
        return self._rag_engine

    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Execute two-stage dense retrieval and grounded answer generation."""
        start_time = time.time()
        question = state.get("question", "").strip()
        chat_history = state.get("chat_history", [])

        logger.info(f"[{self.name}] Executing document search for: '{question}'")

        # 1. Query reformulation for multi-turn coherence
        search_query = question
        if chat_history and len(question.split()) > 3:
            try:
                rewrite_messages = build_rewrite_messages(question, chat_history)
                rewrite_resp = self.chat_model.invoke(rewrite_messages)
                rewritten = rewrite_resp.content.strip()
                if rewritten and len(rewritten) < 500:
                    search_query = rewritten
                    logger.info(f"[{self.name}] Query rewritten to: '{search_query}'")
            except Exception as e:
                logger.warning(f"[{self.name}] Query rewrite failed, using original: {e}")

        # 2. Retrieve documents via BGE-M3 + Cross-Encoder Reranker
        engine = self._get_engine()
        search_result = engine.search(search_query)
        context = search_result.get("context", "").strip()
        sources = search_result.get("sources", [])

        # 3. Handle zero-context fallback
        if not context:
            duration_ms = int((time.time() - start_time) * 1000)
            trace_entry = {
                "agent": self.name,
                "display_name": self.display_name,
                "action": "document_retrieval",
                "sources_count": 0,
                "duration_ms": duration_ms,
                "status": "no_context",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            return {
                "final_answer": NO_CONTEXT_RESPONSE,
                "sources": [],
                "agent_trace": list(state.get("agent_trace", [])) + [trace_entry],
            }

        # 4. Generate grounded response with chat history context
        try:
            messages = build_rag_messages(context, question, chat_history)
            response = self.chat_model.invoke(messages)
            answer = response.content.strip()
        except Exception as e:
            logger.error(f"[{self.name}] LLM generation error: {e}")
            answer = FALLBACK_RESPONSE

        duration_ms = int((time.time() - start_time) * 1000)
        trace_entry = {
            "agent": self.name,
            "display_name": self.display_name,
            "action": "retrieval_and_generation",
            "search_query": search_query,
            "sources_count": len(sources),
            "duration_ms": duration_ms,
            "status": "success",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        return {
            "final_answer": answer,
            "sources": sources,
            "agent_trace": list(state.get("agent_trace", [])) + [trace_entry],
        }
