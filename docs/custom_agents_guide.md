# 🤖 Custom Sub-Agent Development Guide

`OpenLocalEnterpriseRag` features a **modular, extensible, and pluggable Multi-Agent architecture** designed to incorporate specialized domain sub-agents according to enterprise requirements.

The system is centered around an **Intelligent Supervisor Orchestrator**. Whenever a new sub-agent is registered, the Supervisor **automatically discovers it**, registers its specialization domain, and delegates relevant incoming user inquiries accordingly.

---

## 🏗️ Architectural Overview: How It Works

```text
                     ┌────────────────────────────────────────┐
                     │    👑 Supervisor Orchestrator Router   │
                     │  - Analyzes user intent & semantics    │
                     │  - Reads dynamic registered agent meta │
                     └───────────────────┬────────────────────┘
                                         │
        ┌────────────────────────────────┼────────────────────────────────┐
        ▼                                ▼                                ▼
┌──────────────┐                 ┌──────────────┐                 ┌──────────────────────┐
│  doc_agent   │                 │   db_agent   │                 │ ✨ YOUR CUSTOM AGENT  │
│ Document RAG │                 │ SQL Database │                 │  (@register_agent)   │
└──────────────┘                 └──────────────┘                 └──────────────────────┘
```

Every sub-agent inherits from the standardized `BaseSubAgent` class conforming to LangGraph node conventions and implements an `execute(state)` lifecycle method.

---

## 🚀 Creating a New Agent in 3 Simple Steps

Adding a new specialist sub-agent requires only **3 steps**:

### Step 1: Inherit from `BaseSubAgent`
Define your agent's unique identifier (`name`), UI label (`display_name`), and the **specialization description (`description`)** that the Supervisor uses for intent routing.

### Step 2: Decorate with `@register_agent`
Add `@register_agent` to your class definition to automatically register it into the central `agent_registry`.

### Step 3: Implement the `execute(state)` Method
Write your domain business logic, query execution, or calculations, and return a standardized dictionary containing `{"final_answer": "...", "sources": [...], "agent_trace": [...]}`.

---

## 📝 Reference Example: Financial & Currency Calculator (`FinanceCalculatorAgent`)

Below is a complete, production-ready custom agent for financial calculations and currency conversions:

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
    """Specialist sub-agent for financial calculations, currency conversions, and budget metrics."""

    # 1. Unique agent identifier (used for routing)
    name: str = "finance_agent"

    # 2. UI and logging display label
    display_name: str = "Finance & Currency Analyst"

    # 3. CRITICAL: The Supervisor inspects this description to route user questions!
    description: str = (
        "Used for foreign currency exchange rates, currency conversions (USD, EUR, GBP), "
        "VAT/tax calculations, budget ratios, interest calculations, and financial mathematics."
    )

    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Execute domain calculation and grounded response generation."""
        start_time = time.time()
        question = state.get("question", "").strip()

        logger.info(f"[{self.name}] Processing financial request: '{question}'")

        system_prompt = (
            "You are an enterprise financial analyst assistant. "
            "Explain and calculate the user's financial or currency request step-by-step. "
            "Present results clearly with professional formatting."
        )

        try:
            # self.chat_model automatically reuses the shared local LLM backend
            response = self.chat_model.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=question),
            ])
            answer = response.content.strip()
        except Exception as e:
            logger.error(f"[{self.name}] Calculation error: {e}")
            answer = f"An error occurred while processing the financial request: {e}"

        duration_ms = int((time.time() - start_time) * 1000)

        # Transparent execution trace entry
        trace_entry = {
            "agent": self.name,
            "display_name": self.display_name,
            "action": "financial_calculation",
            "duration_ms": duration_ms,
            "status": "success",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Standardized return contract
        return {
            "final_answer": answer,
            "sources": [{
                "source": "FinanceEngine: Calculator",
                "chunk_index": 0,
                "content": "Enterprise financial calculation engine output.",
            }],
            "agent_trace": list(state.get("agent_trace", [])) + [trace_entry],
        }
```

---

## ⚙️ Registration Options

You can register sub-agents in two ways:

### Method A: Automatic Decorator Registration (Recommended)
Add `@register_agent` above your class and save the file in `src/agent/multi_agent/sub_agents/`:
```python
@register_agent
class MyCustomAgent(BaseSubAgent):
    ...
```

### Method B: Programmatic Runtime Registration
To dynamically register or unregister an agent at runtime:
```python
from src.agent.multi_agent.registry import agent_registry

# Register agent instance
agent = MyCustomAgent()
agent_registry.register(agent)

# List registered agents
print(agent_registry.list_agent_names())
# Output: ['doc_agent', 'db_agent', 'compliance_agent', 'my_custom_agent']

# Unregister if needed
agent_registry.unregister("my_custom_agent")
```

---

## 💡 Best Practices

1. **`description` Field is Paramount:**
   * The Supervisor routes queries **strictly based on this semantic description**.
   * Include clear keywords and task types your agent handles.
   * *Avoid:* `"Handles financial tasks."`
   * *Recommended:* `"Used for foreign currency exchange rates, currency conversions (USD, EUR, GBP), VAT/tax calculations, budget ratios, and cost analyses."`

2. **Memory Safety & Lazy Loading:**
   * If your agent requires heavy dependencies or external drivers, load them inside `execute()` or behind a cached `@property` rather than during module import.
   * `self.chat_model` automatically leverages the shared singleton LLM, preventing duplicate VRAM allocations.

3. **Transparent Auditing (`agent_trace`):**
   * Always append an `agent_trace` entry in the dictionary returned by `execute()`. This feeds the Streamlit UI trace panel and the audit database.

4. **Graceful Degradation:**
   * Wrap external API or database calls in `try-except` blocks. If an error occurs, return a helpful error explanation with `status: "error"` in the trace entry without crashing the pipeline.

---

## 🧪 Testing Your Custom Agent

You can test custom sub-agents using standard `unittest` or `pytest`:

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
        result = agent.execute({"question": "Convert 100 USD to local currency"})

        self.assertIn("3450 TRY", result["final_answer"])
        self.assertEqual(len(result["agent_trace"]), 1)
        self.assertEqual(result["agent_trace"][0]["agent"], "finance_agent")

if __name__ == "__main__":
    unittest.main()
```
