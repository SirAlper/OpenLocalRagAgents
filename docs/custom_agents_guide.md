# 🤖 Özel Alt Ajan Geliştirme Yönergesi (Custom Agents Guide)

`OpenLocalRagAgents`, kurumsal ihtiyaçlarınıza göre yeni yapay zeka uzmanları (Sub-Agents) ekleyebileceğiniz **modüler, genişletilebilir ve tak-çalıştır (pluggable)** bir Multi-Agent mimarisine sahiptir.

Sistemde bir **Ana Ajan (Supervisor Orchestrator)** yer alır. Yazdığınız her yeni alt ajan sisteme kaydolduğunda, Ana Ajan onu **otomatik olarak tanır**, yeteneklerini öğrenir ve ilgili kullanıcı sorularını o ajana yönlendirir.

---

## 🏗️ Mimari Bakış: Nasıl Çalışır?

```text
                     ┌────────────────────────────────────────┐
                     │    👑 Ana Ajan (Supervisor Router)     │
                     │  - Kullanıcı niyetini analiz eder      │
                     │  - Kayıtlı ajanların tanımını okur     │
                     └───────────────────┬────────────────────┘
                                         │
        ┌────────────────────────────────┼────────────────────────────────┐
        ▼                                ▼                                ▼
┌──────────────┐                 ┌──────────────┐                 ┌──────────────────────┐
│  doc_agent   │                 │   db_agent   │                 │ ✨ SİZİN ÖZEL AJANINIZ │
│ Belge Ajanı  │                 │   SQL Ajanı  │                 │  (@register_agent)   │
└──────────────┘                 └──────────────┘                 └──────────────────────┘
```

Her alt ajan, standart **LangGraph** düğüm (node) yapısına uyan `BaseSubAgent` sınıfından miras alır ve `execute(state)` metodunu uygular.

---

## 🚀 5 Dakikada Yeni Bir Ajan Oluşturma

Yeni bir uzman ajan eklemek için izlemeniz gereken **3 basit adım**:

### Adım 1: `BaseSubAgent` Sınıfından Miras Alın
Ajanınızın benzersiz adını (`name`), kullanıcı arayüzünde görünecek adını (`display_name`) ve Ana Ajan'ın yönlendirme yapabilmesi için **uzmanlık alanını (`description`)** tanımlayın.

### Adım 2: `@register_agent` Dekoratörünü Ekleyin
Sınıfınızın başına `@register_agent` ekleyerek tek satırda merkezi kayıt defterine (`agent_registry`) bağlayın.

### Adım 3: `execute(state)` Metodunu Yazın
Görevi yerine getiren iş mantığını kodlayın ve kullanıcıya dönecek cevabı `{"final_answer": "...", "sources": [...]}` sözlüğü olarak döndürün.

---

## 📝 Örnek Senaryo: Döviz ve Finans Hesaplama Ajanı (`FinanceCalculatorAgent`)

Aşağıda, şirket içi finansal hesaplamalar ve döviz çevirileri yapan eksiksiz bir özel ajan örneği yer almaktadır:

```python
import time
from datetime import datetime, timezone
from typing import Dict, Any

from langchain_core.messages import SystemMessage, HumanMessage
from src.agent.multi_agent.base import BaseSubAgent
from src.agent.multi_agent.registry import register_agent
from src.core.logger import get_logger

logger = get_logger("MultiAgent.FinanceAgent")


@register_agent
class FinanceCalculatorAgent(BaseSubAgent):
    """Finansal hesaplamalar, kur çevirileri ve bütçe analizleri yapan uzman ajan."""

    # 1. Ajanın benzersiz kimliği (Supervisor routing için kullanılır)
    name: str = "finance_agent"

    # 2. UI ve loglarda görünen etiket
    display_name: str = "Finans & Kur Analisti"

    # 3. CRITICAL: Supervisor bu tanımı okuyarak soruyu bu ajana yönlendirir!
    description: str = (
        "Döviz kurları, para birimi çevirileri, KDV/vergi hesaplamaları, bütçe oranları, "
        "kredi/faiz maliyetleri ve finansal matematik hesaplamaları için kullanılır."
    )

    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Ajanın çalışma mantığı."""
        start_time = time.time()
        question = state.get("question", "").strip()

        logger.info(f"[{self.name}] Finansal talep işleniyor: '{question}'")

        # Özel Ajan Promptu
        system_prompt = (
            "Sen uzman bir kurumsal finans analistisin. "
            "Kullanıcının finansal hesaplama veya kur çevirisi talebini adım adım ve "
            "net bir şekilde hesaplayarak açıkla. Sonuçları anlaşılır bir formatta sun."
        )

        try:
            # self.chat_model otomatik olarak paylaşımlı LLM motorunu kullanır
            response = self.chat_model.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=question),
            ])
            answer = response.content.strip()
        except Exception as e:
            logger.error(f"[{self.name}] Hata oluştu: {e}")
            answer = f"Finansal hesaplama yapılırken bir hata oluştu: {e}"

        duration_ms = int((time.time() - start_time) * 1000)

        # Şeffaf denetim izi (Trace) kaydı
        trace_entry = {
            "agent": self.name,
            "display_name": self.display_name,
            "action": "financial_calculation",
            "duration_ms": duration_ms,
            "status": "success",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Standart dönüş formatı
        return {
            "final_answer": answer,
            "sources": [{
                "source": "FinanceEngine: Calculator",
                "chunk_index": 0,
                "content": "Kurumsal finans hesaplama motoru çıktısı.",
            }],
            "agent_trace": list(state.get("agent_trace", [])) + [trace_entry],
        }
```

---

## ⚙️ Ajanın Sisteme Dahil Edilmesi (Registration Options)

Yeni ajanınızı sisteme tanıtmak için iki yöntemden birini kullanabilirsiniz:

### Yöntem A: Dekoratör ile Otomatik Kayıt (Tavsiye Edilen)
Ajan sınıfınızın başına `@register_agent` ekleyin ve dosyanızı `src/agent/multi_agent/sub_agents/` klasörü altına kaydedin:
```python
@register_agent
class MyCustomAgent(BaseSubAgent):
    ...
```

### Yöntem B: Dinamik Programatik Kayıt
Çalışma anında (runtime) bir ajanı sisteme eklemek veya çıkarmak isterseniz:
```python
from src.agent.multi_agent.registry import agent_registry

# Ajanı kaydet
agent = MyCustomAgent()
agent_registry.register(agent)

# Kayıtlı ajanları listele
print(agent_registry.list_agent_names())
# Çıktı: ['doc_agent', 'db_agent', 'compliance_agent', 'my_custom_agent']

# Ajanı sistemden çıkar
agent_registry.unregister("my_custom_agent")
```

---

## 💡 En İyi Uygulamalar (Best Practices)

1. **`description` Alanı Çok Önemlidir:**
   * Supervisor, kullanıcının sorusunu hangi ajana yönlendireceğine **tamamen bu açıklamaya bakarak** karar verir.
   * Açıklamanızda ajanınızın ilgilendiği anahtar kelimeleri ve görev türlerini net bir şekilde belirtin.
   * *Kötü Örnek:* `"Finans işlerini yapar."`
   * *İyi Örnek:* `"Döviz kurları, para birimi çevirileri, KDV/vergi hesaplamaları, bütçe oranları ve maliyet analizleri için kullanılır."`

2. **Bellek Güvenliği (Lazy Loading):**
   * Ajanınız ağır bir model veya kütüphane gerektiriyorsa, bunu dosya başında veya `__init__` anında değil, `execute()` metodunda veya `@property` arkasında yükleyin.
   * `self.chat_model` özelliği varsayılan olarak paylaşımlı tekil LLM modelini kullanır, böylece VRAM tüketimi artmaz.

3. **Şeffaf İzleme (`agent_trace`):**
   * `execute()` fonksiyonunuzun döndürdüğü sözlüğe mutlaka `agent_trace` alanını ekleyin. Bu sayede kullanıcı arayüzü ve API yanıtı hangi ajanın ne kadar sürede çalıştığını şeffafça gösterir.

4. **Hata Yakalama (Graceful Degradation):**
   * Ağ veya hesaplama hatalarını `try-except` bloğunda yakalayın ve kullanıcıya anlaşılır bir hata mesajı ile `status: "error"` trace kaydı üretin. Sistemin kilitlenmesine izin vermeyin.

---

## 🧪 Özel Ajanınızı Test Etme

Ajanınızın beklendiği gibi çalıştığını doğrulamak için `unittest` veya `pytest` yazabilirsiniz:

```python
import unittest
from unittest.mock import MagicMock
from src.agent.multi_agent.registry import AgentRegistry
from my_custom_agent import FinanceCalculatorAgent

class TestFinanceAgent(unittest.TestCase):
    def test_finance_agent_execution(self):
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content="100 USD = 3450 TRY")

        agent = FinanceCalculatorAgent(chat_model=mock_llm)
        result = agent.execute({"question": "100 dolar kaç TL yapar?"})

        self.assertIn("3450 TRY", result["final_answer"])
        self.assertEqual(len(result["agent_trace"]), 1)
        self.assertEqual(result["agent_trace"][0]["agent"], "finance_agent")

if __name__ == "__main__":
    unittest.main()
```
