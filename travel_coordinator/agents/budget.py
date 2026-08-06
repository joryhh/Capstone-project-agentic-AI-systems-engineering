"""Agent 2: Budget & Logistics + budget_router (Member B, D2/D3)."""
import re
from typing import Literal
from ..observability import traced
from ..state import TravelState

# ============================================================
# SECTION 6 — AGENT 2: BUDGET & LOGISTICS   [Member B]  (D3 + D2 loop trigger)
# ============================================================
# Calls real cost-estimation tools for each itinerary item, aggregates by
# category, compares to budget_limit, and — if over — writes a CONCRETE
# constraint_for_replanning back into shared state (the message contract).

_FLIGHT_RATES = {"kyoto":780.0,"tokyo":780.0,"paris":650.0,"rome":610.0,"cairo":540.0,"bali":720.0,"new york":300.0}
_HOTEL_NIGHTLY = {"budget":60.0,"mid-range":140.0,"luxury":320.0}
_TRANSIT_DAILY = {"public_transit":12.0,"rental_car":55.0,"taxi":40.0}
_ENTRY_FEE_DEFAULT = {"temple":8.0,"museum":18.0,"shrine":5.0,"park":10.0,"landmark":15.0}

def tool_estimate_flight_cost(origin, destination, cabin_class="economy"):
    base = _FLIGHT_RATES.get(destination.lower(), 700.0)
    return round(base * {"economy":1.0,"premium_economy":1.4,"business":2.8}.get(cabin_class,1.0), 2)

def tool_estimate_accommodation_cost(destination, nights, tier="mid-range"):
    return round(_HOTEL_NIGHTLY.get(tier, _HOTEL_NIGHTLY["mid-range"]) * max(nights,0), 2)

def tool_estimate_transit_cost(destination, mode="public_transit", days=1):
    return round(_TRANSIT_DAILY.get(mode, _TRANSIT_DAILY["public_transit"]) * max(days,1), 2)

def tool_estimate_entry_fee(location, site_type="landmark"):
    return round(_ENTRY_FEE_DEFAULT.get(site_type, _ENTRY_FEE_DEFAULT["landmark"]), 2)

TOOL_REGISTRY = {"flight":tool_estimate_flight_cost, "accommodation":tool_estimate_accommodation_cost,
                 "transit":tool_estimate_transit_cost, "entry_fee":tool_estimate_entry_fee}

@traced("node")
def agent2_budget_node(state: TravelState) -> dict:
    itinerary = state["draft_itinerary"]
    destination = state["destination"]
    logs = [f"Agent 2 (Budget) verifying {len(itinerary)} itinerary items via cost tools."]
    cost_by_category, verified_items = {}, []

    for item in itinerary:
        category = item["category"]
        fn = TOOL_REGISTRY.get(category)
        if fn is tool_estimate_flight_cost:
            cost = fn(origin="home", destination=destination)
        elif fn is tool_estimate_accommodation_cost:
            m = re.search(r"(\d+)\s*night", item["activity"], re.IGNORECASE)
            nights = int(m.group(1)) if m else 1
            tier = "luxury" if "luxury" in item["activity"].lower() else "mid-range"
            cost = fn(destination=destination, nights=nights, tier=tier)
        elif fn is tool_estimate_transit_cost:
            cost = fn(destination=destination)
        elif fn is tool_estimate_entry_fee:
            cost = fn(location=item["location"])
        else:
            cost = item["estimated_cost"]  # activity/food: trust planner estimate
            logs.append(f"  no pricing tool for '{category}' ({item['activity']}); using ${cost:.2f}")
        logs.append(f"  [tool] {category} -> ${cost:.2f} for '{item['activity']}' (day {item['day']})")
        cost_by_category[category] = round(cost_by_category.get(category, 0.0) + cost, 2)
        vi = dict(item); vi["estimated_cost"] = cost; verified_items.append(vi)

    total = round(sum(cost_by_category.values()), 2)
    limit = state["budget_limit"]
    over = total > limit
    over_amt = round(max(0.0, total - limit), 2)
    constraint = None
    if over:
        worst = max(cost_by_category, key=cost_by_category.get)
        constraint = (f"Over budget by ${over_amt:.2f} (total ${total:.2f} vs limit ${limit:.2f}). "
                      f"Largest driver is '{worst}' at ${cost_by_category[worst]:.2f}. "
                      f"Cut at least ${over_amt:.2f} from '{worst}' before resubmitting.")
        logs.append(f"  [Agent 2] OVER BUDGET -> {constraint}")
    else:
        logs.append(f"  [Agent 2] within budget: ${total:.2f} <= ${limit:.2f}")

    budget_analysis = {"total_estimated_cost":total, "budget_limit":limit, "over_budget":over,
                       "over_budget_amount":over_amt, "cost_by_category":cost_by_category,
                       "constraint_for_replanning":constraint}
    return {"budget_analysis": budget_analysis, "replan_reason": constraint,
            "draft_itinerary": verified_items, "execution_logs": logs}

def budget_router(state: TravelState) -> Literal["replan", "proceed"]:
    # Termination guard FIRST — an unfixable budget must not loop forever.
    if state["iteration_count"] >= state["max_iterations"]:
        print(f"  [Router] max iterations ({state['max_iterations']}) reached -> proceed.")
        return "proceed"
    b = state.get("budget_analysis")
    if b and b["over_budget"]:
        print(f"  [Router] over budget by {b['over_budget_amount']} -> replan.")
        return "replan"
    print("  [Router] within budget -> proceed.")
    return "proceed"
