"""Human-in-the-loop review node + router (Member B, D5)."""
from typing import Optional, Callable, Literal
from langgraph.types import interrupt
from .observability import traced
from .state import TravelState

# ============================================================
# SECTION 8 — HUMAN-IN-THE-LOOP REVIEW   [Member B]  (D5: HITL interrupt)
# ============================================================
# Sits right after Agent 3. Guards on status=="awaiting_human", pauses the
# graph with interrupt(), and resumes on the human's decision:
#   approve -> status="completed" -> END
#   reject  -> status="in_progress", replan_reason=feedback -> loop to Agent 1

@traced("node")
def human_review_node(state: TravelState, interrupt_fn: Optional[Callable] = None) -> dict:
    if state.get("status") != "awaiting_human":
        return {"execution_logs": [f"Human review skipped: status '{state.get('status')}' != 'awaiting_human'."]}
    if interrupt_fn is None:
        interrupt_fn = interrupt   # real LangGraph interrupt

    decision = interrupt_fn({
        "final_summary": state["final_summary"],
        "audit_notes": state["audit_notes"],
        "budget_analysis": state["budget_analysis"],
        "guardrail_logs": state["guardrail_logs"],
        "question": "Approve this itinerary? Respond {'approved': bool, 'feedback': str}.",
    })
    approved = bool(decision.get("approved", False))
    feedback = decision.get("feedback")
    if approved:
        return {"human_approved": True, "human_feedback": feedback, "status": "completed",
                "execution_logs": ["Human approved. status -> completed."]}
    return {"human_approved": False, "human_feedback": feedback, "status": "in_progress",
            "replan_reason": feedback or "Human rejected; no feedback given.",
            "iteration_count": state["iteration_count"] + 1,
            "execution_logs": [f"Human rejected. replan_reason set: {feedback!r}"]}

def human_review_router(state: TravelState) -> Literal["end", "replan"]:
    return "end" if state["status"] == "completed" else "replan"
