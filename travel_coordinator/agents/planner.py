"""Agent 1: Destination Planner — ReAct + real search tool (Member A, D1)."""
import os, re, json, time
from typing import List, Optional
from datetime import datetime, timezone
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage
from .. import runtime
from ..observability import traced, record_llm_usage
from ..state import TravelState, ItineraryItem

# ============================================================
# SECTION 5 — AGENT 1: DESTINATION PLANNER   [Member A, fixed by C at integration]
# Reasoning pattern: ReAct (Thought -> Action -> Observation).  (D1)
# ------------------------------------------------------------
# Integration fixes applied (both were pipeline-breaking):
#   FIX 1: Agent 1 now PARSES its free-text plan into structured ItineraryItem
#          objects (draft_itinerary), so Agents 2 & 3 actually receive data.
#          (Original returned draft_itinerary=[].)
#   FIX 2: Removed the `_raw_plan_text` return key — it is not in TravelState,
#          and LangGraph rejects writes to undefined channels.
#   ADD:   Member C's input guardrail now screens each retrieved observation
#          (pattern layer) before it enters the planning context.
#   ADD:   @traced instrumentation on the node and the search tool.
# ============================================================

@traced("tool")
def search_travel_info(query: str, max_retries: int = 3) -> str:
    """Real web search tool. Retries with exponential backoff, then degrades
    gracefully instead of crashing the graph (the retry/fallback path)."""
    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            results = runtime.tavily.search(query=query, max_results=3, search_depth="basic")
            formatted = [f"- {r['title']}: {r['content'][:300]} (source: {r['url']})"
                         for r in results.get("results", [])]
            return "\n".join(formatted) if formatted else "No results found."
        except Exception as e:
            last_error = e
            wait = 2 ** attempt
            print(f"  [search] attempt {attempt}/{max_retries} failed: {e}; retry in {wait}s")
            time.sleep(wait)
    print(f"  [search] all {max_retries} attempts failed — degrading gracefully.")
    return f"[SEARCH UNAVAILABLE after {max_retries} retries: {last_error}]"

TOOLS_SCHEMA = [{
    "type": "function",
    "function": {
        "name": "search_travel_info",
        "description": "Search the web for real, current travel info: attractions, activities, neighborhoods, seasonal notes, logistics.",
        "parameters": {"type": "object",
                       "properties": {"query": {"type": "string", "description": "e.g. 'best temples in Kyoto November'"}},
                       "required": ["query"]},
    },
}]

MAX_REACT_STEPS = 4

VALID_CATEGORIES = {"flight", "accommodation", "transit", "activity", "food", "entry_fee"}

def parse_itinerary_to_items(plan_text: str) -> List[ItineraryItem]:
    """FIX 1: convert Agent 1's free-text plan into structured ItineraryItems
    via one strict-JSON LLM call. Coerces bad categories, skips malformed rows."""
    prompt = (
        "Convert the travel plan below into a STRICT JSON array. Each element MUST be:\n"
        '{"day": int, "activity": str, "location": str, "estimated_cost": number, '
        '"category": one of ["flight","accommodation","transit","activity","food","entry_fee"]}\n'
        "Respond ONLY with the JSON array, no markdown.\n\nPLAN:\n" + plan_text
    )
    resp = runtime.llm.invoke([HumanMessage(content=prompt)])
    record_llm_usage(resp, "agent1_itinerary_parse")
    raw = resp.content.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*\n?", "", raw); raw = re.sub(r"\n?```$", "", raw)
    try:
        data = json.loads(raw)
    except Exception as e:
        print("  [Agent 1] itinerary parse failed, returning []:", e)
        return []
    items: List[ItineraryItem] = []
    for d in (data if isinstance(data, list) else []):
        try:
            cat = d.get("category", "activity")
            if cat not in VALID_CATEGORIES:
                cat = "activity"
            items.append({
                "day": int(d.get("day", 0)),
                "activity": str(d.get("activity", "")).strip(),
                "location": str(d.get("location", "")).strip(),
                "estimated_cost": float(d.get("estimated_cost", 0) or 0),
                "category": cat,
            })
        except Exception:
            continue
    return items

@traced("node")
def agent1_planner_node(state: TravelState) -> dict:
    print("  [Agent 1 - Planner] Starting ReAct loop...")
    destination = state.get("destination", "")
    dates = state.get("travel_dates", "")
    prefs = ", ".join(state.get("traveler_preferences", []))
    budget = state.get("budget_limit", "unspecified")
    replan_reason = state.get("replan_reason")

    system_prompt = f"""You are a travel destination planning agent using the ReAct pattern.
Each turn: reason step by step (Thought), then either call search_travel_info (Action) to get
real info, or finalize a day-by-day itinerary once you have enough.

Destination: {destination}
Dates: {dates}
Preferences: {prefs}
Budget limit: {budget}
{"IMPORTANT constraint from budget review: " + replan_reason if replan_reason else ""}

When ready, respond in plain text starting with 'FINAL ITINERARY:' then a day-by-day
breakdown with an estimated cost per item."""

    messages = [SystemMessage(content=system_prompt),
                HumanMessage(content="Begin planning. Think first, then act.")]

    react_trace, new_search_results, new_guardrail_logs = [], [], []
    step = 0
    response = None

    while step < MAX_REACT_STEPS:
        step += 1
        response = runtime.llm_with_tools.invoke(messages)
        record_llm_usage(response, "agent1_react")
        messages.append(response)
        tool_calls = getattr(response, "tool_calls", None)

        if not tool_calls:
            react_trace.append({"thought": (response.content or "")[:500],
                                "action": "none (final answer)", "action_input": "", "observation": ""})
            break

        for call in tool_calls:
            query = call["args"].get("query", "")
            print(f"  [Agent 1] step {step}: Action=search_travel_info query='{query}'")
            observation = search_travel_info(query)

            # --- Member C's input guardrail: screen retrieved content (pattern layer) ---
            verdict = runtime.guardrail.scan(observation, use_llm=False)
            if verdict["is_injection"]:
                new_guardrail_logs.append({
                    "check_type": "prompt_injection", "triggered": True,
                    "details": f"BLOCKED retrieved content for query='{query}' — {verdict['reason']}",
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                })
                print(f"    [GUARDRAIL] injection in retrieved content BLOCKED: {verdict['reason']}")
                observation = "[BLOCKED: retrieved content flagged as prompt injection and withheld]"

            react_trace.append({"thought": (response.content or "(reasoning to call tool)")[:500],
                                "action": "search_travel_info", "action_input": query,
                                "observation": observation[:500]})
            new_search_results.append({"source": "attraction_search", "query": query,
                                       "raw_content": observation, "url": None})
            messages.append(ToolMessage(content=observation, tool_call_id=call["id"]))
    else:
        print(f"  [Agent 1] hit MAX_REACT_STEPS ({MAX_REACT_STEPS}) — forcing finalize.")
        response = runtime.llm.invoke(messages + [HumanMessage(content="Finalize now with FINAL ITINERARY:.")])
        record_llm_usage(response, "agent1_react")
        messages.append(response)

    final_text = messages[-1].content
    # FIX 1: structure the plan so downstream agents receive real items
    draft_itinerary = parse_itinerary_to_items(final_text)
    print(f"  [Agent 1] loop done: {step} step(s), {len(new_search_results)} tool call(s), "
          f"{len(draft_itinerary)} itinerary item(s).")

    return {
        "react_trace": react_trace,
        "search_results": new_search_results,
        "guardrail_logs": new_guardrail_logs,
        "draft_itinerary": draft_itinerary,     # FIX 1: populated (was [])
        "execution_logs": [f"Agent 1 completed ReAct: {step} step(s), "
                           f"{len(new_search_results)} tool call(s), {len(draft_itinerary)} items."],
        "iteration_count": state["iteration_count"] + 1,
        # FIX 2: no `_raw_plan_text` (not a TravelState channel).
    }
