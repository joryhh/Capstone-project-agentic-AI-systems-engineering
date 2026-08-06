# Itinera AI

**Itinera AI** is an AI-powered **Multi-Agent Travel and Itinerary Coordination System** that turns a single trip request into a budget-checked, safety-audited, human-approved day-by-day itinerary. It is built with LangGraph, Groq (Llama 3.3 70B), real web-search tooling, SQLite checkpointing, security guardrails, structured observability, a human-in-the-loop approval gate, FastAPI, and Docker.

> **Students:** Ghala Alawad, Lujain, Jory Alhassan
>
> **Training program:** Advanced Agentic AI Systems Engineering
>
> **Delivered by:** SDAIA Academy
>
> **Trainer:** Mohammed Albeladi
>
> **Cohort/session dates:** **August 2 - August 6 2026**

---

## Project Description

**Itinera AI** coordinates the main activities required to plan a trip: deciding what to do, verifying what it costs, and confirming that the plan is safe and sensible before a human approves it.

Planning a trip normally means balancing three concerns that pull against one another. A traveller wants an interesting itinerary, but the itinerary must fit a budget, and it must also be practical and free of unsafe or exposed information. When these concerns are handled by a single prompt pretending to do everything at once, the result is often an itinerary that ignores the budget, overlooks practical constraints, or leaks personal details into its output.

Itinera AI addresses this through a LangGraph workflow that coordinates specialized agents using a single shared state. The system does not rely on one model call to perform every responsibility. Instead, it uses multiple named agents, each with a distinct role, structured outputs, and access to the information produced by earlier agents.

The workflow begins with a **Destination Planner Agent** that reasons using the ReAct pattern, calls a real web-search tool to gather current information, and produces a structured draft itinerary. A **Budget and Logistics Agent** then verifies the cost of every itinerary item through dedicated cost-estimation tools, compares the total against the budget, and — when the plan is over budget — writes a concrete constraint back into shared state so the planner can revise. This revision loop is bounded by a maximum-iteration counter so an unsatisfiable budget cannot loop indefinitely.

Once the plan is within budget, a **Safety and Policy Guardrail Agent** audits the itinerary for practical concerns, masks any personally identifiable information before it can reach the summary or logs, and formats a human-readable recap. The graph then pauses at a genuine human-in-the-loop approval node, where a reviewer can approve the itinerary or reject it with feedback that sends the workflow back to the planner.

Throughout execution, an input guardrail screens externally retrieved content for prompt-injection attempts before it enters the planning context, and a structured observability layer records the latency, success or failure, and token cost of every node and tool call. Workflow state is persisted using a SQLite LangGraph checkpointer, allowing a paused run to survive a restart and resume later using the same thread identifier.

For production-readiness evidence, the repository includes a FastAPI application, a Dockerfile, a dependency file, a `.gitignore`, an architecture write-up, and an executed Colab notebook containing successful, re-planning, security, persistence, and human-approval demonstrations.

---

## Problem Statement

Planning a trip requires balancing competing goals — desirability, cost, and safety — that are usually managed manually across separate tools and searches.

Handled that way, or by a single undivided model call, this commonly leads to:

- Itineraries that exceed the stated budget
- Costs that are guessed rather than verified against a source
- Practical issues that are missed, such as over-packed days or missing accommodation
- Personal information exposed in generated output
- Untrusted retrieved content influencing the plan
- No visibility into tool calls, failures, or response times
- Loss of progress when a long-running process is interrupted
- Plans finalized without human oversight

Itinera AI provides one orchestrated workflow that manages these tasks while enforcing budget control, security, traceability, persistence, and human approval.

---

## System Objectives

The system is designed to:

1. Turn a trip request (destination, dates, budget, preferences) into a structured itinerary.
2. Reason using the ReAct pattern and call a real web-search tool for current information.
3. Verify the cost of every itinerary item through dedicated cost-estimation tools.
4. Compare the total against the budget and re-plan with a concrete constraint when over budget.
5. Bound the re-planning loop with a maximum-iteration guard so it always terminates.
6. Screen externally retrieved content for prompt-injection before it enters the planning context.
7. Audit the itinerary for practical and safety concerns.
8. Mask personally identifiable information before it reaches the summary or logs.
9. Pause for a real human decision before the itinerary is finalized.
10. Persist graph state so an interrupted workflow can resume later.
11. Capture structured logs, latency, failures, and token cost across the workflow.
12. Provide FastAPI and Docker artifacts as deployment evidence.

---

## Multi-Agent Architecture

The system uses a **centralized graph-orchestration strategy with shared-state communication**.

The LangGraph `StateGraph` acts as the central orchestrator. It routes execution among specialized agents through normal and conditional edges. No agent calls another agent directly; instead, every agent communicates by reading and updating a single shared `TravelState` object. The graph is the coordinator.

### Coordination Strategy

All three agents read from and write to one shared `TravelState`. Append-type channels (such as the reasoning trace, search results, guardrail logs, and execution logs) accumulate contributions from every node without overwriting one another, while decision fields (such as the draft itinerary, budget analysis, and status) are overwritten as the workflow progresses. The `budget_router` and `human_review_router` conditional edges read this shared state to decide the next step.

### Agents and Responsibilities

#### 1. Destination Planner Agent

Reasons using the **ReAct** pattern (Thought, Action, Observation). It calls a real web-search tool through Groq function-calling to gather current information about attractions, activities, and logistics, then parses its plan into a structured list of itinerary items. Short-term memory is maintained as the message list carried across ReAct steps. Retrieved content is screened by the input guardrail before it enters the planning context.

#### 2. Budget and Logistics Agent

Verifies the cost of every itinerary item using dedicated cost-estimation tools for flights, accommodation, transit, and entry fees. It aggregates cost by category, compares the total to the budget, and — when over budget — writes a concrete `constraint_for_replanning` back into shared state that names the largest cost driver and the exact amount to cut. This constraint is the message the planner consumes on the next revision.

#### 3. Safety and Policy Guardrail Agent

Audits the itinerary using both deterministic rules (over-packed days, gaps, missing accommodation) and an LLM pass (seasonal or practical concerns). It masks personally identifiable information — email, passport, and phone patterns — before any summary or log is produced, then formats the human-readable recap and marks the workflow as awaiting human review.

#### 4. Human-in-the-Loop Review

Pauses the graph at a genuine interrupt and surfaces the summary, audit notes, budget breakdown, and guardrail logs for a human decision. On approval the workflow completes; on rejection the reviewer's feedback is written back as a re-planning constraint and the graph loops to the planner.

---

## Workflow

```text
Trip Request
   |
   v
Destination Planner Agent (ReAct: Thought -> Action(search) -> Observation)
   |   input guardrail screens retrieved content
   v
Budget and Logistics Agent
   |
   |-- over budget --> budget_router --> re-plan (loop back to Planner)
   |
   |   within budget
   v
Safety and Policy Guardrail Agent (audit + PII masking + summary)
   |
   v
Human-in-the-Loop Interrupt
   |            \
   | approve     \ reject + feedback --> re-plan (loop back to Planner)
   v
Final Itinerary
```

The workflow is implemented as a LangGraph `StateGraph` with shared state, conditional edges, a bounded re-planning loop, and a human-in-the-loop breakpoint.

---

## Reasoning Pattern

Itinera AI's planning agent implements the **ReAct** reasoning pattern. The agent alternates between reasoning steps (Thought), tool actions (Action, a real web search), and results (Observation), looping until it has enough information to produce a final structured itinerary. The loop is bounded by a maximum number of reasoning steps so it always terminates.

---

## Graph Orchestration

- **Nodes:** `agent1_planner`, `agent2_budget`, `agent3_audit`, `human_review`
- **Normal edges:** planner to budget, audit to human review
- **Conditional edges:** `budget_router` (re-plan versus proceed) and `human_review_router` (loop versus end)
- **Loop termination:** `budget_router` checks the iteration count against the maximum first and forces the workflow to proceed once the limit is reached, so an unsatisfiable budget cannot loop forever. LangGraph's own recursion limit acts as a second, independent safety net.

---

## Security and Guardrails

- **Input guardrail (prompt-injection):** a hybrid pattern-plus-LLM filter screens externally retrieved review snippets before they reach the planning context, defending against indirect prompt injection. Flagged content is dropped and logged.
- **Output guardrail (PII masking):** the Safety Agent masks email, passport, and phone patterns before any summary or log is emitted.
- **Structured output validation:** the planner's free-text plan is parsed and validated into typed itinerary items, and unsafe categories are coerced to safe defaults.

---

## Observability

A structured observability layer records every node and tool call as a span capturing latency, success or failure, and timestamp, and captures LLM token usage for a cost estimate. These are aggregated into a metrics table and a bar chart at the end of a run. This is structured monitoring rather than plain print statements.

---

## Persistence

Itinera AI uses a **SQLite-based LangGraph checkpointer** (`SqliteSaver`) to persist workflow state. A run paused at the human-in-the-loop interrupt survives a process restart and can be resumed from disk using the same `thread_id`, which the notebook demonstrates directly.

---

## Human-in-the-Loop

Before the itinerary is finalized, the graph pauses at a real human-in-the-loop node.

The reviewer can choose to:

- Approve the itinerary, which completes the workflow
- Reject it with feedback, which is written back as a re-planning constraint and routes the graph to the planner

The graph then resumes execution based on the selected decision.

---

## Technologies

- Python
- Google Colab
- LangGraph
- LangChain
- Groq (Llama 3.3 70B)
- Tavily (web search)
- SQLite (LangGraph checkpointer)
- FastAPI
- Uvicorn
- Docker
- Matplotlib

---

## Repository Structure

```text
Capstone-project-agentic-AI-systems-engineering/
├── capstone_main.ipynb          # integrated system and executed evidence
├── travel_coordinator/          # the same final code, as an importable package
│   ├── __init__.py              # exposes build_app and make_initial_state
│   ├── state.py                 # shared TravelState schema
│   ├── observability.py         # tracer and instrumentation
│   ├── guardrails.py            # prompt-injection input guardrail
│   ├── runtime.py               # shared LLM and tool singletons
│   ├── hitl.py                  # human-in-the-loop node and router
│   ├── graph.py                 # graph assembly and build_app factory
│   └── agents/
│       ├── __init__.py
│       ├── planner.py           # Agent 1: ReAct planner and search tool
│       ├── budget.py            # Agent 2: cost tools and budget router
│       └── safety.py            # Agent 3: audit and PII masking
├── app.py                       # FastAPI service
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .gitignore
├── README.md
└── ARCHITECTURE.md              # technical write-up
```

The complete multi-agent implementation is available inside `capstone_main.ipynb` for reproducible evaluation in Google Colab. The `travel_coordinator` package is the same final code organized for import and deployment.

---

## Prerequisites

- Python 3.11 or later
- A **Groq** API key (LLM: Llama 3.3 70B)
- A **Tavily** API key (web search)

Itinera AI does **not** store API keys in the GitHub repository.

---

## Setup

Clone the repository and install dependencies:

```bash
git clone https://github.com/joryhh/Capstone-project-agentic-AI-systems-engineering.git
cd Capstone-project-agentic-AI-systems-engineering
pip install -r requirements.txt
```

Provide the two API keys as environment variables (for the service) or in the Colab Secrets panel (for the notebook):

```bash
export GROQ_API_KEY=your_groq_key
export TAVILY_API_KEY=your_tavily_key
```

---

## How to Run

### Option 1 - Google Colab (recommended for evaluation)

1. Open `capstone_main.ipynb` in Google Colab.
2. Open the **Secrets** panel and add two secrets, `GROQ_API_KEY` and `TAVILY_API_KEY`, then enable notebook access to each.
3. From the menu select **Runtime -> Restart session and run all**.

The notebook installs the required dependencies, runs the full system end to end, and captures the output for every demonstration.

### Option 2 - As a service

```bash
uvicorn app:api --host 0.0.0.0 --port 8000
```

### Option 3 - With Docker

```bash
docker build -t itinera-ai .
docker run -p 8000:8000 -e GROQ_API_KEY=$GROQ_API_KEY -e TAVILY_API_KEY=$TAVILY_API_KEY itinera-ai
# or:
docker compose up --build
```

Example request:

```bash
curl -X POST localhost:8000/plan -H 'Content-Type: application/json' \
  -d '{"destination":"Kyoto","travel_dates":"2026-11-10 to 2026-11-15","budget_limit":2000,"preferences":["food","temples"]}'
```

The `/plan` endpoint returns an itinerary summary awaiting human approval; the `/decision` endpoint resumes the paused run with an approve or reject decision.

---

## Expected Output

Itinera AI produces:

- A structured, day-by-day itinerary with per-item cost
- A budget breakdown by category with an over- or within-budget status
- Audit and safety notes for the plan
- A human-readable summary with personal information masked
- Structured execution logs and a metrics summary (tool calls, latency, failures, token cost)

The executed notebook additionally demonstrates: a full planning run ending in human approval, a re-planning loop that fires and terminates on the guard, blocked prompt-injection attempts, masked PII in the summary, and a checkpoint surviving a simulated restart.

---

## Cloud and Production Artifact

The repository includes a lightweight **FastAPI** service (`app.py`) exposing `/health`, `/plan`, and `/decision` endpoints, together with a **Dockerfile** and **docker-compose** configuration, as production-readiness artifacts. The `docker-compose` file mounts a volume so the checkpoint database persists outside the container. The complete multi-agent implementation remains available inside `capstone_main.ipynb` for reproducible evaluation in Google Colab.

---

## Capstone Concepts Demonstrated

Itinera AI demonstrates the key concepts covered in **Advanced Agentic AI Systems Engineering**, including:

- Agentic reasoning with the ReAct pattern
- Real tool usage (web search and cost-estimation tools)
- Graph-based orchestration with a LangGraph `StateGraph`
- Multi-agent collaboration and agent role specialization
- Shared state and conditional routing
- Bounded re-planning loops with a termination guard
- Security guardrails (prompt-injection screening and PII masking)
- Structured observability (latency, failures, token cost)
- Persistent checkpoints and restart survival
- Human-in-the-loop approval
- Production-readiness with FastAPI and Docker

---

## Team

- **Ghala Alawad**
- **Lujain**
- **Jory Alhassan**

---

## Training Program Attribution

Developed as part of the **Advanced Agentic AI Systems Engineering** program delivered by **SDAIA Academy**, trained by **Mohammed Albeladi**, cohort dates **August 2 - August 6 2026**.

SDAIA Academy on GitHub: https://github.com/SDAIAAcademy
