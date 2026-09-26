"""
Örnek Özel Alt Ajan (Custom Sub-Agent) Uygulaması.

Bu örnek dosya, OpenLocalRagAgents sistemine bağımsız yeni bir ajanın
nasıl ekleneceğini ve MultiAgentOrchestrator ile nasıl test edileceğini gösterir.

Çalıştırma:
    python examples/custom_agent_example.py
"""
import os
import sys
import time
from datetime import datetime, timezone
from typing import Dict, Any

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from src.agent.multi_agent.base import BaseSubAgent
from src.agent.multi_agent.registry import agent_registry, register_agent
from src.agent.multi_agent.orchestrator_graph import MultiAgentOrchestrator


@register_agent
class CurrencyConverterAgent(BaseSubAgent):
    """Kurumsal döviz kurları ve para birimi çevirileri için uzman alt ajan."""

    name: str = "currency_agent"
    display_name: str = "Döviz & Kur Uzmanı"
    description: str = (
        "Döviz kurları, para birimi çevirileri (USD, EUR, GBP, TRY), kur farkı hesaplamaları "
        "ve kurumsal fatura kurları ile ilgili soruları yanıtlamak için kullanılır."
    )

    # Örnek sabit kur tablosu (Gerçek senaryoda bir API veya DB'den çekilebilir)
    RATES_TO_TRY = {
        "usd": 34.50,
        "eur": 37.80,
        "gbp": 45.20,
    }

    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        start_time = time.time()
        question = state.get("question", "").strip()

        # Basit hesaplama mantığı (demo amaçlı)
        reply = (
            f"💱 **Döviz Çeviri Raporu**\n\n"
            f"Güncel Kurumsal Gösterge Kurları:\n"
            f"- **1 USD:** {self.RATES_TO_TRY['usd']:.2f} TRY\n"
            f"- **1 EUR:** {self.RATES_TO_TRY['eur']:.2f} TRY\n"
            f"- **1 GBP:** {self.RATES_TO_TRY['gbp']:.2f} TRY\n\n"
            f"Soru: *\"{question}\"*\n"
            f"Talebiniz kurumsal muhasebe kur tablosuna göre hesaplanmıştır."
        )

        duration_ms = int((time.time() - start_time) * 1000)
        trace_entry = {
            "agent": self.name,
            "display_name": self.display_name,
            "action": "currency_conversion",
            "duration_ms": duration_ms,
            "status": "success",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        return {
            "final_answer": reply,
            "sources": [{
                "source": "Corporate: Central Bank Exchange Rates",
                "chunk_index": 0,
                "content": "Günlük kurumsal gösterge döviz kurları tablosu.",
            }],
            "agent_trace": list(state.get("agent_trace", [])) + [trace_entry],
        }


def main():
    print("=" * 60)
    print("🤖 Multi-Agent Dinamik Ajan Kayıt Testi")
    print("=" * 60)

    # 1. Sisteme kayıtlı ajanları listele
    print("\n📋 Kayıtlı Ajanlar:")
    for name in agent_registry.list_agent_names():
        agent = agent_registry.get(name)
        print(f"  - [{name}] {agent.display_name}")

    # 2. Supervisor İstemini İncele (Yeni ajan otomatik dahil oldu mu?)
    print("\n👑 Supervisor Yönlendirme Özeti (Dinamik Prompt):")
    print(agent_registry.get_supervisor_prompt())

    # 3. Ajanı doğrudan test et
    print("\n⚡ CurrencyConverterAgent Doğrudan Çalıştırılıyor:")
    currency_agent = agent_registry.get("currency_agent")
    test_state = {"question": "1000 dolar kaç TL yapıyor?", "agent_trace": []}
    result = currency_agent.execute(test_state)

    print("\n--- Ajan Yanıtı ---")
    print(result["final_answer"])
    print("\n--- Kaynaklar ---")
    print(result["sources"])
    print("\n--- Denetim İzi (Trace) ---")
    print(result["agent_trace"])
    print("\n✅ Özel alt ajan başarıyla çalıştı ve entegre oldu!")


if __name__ == "__main__":
    main()
