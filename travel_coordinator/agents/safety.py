"""Agent 3: Safety & Policy Guardrail + PII output masking (Member C, D3/D4)."""
import re, json
from datetime import datetime
from collections import defaultdict
from langchain_core.messages import HumanMessage
from .. import runtime
from ..observability import traced, record_llm_usage
from ..state import TravelState

# ============================================================
# SECTION 7 — AGENT 3: SAFETY & POLICY GUARDRAIL   [Member C]  (D3 + D4 output guardrail)
# ============================================================
# Audits the itinerary (rules + LLM), masks PII (email/passport/phone) before
# it reaches the summary/logs, and formats the final_summary for human review.

class SafetyPolicyGuardrailAgent:
    EMAIL_RE    = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
    PASSPORT_RE = re.compile(r"\b[A-Z]{1,2}\d{6,9}\b")
    PHONE_RE    = re.compile(r"\+?\d{1,3}[\s-]?\d{2,4}[\s-]?\d{3}[\s-]?\d{3,4}")

    def __init__(self, llm):
        self.llm = llm

    def rule_based_audit(self, itinerary):
        notes = []
        if not itinerary:
            return ["No itinerary items to audit."]
        per_day = defaultdict(list)
        for it in itinerary:
            per_day[it["day"]].append(it)
        for day in sorted(per_day):
            acts = [i for i in per_day[day] if i["category"] == "activity"]
            if len(acts) > 4:
                notes.append(f"Day {day}: {len(acts)} activities — likely over-packed, no rest interval.")
        days = sorted(per_day)
        missing = [d for d in range(days[0], days[-1] + 1) if d not in per_day]
        if missing:
            notes.append(f"Itinerary has gaps: no plan for day(s) {missing}.")
        if len(days) > 1 and not any(i["category"] == "accommodation" for i in itinerary):
            notes.append("Multi-day trip but no accommodation item found.")
        return notes

    def llm_audit(self, state):
        text = "\n".join(f"Day {i['day']}: {i['activity']} @ {i['location']} ({i['category']})"
                         for i in state["draft_itinerary"])
        prompt = ("You are a travel safety advisor. Audit for PRACTICAL constraints only "
                  "(extreme/seasonal weather for the dates, travel advisories, pacing). "
                  'Respond ONLY with JSON: {"concerns": ["...", "..."]}. Empty list if none.\n\n'
                  f"Destination: {state['destination']}\nDates: {state['travel_dates']}\nItinerary:\n{text}")
        resp = self.llm.invoke([HumanMessage(content=prompt)])
        record_llm_usage(resp, "agent3_audit")
        raw = resp.content.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```[a-z]*\n?", "", raw); raw = re.sub(r"\n?```$", "", raw)
        try:
            return list(json.loads(raw).get("concerns", []))
        except Exception:
            return ["(LLM audit could not be parsed — manual review advised.)"]

    def mask_pii(self, text):
        found = {}
        for pat, label in [(self.EMAIL_RE,"EMAIL"), (self.PASSPORT_RE,"PASSPORT"), (self.PHONE_RE,"PHONE")]:
            if pat.findall(text):
                found[label] = found.get(label, 0) + len(pat.findall(text))
                text = pat.sub(f"[REDACTED-{label}]", text)
        return text, found

    def format_summary(self, state, audit_notes):
        lines = [f"TRIP SUMMARY — {state['destination']}", f"Dates: {state['travel_dates']}", "", "Day-by-day plan:"]
        pii_total = {}
        for it in sorted(state["draft_itinerary"], key=lambda x: x["day"]):
            activity, f1 = self.mask_pii(it["activity"])
            location, f2 = self.mask_pii(it["location"])
            for d in (f1, f2):
                for k, v in d.items():
                    pii_total[k] = pii_total.get(k, 0) + v
            lines.append(f"  Day {it['day']}: {activity} @ {location} — {it['category']}, ~${it['estimated_cost']:.0f}")
        lines.append("")
        b = state.get("budget_analysis")
        if b:
            status = "within budget" if not b["over_budget"] else f"OVER by ${b['over_budget_amount']:.0f}"
            lines += ["Budget:", f"  Estimated total: ${b['total_estimated_cost']:.0f} (limit ${b['budget_limit']:.0f})",
                      f"  Status: {status}", ""]
        lines.append("Audit & safety notes:")
        lines += [f"  - {n}" for n in audit_notes] if audit_notes else ["  - No practical concerns flagged."]
        lines += ["", "Ready for human review."]
        return "\n".join(lines), pii_total

    def run(self, state):
        notes = self.rule_based_audit(state["draft_itinerary"]) + self.llm_audit(state)
        summary, pii = self.format_summary(state, notes)
        return summary, notes, pii

@traced("node")
def agent3_audit_node(state: TravelState) -> dict:
    print("  [Agent 3 - Safety & Policy Guardrail] running.")
    agent = SafetyPolicyGuardrailAgent(runtime.llm)
    final_summary, audit_notes, pii_found = agent.run(state)
    log = {"check_type": "pii_masking", "triggered": bool(pii_found),
           "details": (f"Masked PII: {pii_found}" if pii_found else "No PII detected in itinerary text."),
           "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    print(f"    audit notes: {len(audit_notes)} | PII masked: {pii_found or 'none'}")
    return {"final_summary": final_summary, "audit_notes": audit_notes, "pii_masked": True,
            "guardrail_logs": [log], "execution_logs": ["Agent 3 (Safety & Policy Guardrail) executed"],
            "status": "awaiting_human"}   # hand-off to B's HITL node
