# Architecture — Automated Travel & Itinerary Coordinator

## 1. Overview
A multi-agent system implemented as a LangGraph `StateGraph`. Three specialized agents plus a human-in-the-loop gate collaborate over a single shared state object to produce a budget-checked, safety-audited, human-approved travel itinerary. Coordination is **centralized through shared state**: no agent calls another directly — the graph is the coordinator.

## 2. State (the message contract)
`TravelState` (a `TypedDict`) is the one object every node reads and writes. Notable channels:
- **Append channels** (reducer `operator.add`): `react_trace`, `search_results`, `guardrail_logs`, `execution_logs` — each node contributes without clobbering others.
- **Overwrite channels**: `draft_itinerary`, `budget_analysis`, `final_summary`, `status`, control-flow counters (`iteration_count`, `max_iterations`, `replan_reason`), and HITL fields (`human_approved`, `human_feedback`).

Sub-schemas: `ItineraryItem`, `BudgetBreakdown`, `GuardrailLog`, `SearchResult`, `ReActStep`.

## 3. Nodes (agents) and tools
| Node | Agent | Reasoning / tools |
|---|---|---|
| `agent1_planner` | Destination Planner | **ReAct** loop (Thought → Action → Observation) via Groq function-calling; real **Tavily** `search_travel_info` tool with retry/backoff; parses its plan into a structured `draft_itinerary`. Short-term memory = the message list across ReAct steps. |
| `agent2_budget` | Budget & Logistics | Four cost-estimation tools (flight / accommodation / transit / entry-fee); aggregates `cost_by_category`; writes a concrete `constraint_for_replanning` when over budget. |
| `agent3_audit` | Safety & Policy Guardrail | Deterministic rule audit + LLM audit; **PII output masking** (email / passport / phone); formats `final_summary`; sets `status="awaiting_human"`. |
| `human_review` | Human-in-the-Loop | Real `interrupt()` gate; approve → `completed`, reject+feedback → loop back to Agent 1. |

## 4. Edges and control flow
- `agent1_planner → agent2_budget` (normal edge)
- `agent2_budget → budget_router` (**conditional edge**): `over_budget → agent1_planner` (re-plan), else `→ agent3_audit`
- `agent3_audit → human_review` (normal edge)
- `human_review → human_review_router` (**conditional edge**): `completed → END`, else `→ agent1_planner`

**Loop termination.** `budget_router` checks `iteration_count >= max_iterations` *first* and forces `proceed`, so an unsatisfiable budget cannot loop forever. LangGraph's own `recursion_limit` is a second independent safety net.

## 5. Security & observability (D4)
- **Input guardrail** (`PromptInjectionGuardrail`): hybrid pattern + LLM screening of externally retrieved review snippets — indirect prompt-injection defense — applied inside Agent 1 before content enters the planning context, and available standalone via `screen_search_results`.
- **Output guardrail**: PII masking in Agent 3 before any summary or log is emitted.
- **Observability** (`Tracer` + `@traced`): every node and tool call records latency, success/failure, and timestamp as structured spans; LLM token usage is captured for a cost estimate. Surfaced as a metrics table + bar chart — structured monitoring, not print statements.

## 6. Production readiness (D5)
- **Persistence**: `SqliteSaver` checkpointer writes state to `checkpoints.sqlite`; a run survives a process restart (resume by `thread_id`).
- **HITL**: real `interrupt()` pause; resume with `Command(resume={"approved": ..., "feedback": ...})`.
- **Cloud**: `Dockerfile` + `app.py` (FastAPI) expose `/health`, `/plan`, `/decision`; `docker-compose.yml` runs it with a mounted volume for the checkpoint DB.
