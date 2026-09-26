import json
import re
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from langchain_core.messages import SystemMessage, HumanMessage
from src.agent.llm import create_chat_model
from src.agent.multi_agent.registry import AgentRegistry, agent_registry
from src.core.logger import get_logger

logger = get_logger("MultiAgent.Supervisor")

SUPERVISOR_SYSTEM_PROMPT = """Sen kurumsal bir Yapay Zeka Orkestratörü ve Baş Ajanısın (Enterprise AI Supervisor Orchestrator).
Görevin, kullanıcının sorusunu analiz ederek en doğru uzman alt ajana yönlendirmek veya soru genel bir sohbet ise doğrudan yanıtlamaktır.

SİSTEMDE KAYITLI UZMAN AJANLAR:
{agent_descriptions}

YÖNLENDİRME VE KARAR KURALLARI:
1. Soru yukarıdaki uzman ajanlardan birinin alanına giriyorsa, ilgili ajanın adını ('agent' alanında) seç.
   - Şirket politikaları, prosedürler, PDF'ler, yönergeler -> doc_agent
   - Veritabanı tabloları, satış rakamları, ürün/stok bilgisi, operasyonel SQL verisi -> db_agent
   - Bir eylemin/talebin/durumun şirket kurallarına ve KVKK/güvenliğe uygunluk denetimi -> compliance_agent
   - (Varsa diğer özel ajanlar)
2. Soru genel bir selamlama (örn: "merhaba", "selam", "nasılsın"), sistemin ne işe yaradığını/yeteneklerini sorma veya genel bir bilgi ise, 'agent': 'finish' seç ve 'direct_response' alanında doğrudan nazik ve profesyonel bir cevap ver.

ÇIKTI FORMATI:
Yanıtını MUTLAKA aşağıdaki JSON formatında üret, başka hiçbir metin ekleme:
```json
{{
  "agent": "<seçilen_ajan_adı veya 'finish'>",
  "reason": "<kısa yönlendirme gerekçesi>",
  "direct_response": "<yalnızca agent 'finish' ise verilecek doğrudan cevap, aksi halde boş string>"
}}
```
"""


class SupervisorAgent:
    """The central orchestrator responsible for user intent classification, delegation, and direct fallback responses."""

    def __init__(self, chat_model=None, registry: Optional[AgentRegistry] = None):
        self._chat_model = chat_model
        self.registry = registry or agent_registry

    @property
    def chat_model(self):
        if self._chat_model is None:
            self._chat_model = create_chat_model()
        return self._chat_model

    def route(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze question and decide routing target or return direct answer."""
        start_time = time.time()
        question = state.get("question", "").strip()
        forced_agent = state.get("forced_agent")

        # 1. Honor explicit user agent selection if provided
        if forced_agent and self.registry.get(forced_agent):
            logger.info(f"[Supervisor] Forced routing to agent: '{forced_agent}'")
            return {"next_agent": forced_agent}

        # 2. Check for trivial greetings to bypass LLM routing latency
        lower_q = question.lower().strip()
        clean_q = re.sub(r"[^\w\s]", "", lower_q).strip()
        greeting_words = {
            "merhaba", "selam", "selamlar", "günaydın", "gunaydin",
            "iyi günler", "iyi gunler", "iyi akşamlar", "iyi aksamlar",
            "nasılsın", "nasilsin", "hello", "hi", "hey"
        }
        words = clean_q.split()
        is_greeting = (clean_q in greeting_words) or (
            len(words) <= 4
            and any(w in greeting_words for w in words)
            and not any(kw in clean_q for kw in ("sql", "select", "tablo", "doküman", "dokuman", "belge", "rapor", "mevzuat", "kvkk", "politika"))
        )
        if is_greeting:
            duration_ms = int((time.time() - start_time) * 1000)
            direct_reply = (
                "Merhaba! Ben kurumsal yapay zeka asistanınızım. "
                "Şirket dokümanları (PDF/DOCX), SQL veritabanı tabloları ve kurumsal uyum/güvenlik "
                "denetimleri konularında uzman ajanlarımla size yardımcı olmaya hazırım. Nasıl yardımcı olabilirim?"
            )
            return {
                "next_agent": "finish",
                "final_answer": direct_reply,
                "sources": [],
                "agent_trace": list(state.get("agent_trace", [])) + [{
                    "agent": "supervisor",
                    "display_name": "Supervisor Orchestrator",
                    "action": "direct_greeting",
                    "duration_ms": duration_ms,
                    "status": "success",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }],
            }

        # 3. Dynamic prompt with registered agents
        agent_descriptions = self.registry.get_supervisor_prompt()
        prompt = SUPERVISOR_SYSTEM_PROMPT.format(agent_descriptions=agent_descriptions)

        try:
            response = self.chat_model.invoke([
                SystemMessage(content=prompt),
                HumanMessage(content=question),
            ])
            content = response.content.strip()

            # Clean json fences
            json_text = re.sub(r"^```(?:json)?\s*", "", content, flags=re.IGNORECASE)
            json_text = re.sub(r"\s*```$", "", json_text).strip()

            data = json.loads(json_text)
            chosen_agent = data.get("agent", "doc_agent").strip()
            reason = data.get("reason", "")
            direct_response = data.get("direct_response", "").strip()

            logger.info(f"[Supervisor] Decision: agent='{chosen_agent}', reason='{reason}'")
        except Exception as e:
            logger.warning(f"[Supervisor] Routing JSON parse failed ({e}), using keyword heuristics")
            chosen_agent, reason, direct_response = self._heuristic_routing(question)

        duration_ms = int((time.time() - start_time) * 1000)
        trace_entry = {
            "agent": "supervisor",
            "display_name": "Supervisor Orchestrator",
            "action": "intent_routing",
            "target_agent": chosen_agent,
            "reason": reason,
            "duration_ms": duration_ms,
            "status": "success",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # If supervisor answered directly
        if chosen_agent == "finish":
            return {
                "next_agent": "finish",
                "final_answer": direct_response or "Sorunuza yanıt üretildi.",
                "sources": [],
                "agent_trace": list(state.get("agent_trace", [])) + [trace_entry],
            }

        # Validate chosen agent exists in registry; fallback to doc_agent if unknown
        if not self.registry.get(chosen_agent):
            logger.warning(f"[Supervisor] Agent '{chosen_agent}' not found in registry. Defaulting to 'doc_agent'.")
            chosen_agent = "doc_agent"

        return {
            "next_agent": chosen_agent,
            "agent_trace": list(state.get("agent_trace", [])) + [trace_entry],
        }

    def _heuristic_routing(self, question: str) -> tuple[str, str, str]:
        """Fallback rule-based routing when LLM JSON parsing encounters issues."""
        q = question.lower()

        # Database keywords
        if any(w in q for w in ("tablo", "sql", "satış", "ürün", "stok", "fiyat", "sipariş", "kaç adet", "ciro", "kayıt")):
            return "db_agent", "Veritabanı ve tablosal veri anahtar kelimeleri tespit edildi.", ""

        # Compliance keywords
        if any(w in q for w in ("uygun mu", "yasak mı", "izin", "ihlal", "kvkk", "ceza", "güvenlik kuralı", "kural ihlali")):
            return "compliance_agent", "Uyum, kural ve denetim anahtar kelimeleri tespit edildi.", ""

        # Default document RAG
        return "doc_agent", "Varsayılan kurumsal doküman araması seçildi.", ""
