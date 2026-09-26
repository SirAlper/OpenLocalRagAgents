import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from langchain_core.messages import SystemMessage, HumanMessage
from src.agent.multi_agent.base import BaseSubAgent
from src.agent.multi_agent.registry import register_agent
from src.agent.llm import create_chat_model
from src.rag.rag_engine import RAGEngine
from src.core.logger import get_logger

logger = get_logger("MultiAgent.ComplianceAgent")

COMPLIANCE_SYSTEM_PROMPT = """Sen üst düzey bir Kurumsal Uyum, Hukuk ve Bilgi Güvenliği Denetçisisin (Chief Compliance & Information Security Officer).
Görevin, kullanıcının belirttiği senaryoyu, eylemi, talebi veya sözleşme şartını şirketin resmi politikaları ve mevzuatlarına göre tarafsız bir şekilde denetlemektir.

Aşağıda şirketin bilgi tabanından taranarak bulunan ilgili şirket politikaları, yönetmelikler ve kurallar yer almaktadır:
--------------------
{context}
--------------------

DENETİM VE RAPORLAMA STANDARTLARI:
Yanıtını MUTLAKA aşağıdaki resmi kurumsal denetim formatında üret:

### 📌 1. Denetim Kararı (Verdict)
Aşağıdaki üç kategoriden birini açıkça seç:
- **[UYGUN - COMPLIANT]**: Talep şirket politikalarına tamamen uygundur.
- **[RİSKLİ / ŞARTLI UYGUN - WARNING]**: Belirli güvenlik veya idari şartlar/izinler sağlandığında uygulanabilir.
- **[İHLAL / YASAK - VIOLATION]**: Talep şirket bilgi güvenliği, KVKK veya etik kurallarına aykırıdır, kesinlikle uygulanamaz.

### 📑 2. Dayanak Politika ve Madde Referansları
Yukarıdaki metinde yer alan doküman adı, politika kodu ve ilgili fıkraları belirt (Örn: SEC-POL-04 Madde 4.1).

### 🔍 3. Risk ve Etki Değerlendirmesi
Talebin şirkete getireceği güvenlik, yasal, idari veya cezai riskleri analiz et.

### 💡 4. Zorunlu Onaylar ve Aksiyon Planı
Bu eylemin gerçekleştirilebilmesi için gereken idari onaylar (BT Direktörü, DPO, İK vb.) veya izlenmesi gereken doğru prosedür adımları.

Eğer şirket belgelerinde bu konuyla ilgili hiçbir kural bulunmuyorsa, şirketin bu konuda özel bir yazılı kuralı olmadığını ve ilgili departmandan (BT/Hukuk) görüş alınması gerektiğini belirt.
"""


@register_agent
class ComplianceAuditorAgent(BaseSubAgent):
    """Specialist sub-agent for auditing enterprise actions against compliance policies and producing structured verdicts."""

    name: str = "compliance_agent"
    display_name: str = "Kurumsal Uyum & Politika Denetçisi"
    description: str = (
        "Kullanıcının sorduğu durumları, eylemleri, süreçleri veya talepleri şirket güvenlik politikaları, "
        "KVKK/GDPR, İK yönetmeliği ve kurumsal kurallara göre resmi olarak denetleyip [UYGUN / RİSKLİ / İHLAL] "
        "denetim raporu üretmek için kullanılır."
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
        """Audit user scenario against enterprise policies and output structured compliance report."""
        start_time = time.time()
        question = state.get("question", "").strip()

        logger.info(f"[{self.name}] Auditing compliance scenario: '{question}'")

        # 1. Search relevant compliance policies and regulations
        engine = self._get_engine()
        search_result = engine.search(question)
        context = search_result.get("context", "").strip()
        sources = search_result.get("sources", [])

        if not context:
            duration_ms = int((time.time() - start_time) * 1000)
            answer = (
                "### 📌 1. Denetim Kararı\n**[DEĞERLENDİRİLEMEDİ]**\n\n"
                "### 📑 2. Dayanak Belgeler\nŞirket bilgi tabanında bu konuyla doğrudan eşleşen bir politika veya yönetmelik belgesi bulunamadı.\n\n"
                "### 🔍 3. Tavsiye\nLütfen ilgili talep için Hukuk ve Uyum veya Bilgi Güvenliği birimiyle doğrudan iletişime geçiniz."
            )
            return {
                "final_answer": answer,
                "sources": [],
                "agent_trace": list(state.get("agent_trace", [])) + [{
                    "agent": self.name,
                    "display_name": self.display_name,
                    "action": "compliance_audit",
                    "verdict": "NO_POLICY_FOUND",
                    "sources_count": 0,
                    "duration_ms": duration_ms,
                    "status": "warning",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }],
            }

        # 2. Generate structured audit report
        prompt = COMPLIANCE_SYSTEM_PROMPT.format(context=context)
        try:
            response = self.chat_model.invoke([
                SystemMessage(content=prompt),
                HumanMessage(content=f"Denetlenecek Durum / Talep: {question}"),
            ])
            audit_report = response.content.strip()
        except Exception as e:
            logger.error(f"[{self.name}] Compliance audit LLM error: {e}")
            audit_report = f"Denetim raporu hazırlanırken sistemsel bir hata oluştu: {e}"

        duration_ms = int((time.time() - start_time) * 1000)
        trace_entry = {
            "agent": self.name,
            "display_name": self.display_name,
            "action": "compliance_audit",
            "sources_count": len(sources),
            "duration_ms": duration_ms,
            "status": "success",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        return {
            "final_answer": audit_report,
            "sources": sources,
            "agent_trace": list(state.get("agent_trace", [])) + [trace_entry],
        }
