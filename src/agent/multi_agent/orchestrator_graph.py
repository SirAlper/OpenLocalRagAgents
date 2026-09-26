import os
from typing import Optional, Dict, Any, Generator
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from src.agent.llm import create_chat_model
from src.agent.multi_agent.state import MultiAgentState
from src.agent.multi_agent.registry import AgentRegistry, agent_registry
from src.agent.multi_agent.supervisor import SupervisorAgent
import src.agent.multi_agent.sub_agents  # Ensures built-in sub-agents are loaded & registered
from src.core.logger import get_logger

logger = get_logger("MultiAgent.Orchestrator")


class MultiAgentOrchestrator:
    """Enterprise Multi-Agent Orchestrator compiling and executing the LangGraph Supervisor-Worker workflow."""

    def __init__(
        self,
        chat_model=None,
        registry: Optional[AgentRegistry] = None,
        checkpointer=None,
    ):
        self.chat_model = chat_model or create_chat_model()
        self.registry = registry or agent_registry
        self.supervisor = SupervisorAgent(chat_model=self.chat_model, registry=self.registry)
        self.checkpointer = checkpointer or self._init_default_checkpointer()
        self._sqlite_conn = None
        self.app = self._build_graph()

    def _init_default_checkpointer(self):
        """Initialize SQLite checkpointer for multi-agent multi-turn conversation persistence."""
        try:
            import sqlite3
            from langgraph.checkpoint.sqlite import SqliteSaver
            from src.core.config import DOCS_PATH

            os.makedirs(DOCS_PATH, exist_ok=True)
            db_path = os.path.join(DOCS_PATH, "multi_agent_conversations.db")
            conn = sqlite3.connect(db_path, check_same_thread=False)
            self._sqlite_conn = conn
            saver = SqliteSaver(conn)
            saver.setup()
            logger.info(f"[Orchestrator] Multi-agent checkpointer initialized at: {db_path}")
            return saver
        except Exception as e:
            logger.warning(f"[Orchestrator] Could not initialize SqliteSaver, using MemorySaver: {e}")
            return MemorySaver()

    def _build_graph(self):
        """Compile the dynamic LangGraph StateGraph with Supervisor routing and registered worker nodes."""
        workflow = StateGraph(MultiAgentState)

        # 1. Add Supervisor Router Node
        workflow.add_node("supervisor", self.supervisor.route)
        workflow.set_entry_point("supervisor")

        # 2. Add each registered sub-agent as a worker node
        registered_agents = self.registry.list_agents()
        agent_names = [agent.name for agent in registered_agents]

        for agent in registered_agents:
            # Inject shared chat_model to sub-agent if not already initialized
            if agent._chat_model is None:
                agent.chat_model = self.chat_model

            workflow.add_node(agent.name, agent.execute)
            # Once a specialist agent finishes execution, terminate the flow
            workflow.add_edge(agent.name, END)

        # 3. Define conditional routing edge from Supervisor
        def route_decision(state: MultiAgentState) -> str:
            target = state.get("next_agent", "finish")
            if target in agent_names:
                return target
            return "finish"

        # Edge routing mapping
        edge_mapping = {name: name for name in agent_names}
        edge_mapping["finish"] = END

        workflow.add_conditional_edges("supervisor", route_decision, edge_mapping)

        # 4. Compile with checkpointer
        app = workflow.compile(checkpointer=self.checkpointer)
        logger.info(f"[Orchestrator] Compiled MultiAgent workflow with {len(agent_names)} sub-agents: {agent_names}")
        return app

    def query(
        self,
        question: str,
        thread_id: Optional[str] = None,
        forced_agent: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute the multi-agent workflow and return verified answer, sources, and agent trace."""
        config = {"configurable": {"thread_id": thread_id}} if thread_id else {}

        initial_state: MultiAgentState = {
            "question": question,
            "agent_trace": [],
            "sources": [],
            "final_answer": "",
        }
        if forced_agent:
            initial_state["forced_agent"] = forced_agent

        result = self.app.invoke(initial_state, config=config)

        # Update chat history in state
        chat_history = list(result.get("chat_history", []))
        raw_agent = result.get("next_agent", "supervisor")
        active_agent = "supervisor" if raw_agent == "finish" else raw_agent

        chat_history.append({
            "question": question,
            "answer": result.get("final_answer", ""),
            "agent": active_agent,
        })

        return {
            "answer": result.get("final_answer", ""),
            "sources": result.get("sources", []),
            "agent_trace": result.get("agent_trace", []),
            "active_agent": active_agent,
            "chat_history": chat_history,
        }

    def stream_events(
        self,
        question: str,
        thread_id: Optional[str] = None,
        forced_agent: Optional[str] = None,
    ) -> Generator[Dict[str, Any], None, None]:
        """Stream real-time multi-agent execution events with intermediate status and final response."""
        yield {
            "type": "status",
            "message": "👑 Supervisor: Soru analiz ediliyor ve en uygun uzman ajan belirleniyor...",
            "node": "supervisor",
        }

        state: MultiAgentState = {
            "question": question,
            "agent_trace": [],
            "sources": [],
            "final_answer": "",
        }
        if forced_agent:
            state["forced_agent"] = forced_agent

        # Step 1: Run Supervisor
        supervisor_out = self.supervisor.route(state)
        state.update(supervisor_out)
        target_agent = state.get("next_agent", "finish")

        # If Supervisor answered directly (e.g. greeting)
        if target_agent == "finish":
            yield {
                "type": "agent_selected",
                "agent": "supervisor",
                "display_name": "Supervisor Orchestrator",
                "reason": "Genel yanıt / selamlama doğrudan yanıtlandı.",
            }
            yield {
                "type": "done",
                "answer": state.get("final_answer", ""),
                "sources": [],
                "agent_trace": state.get("agent_trace", []),
                "active_agent": "supervisor",
            }
            return

        # Step 2: Specialist agent delegated
        sub_agent = self.registry.get(target_agent)
        display_name = sub_agent.display_name if sub_agent else target_agent

        yield {
            "type": "agent_selected",
            "agent": target_agent,
            "display_name": display_name,
            "reason": f"Görev '{display_name}' uzmanına devredildi.",
        }

        yield {
            "type": "status",
            "message": f"🤖 {display_name}: Uzmanlık alanı kapsamında çalışıyor...",
            "node": target_agent,
        }

        # Step 3: Run Specialist Agent
        if sub_agent:
            agent_out = sub_agent.execute(state)
            state.update(agent_out)

        yield {
            "type": "sources",
            "sources": state.get("sources", []),
        }

        yield {
            "type": "done",
            "answer": state.get("final_answer", ""),
            "sources": state.get("sources", []),
            "agent_trace": state.get("agent_trace", []),
            "active_agent": target_agent,
        }

    def cleanup(self):
        """Gracefully release checkpointer SQLite database connection."""
        if self._sqlite_conn:
            try:
                self._sqlite_conn.close()
                logger.info("[Orchestrator] Multi-agent checkpointer connection closed.")
            except Exception as e:
                logger.warning(f"[Orchestrator] Error closing checkpointer connection: {e}")
            finally:
                self._sqlite_conn = None
