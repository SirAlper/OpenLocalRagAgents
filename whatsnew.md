# 🚀 Yenilikler ve Değişiklikler (What's New)

Bu belge, **OpenLocalEnterpriseRag** projesine eklenen en son özellikleri, mimari geliştirmeleri, yeni modülleri, API uç noktalarını ve kullanıcı arayüzü bileşenlerini detaylandırmaktadır.

---

## 🌟 Sürüm 2.1.0 — Modüler Çoklu Ajan (Multi-Agent) Ekosistemi

Proje, tekli RAG ajanından **dinamik, genişletilebilir ve tak-çalıştır (pluggable) bir Multi-Agent (Çoklu Ajan) mimarisine** yükseltilmiştir. Artık sistem; kullanıcı niyetini analiz eden bir **Supervisor (Ana Orkestratör)** ve uzmanlık alanlarına göre ayrışmış **Özel Alt Ajanlar (Sub-Agents)** ile çalışmaktadır.

---

### 1. 🏗️ Yeni Modüler Çoklu Ajan Çerçevesi (`src/agent/multi_agent/`)

Sisteme sıfırdan kurumsal düzeyde bir LangGraph tabanlı çoklu ajan çekirdeği entegre edildi:

* **[`BaseSubAgent`](file:///c:/Users/hanal/PycharmProjects/OpenLocalEnterpriseRag/src/agent/multi_agent/base.py)**:
  * Tüm uzman alt ajanların miras aldığı standart temel soyut sınıf.
  * `name`, `display_name`, `description`, `version` özniteliklerini ve standart `execute(state)` arayüzünü tanımlar.
  * Ortak paylaşımlı LLM motoru (`chat_model`) erişimini otomatik sağlar.

* **[`AgentRegistry`](file:///c:/Users/hanal/PycharmProjects/OpenLocalEnterpriseRag/src/agent/multi_agent/registry.py)** & **`@register_agent`**:
  * Merkezi dinamik ajan tescil defteri (Registry Pattern).
  * `@register_agent` dekoratörü sayesinde geliştirilen herhangi bir yeni uzman ajan, tek bir satırla sisteme otomatik olarak dahil edilir.
  * Ajan metaverilerini okuyarak Supervisor ve API katmanına anında sunar.

* **[`MultiAgentState`](file:///c:/Users/hanal/PycharmProjects/OpenLocalEnterpriseRag/src/agent/multi_agent/state.py)**:
  * Çoklu ajan iş akışında veri alışverişini yöneten LangGraph durum şeması.
  * Soru, thread kimliği, aktif ajan (`active_agent`), adım adım yürütme izi (`agent_trace`), yanıtlar ve kaynak doğrulamalarını taşır.

* **[`SupervisorAgent`](file:///c:/Users/hanal/PycharmProjects/OpenLocalEnterpriseRag/src/agent/multi_agent/supervisor.py)**:
  * Akıllı yönlendirici ve orkestratör (Routing & Intent Orchestrator).
  * Kayıt defterindeki tüm uzman ajanların uzmanlık açıklamalarını dinamik olarak okur.
  * Kullanıcı sorusunu analiz ederek en uygun uzman ajana veya doğrudan genel yanıta (selamlaşma, genel sohbet) yönlendirir.
  * Dinamik karar mekanizması, regex/kural tabanlı hızlı kestirme ve hata durumlarında koruyucu fallback desteği içerir.

* **[`MultiAgentOrchestrator`](file:///c:/Users/hanal/PycharmProjects/OpenLocalEnterpriseRag/src/agent/multi_agent/orchestrator_graph.py)**:
  * LangGraph `StateGraph` üzerinde Supervisor ile alt ajan düğümlerini (Nodes & Conditional Edges) birbirine bağlayan ana orkestrasyon motoru.
  * `MemorySaver` ile oturum bazlı (`thread_id`) durum kontrol noktaları (checkpointing).
  * Senkron çalıştırma (`query()`) ve gerçek zamanlı aşama akışı (`stream_events()`) işlevleri.
  * Kullanıcı isteğine göre spesifik bir ajanı zorunlu çalıştırma (`forced_agent`) yeteneği.

---

### 2. 👥 Yerleşik Uzman Alt Ajanlar (`src/agent/multi_agent/sub_agents/`)

Farklı kurumsal görevler için özelleşmiş üç temel uzman ajan devreye alındı:

| Ajan Kimliği | Ekrandaki Adı | Uzmanlık Alanı |
| :--- | :--- | :--- |
| **`doc_agent`** | 📄 Belge RAG Uzmanı | Şirket içi PDF, DOCX, TXT ve Markdown belgelerinde vektörel anlamsal arama (ChromaDB / BM25) yapar ve kaynak referanslı yanıt üretir. |
| **`db_agent`** | 🗄️ SQL Veritabanı Uzmanı | Bağlı kurumsal SQL veritabanlarında (PostgreSQL, MySQL, SQLite vb.) şemaları inceler, güvenli salt-okunur (read-only) SQL sorguları oluşturur ve verileri analiz eder. |
| **`compliance_agent`** | 🛡️ Mevzuat & Uyum Denetçisi | Şirket içi politika belgeleri, regülasyonlar, yönetmelikler ve KVKK/GDPR uyum kuralları çerçevesinde risk ve uyumluluk kontrolleri gerçekleştirir. |

---

### 3. 🌐 REST API ve Canlı Akış Geliştirmeleri (`src/api/`)

FastAPI servisleri çoklu ajan yapısını tam olarak destekleyecek şekilde güncellendi:

* **Yeni Uç Nokta — `GET /api/v1/agents`**:
  * Sistemde aktif olarak kayıtlı tüm alt ajanları, görünen adlarını ve yetenek açıklamalarını istemcilere (UI/entegrasyonlar) JSON olarak sunar.
* **Gelişmiş Sorgu — `POST /api/v1/query`**:
  * İstek gövdesine (`QueryRequest`) opsiyonel `agent` parametresi eklendi (`auto` veya spesifik ajan adı).
  * Yanıt modeline hangi ajanın yanıtladığını gösteren `active_agent` ve adım adım yürütülen işlemleri gösteren `agent_trace` alanları eklendi.
* **Canlı Akış — `POST /api/v1/query/stream`**:
  * NDJSON (Newline Delimited JSON) canlı akışına Multi-Agent olayları entegre edildi.
  * Hangi ajanın devreye girdiği ve akışın hangi adımlardan geçtiği istemciye anlık iletilir.
* **Servis Yaşam Döngüsü (`src/api/state.py`)**:
  * `get_multi_agent_orchestrator()` singleton fonksiyonu ve uygulama sonlandığında orkestratör kaynaklarının güvenle serbest bırakılması (`cleanup_services`).

---

### 4. 🎨 Modern Streamlit Kullanıcı Arayüzü (`ui/app.py`)

Kullanıcı deneyimi çoklu ajan ekosistemine uygun olarak zenginleştirildi:

* **🤖 Uzman Ajan Ekibi Seçicisi**:
  * Sol kenar çubuğuna (Sidebar) backend'deki kayıt defterinden dinamik olarak beslenen ajan seçici kutusu eklendi.
  * Kullanıcı isterse "Otomatik (Supervisor Orchestrator)" modunu seçerek yönlendirmeyi sisteme bırakabilir, isterse belirli bir uzman ajanı (örn. `db_agent`) doğrudan görevlendirebilir.
* **🏷️ Renkli Ajan Rozetleri (Badges)**:
  * Her asistan mesajının üzerinde yanıtı hangi ajanın hazırladığını belirten renk kodlu rozetler gösterilir:
    * 👑 **Supervisor** (Doğrudan Yanıt)
    * 📄 **doc_agent** (Belge RAG Uzmanı)
    * 🗄️ **db_agent** (SQL Veritabanı Uzmanı)
    * 🛡️ **compliance_agent** (Mevzuat & Uyum Denetçisi)
* **🔍 İnteraktif Ajan Yürütme İzi (Execution Trace Expander)**:
  * Asistan yanıtlarının altında yer alan açılır-kapanır panel ile ajanın arkada attığı adımlar, çalıştırılan SQL sorguları, aranan sorgu terimleri ve harcanan süre milisaniye (`ms`) cinsinden şeffafça izlenebilir.

---

### 5. 📚 Geliştirici Kılavuzu ve Örnek Kodlar

Dışarıdan ve şirket içinden geliştiricilerin 5 dakika içinde sisteme yeni ajanlar ekleyebilmesi için kapsamlı dokümantasyon ve örnekler eklendi:

* **[`docs/custom_agents_guide.md`](file:///c:/Users/hanal/PycharmProjects/OpenLocalEnterpriseRag/docs/custom_agents_guide.md)**:
  * `BaseSubAgent` miras alma, `@register_agent` kullanma ve `execute(state)` yazma adımlarını içeren ayrıntılı kılavuz.
* **[`examples/custom_agent_example.py`](file:///c:/Users/hanal/PycharmProjects/OpenLocalEnterpriseRag/examples/custom_agent_example.py)**:
  * Gerçek hayat senaryosu olarak finansal hesaplamalar, döviz çevirileri ve vergi maliyeti hesaplayan `FinanceCalculatorAgent` örnek uygulaması.

---

### 6. 🧪 Kapsamlı Test Paketi

Çoklu ajan altyapısının kararlılığı ve regresyon güvenliği için yeni test suitleri eklendi:

* **[`tests/test_multi_agent.py`](file:///c:/Users/hanal/PycharmProjects/OpenLocalEnterpriseRag/tests/test_multi_agent.py)**:
  * `BaseSubAgent` doğrulama testleri.
  * `AgentRegistry` ajan kayıt, arama ve geçersiz ajan reddetme testleri.
  * `SupervisorAgent` niyet analizi, yönlendirme ve doğrudan selamlama testleri.
  * `MultiAgentOrchestrator` LangGraph akış ve zorunlu ajan (`forced_agent`) yönlendirme testleri.
* **[`tests/test_api_multi_agent.py`](file:///c:/Users/hanal/PycharmProjects/OpenLocalEnterpriseRag/tests/test_api_multi_agent.py)**:
  * `/api/v1/agents` uç noktası kimlik doğrulama ve liste doğrulama testleri.
  * `/api/v1/query` uç noktası çoklu ajan yönlendirme ve trace entegrasyon testleri.

---

## 📋 Özet Dosya Değişiklikleri Tablosu

| Dizin / Dosya | Durum | Açıklama |
| :--- | :--- | :--- |
| `src/agent/multi_agent/base.py` | ✨ Yeni | Alt ajanlar için temel soyut sınıf (`BaseSubAgent`) |
| `src/agent/multi_agent/registry.py` | ✨ Yeni | Merkezi ajan kayıt defteri ve `@register_agent` dekoratörü |
| `src/agent/multi_agent/state.py` | ✨ Yeni | Multi-Agent LangGraph durum veri modelleri |
| `src/agent/multi_agent/supervisor.py` | ✨ Yeni | Akıllı yönlendirici ve orkestratör ajan |
| `src/agent/multi_agent/orchestrator_graph.py` | ✨ Yeni | LangGraph derlenmiş çoklu ajan iş akış grafiği |
| `src/agent/multi_agent/sub_agents/doc_agent.py` | ✨ Yeni | Belge tabanlı vektör RAG uzmanı |
| `src/agent/multi_agent/sub_agents/db_agent.py` | ✨ Yeni | SQL veritabanı analizi ve sorgulama uzmanı |
| `src/agent/multi_agent/sub_agents/compliance_agent.py` | ✨ Yeni | Şirket içi uyum ve mevzuat denetçisi |
| `src/api/routes/query.py` | 📝 Güncellendi | `/api/v1/agents` eklendi, `/api/v1/query` çoklu ajanla genişletildi |
| `src/api/schemas.py` | 📝 Güncellendi | `AgentInfo`, `AgentsListResponse` ve `QueryRequest.agent` eklendi |
| `src/api/state.py` | 📝 Güncellendi | `get_multi_agent_orchestrator()` ve kapatma temizliği eklendi |
| `src/api/main.py` | 📝 Güncellendi | Orkestratör import ve export entegrasyonu |
| `ui/app.py` | 📝 Güncellendi | Ajan seçici dropdown, renkli rozetler ve yürütme izi paneli eklendi |
| `docs/custom_agents_guide.md` | ✨ Yeni | Özel alt ajan geliştirme rehberi |
| `examples/custom_agent_example.py` | ✨ Yeni | Finans ve kur hesaplama ajanı örnek kodu |
| `tests/test_multi_agent.py` | ✨ Yeni | Çoklu ajan çekirdek birim testleri |
| `tests/test_api_multi_agent.py` | ✨ Yeni | API çoklu ajan entegrasyon testleri |
| `whatsnew.md` | ✨ Yeni | Bu yenilikler ve değişiklikler dokümanı |
