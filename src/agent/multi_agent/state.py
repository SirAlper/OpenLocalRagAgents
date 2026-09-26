from typing import TypedDict, List, Dict, Any, Optional
from pydantic import BaseModel, Field


class AgentResponse(BaseModel):
    """Standardized response model produced by a sub-agent execution."""
    content: str = Field(description="Generated text response or explanation")
    sources: List[Dict[str, Any]] = Field(default_factory=list, description="Referenced documents or data sources")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Execution telemetry (execution time, tools called, model info)")


class MultiAgentState(TypedDict, total=False):
    """Central state container shared across the LangGraph Multi-Agent workflow."""
    question: str                              # Original user query
    chat_history: List[Dict[str, str]]         # Prior conversation history
    next_agent: str                            # Routing decision made by the Supervisor
    agent_trace: List[Dict[str, Any]]          # Chronological execution trace (which agent ran, runtime, result preview)
    final_answer: str                          # Consolidated final answer delivered to user
    sources: List[Dict[str, Any]]              # Consolidated list of sources from all contributing agents
    intermediate_steps: List[Dict[str, Any]]   # Intermediate scratchpad / artifacts produced by agents
