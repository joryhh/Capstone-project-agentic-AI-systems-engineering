"""
FastAPI wrapper around the compiled agentic graph — the cloud deployment artifact (D5).
Run locally:   uvicorn app:app --host 0.0.0.0 --port 8000
Then POST a trip request to /plan.
"""
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Optional
import sqlite3

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command
from travel_coordinator import build_app, make_initial_state

api = FastAPI(title="Automated Travel & Itinerary Coordinator")

_conn = sqlite3.connect("checkpoints.sqlite", check_same_thread=False)
_graph = build_app(checkpointer=SqliteSaver(_conn))


class TripRequest(BaseModel):
    destination: str
    travel_dates: str
    budget_limit: float
    preferences: List[str] = []
    max_iterations: int = 3


class Decision(BaseModel):
    thread_id: str
    approved: bool
    feedback: Optional[str] = None


@api.get("/health")
def health():
    return {"status": "ok"}


@api.post("/plan")
def plan(req: TripRequest):
    """Start a planning run. Returns the itinerary summary awaiting human approval."""
    thread_id = f"trip-{req.destination.lower().replace(' ', '-')}-{abs(hash(req.travel_dates)) % 10000}"
    cfg = {"configurable": {"thread_id": thread_id}}
    init = make_initial_state(req.destination, req.travel_dates, req.budget_limit,
                              req.preferences, req.max_iterations)
    _graph.invoke(init, config=cfg)              # runs until the HITL interrupt
    snap = _graph.get_state(cfg).values
    return {"thread_id": thread_id, "status": snap["status"],
            "final_summary": snap.get("final_summary"),
            "audit_notes": snap.get("audit_notes"),
            "budget_analysis": snap.get("budget_analysis")}


@api.post("/decision")
def decision(d: Decision):
    """Resume a paused run with the human's approve/reject decision (HITL)."""
    cfg = {"configurable": {"thread_id": d.thread_id}}
    final = _graph.invoke(Command(resume={"approved": d.approved, "feedback": d.feedback}), config=cfg)
    return {"thread_id": d.thread_id, "status": final["status"],
            "human_approved": final.get("human_approved")}
