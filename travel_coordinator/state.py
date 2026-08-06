"""Shared state schema — the inter-agent message contract (Member A)."""
from typing import TypedDict, List, Dict, Optional, Literal, Annotated
import operator

# ============================================================
# SECTION 1 — SHARED STATE SCHEMA   [Member A]
# ============================================================
# The single source of truth. Every node reads/writes this one object;
# there is no direct agent-to-agent messaging (see coordination strategy).
# Fields annotated with operator.add are APPEND channels (reducers);
# all others OVERWRITE on write.

class SearchResult(TypedDict):
    source: str
    query: str
    raw_content: str
    url: Optional[str]

class ReActStep(TypedDict):
    thought: str
    action: str
    action_input: str
    observation: str

class ItineraryItem(TypedDict):
    day: int
    activity: str
    location: str
    estimated_cost: float
    category: Literal["flight", "accommodation", "transit", "activity", "food", "entry_fee"]

class BudgetBreakdown(TypedDict):
    total_estimated_cost: float
    budget_limit: float
    over_budget: bool
    over_budget_amount: float
    cost_by_category: Dict[str, float]
    constraint_for_replanning: Optional[str]

class GuardrailLog(TypedDict):
    check_type: Literal["prompt_injection", "pii_masking"]
    triggered: bool
    details: str
    timestamp: str

class TravelState(TypedDict):
    # Input
    user_request: str
    destination: str
    travel_dates: str
    budget_limit: float
    traveler_preferences: List[str]
    # Agent 1 (Planner / ReAct)
    react_trace: Annotated[List[ReActStep], operator.add]
    search_results: Annotated[List[SearchResult], operator.add]
    draft_itinerary: List[ItineraryItem]
    # Agent 2 (Budget)
    budget_analysis: Optional[BudgetBreakdown]
    # Agent 3 (Audit)
    final_summary: Optional[str]
    audit_notes: List[str]
    # Guardrails
    guardrail_logs: Annotated[List[GuardrailLog], operator.add]
    pii_masked: bool
    # Control flow
    iteration_count: int
    max_iterations: int
    replan_reason: Optional[str]
    # HITL
    human_approved: Optional[bool]
    human_feedback: Optional[str]
    # Cross-cutting
    execution_logs: Annotated[List[str], operator.add]
    status: Literal["in_progress", "awaiting_human", "completed", "failed"]
