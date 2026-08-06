"""Graph assembly + runtime wiring (Member A graph + Member B persistence)."""
import os
from langchain_groq import ChatGroq
from tavily import TavilyClient
from langgraph.graph import StateGraph, END

from . import runtime
from .state import TravelState
from .guardrails import PromptInjectionGuardrail
from .agents.planner import agent1_planner_node, TOOLS_SCHEMA
from .agents.budget import agent2_budget_node, budget_router
from .agents.safety import agent3_audit_node
from .hitl import human_review_node, human_review_router

MODEL = "llama-3.3-70b-versatile"


def build_app(checkpointer=None):
    """Initialize runtime singletons and compile the StateGraph."""
    llm = ChatGroq(model=MODEL, temperature=0)
    runtime.init(
        llm,
        llm.bind_tools(TOOLS_SCHEMA),
        TavilyClient(api_key=os.environ["TAVILY_API_KEY"]),
        PromptInjectionGuardrail(llm),
    )
    wf = StateGraph(TravelState)
    wf.add_node("agent1_planner", agent1_planner_node)
    wf.add_node("agent2_budget", agent2_budget_node)
    wf.add_node("agent3_audit", agent3_audit_node)
    wf.add_node("human_review", human_review_node)
    wf.set_entry_point("agent1_planner")
    wf.add_edge("agent1_planner", "agent2_budget")
    wf.add_conditional_edges("agent2_budget", budget_router,
                             {"replan": "agent1_planner", "proceed": "agent3_audit"})
    wf.add_edge("agent3_audit", "human_review")
    wf.add_conditional_edges("human_review", human_review_router,
                             {"end": END, "replan": "agent1_planner"})
    return wf.compile(checkpointer=checkpointer)


# ============================================================
# Helper — a fresh initial state for the demos
# ============================================================
def make_initial_state(destination="Kyoto", dates="2026-11-10 to 2026-11-15",
                       budget=2000.0, prefs=None, max_iters=3) -> TravelState:
    return {
        "user_request": f"5-day trip to {destination}", "destination": destination,
        "travel_dates": dates, "budget_limit": budget,
        "traveler_preferences": prefs or ["food", "temples"],
        "react_trace": [], "search_results": [], "draft_itinerary": [],
        "budget_analysis": None, "final_summary": None, "audit_notes": [],
        "guardrail_logs": [], "pii_masked": False,
        "iteration_count": 0, "max_iterations": max_iters, "replan_reason": None,
        "human_approved": None, "human_feedback": None,
        "execution_logs": [], "status": "in_progress",
    }
