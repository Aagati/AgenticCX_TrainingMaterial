"""
PM · H4 — Retail: Capstone — Personalised Outbound Journey Agent (STARTER)

Every primitive in this file already exists somewhere in PM_H1-H3, in
slightly different clothes: ConsentGate (H3), an eligibility/quiet-hours
check (H1), locale-aware persona routing (H2), cost-tiered drafting (H1),
BrandSafetyLinter + repair (H3), journey memory (H2), and hand-off (H2).
This lab re-implements a thin, retail-flavored version of each. The new
piece is PERSONALISATION: which offer a customer sees is a lookup keyed
on their segment (retail_offer_catalog.json).

THE ORCHESTRATION IS MULTI-AGENT — a LangGraph StateGraph, not a flat
function-call chain. Two deterministic GATE nodes (given below) feed a
supervisor-style conditional router that delegates to whichever
SPECIALIST AGENT the situation calls for:

    ConsentGate ─┐
    (gate node)  │ blocked → END
                 ▼
    EligibilityEngine ─┐
    (gate node)        │ blocked → END
                        ▼
              at_risk_churn? ──yes──► EscalationAgent ──► END
                        │no
                        ▼
              TieringAgent (cheap classify → capable draft OR template)
                        ▼
              ComplianceAgent ──pass──► SendAgent ──► END
                        │fail (1st time)
                        ▼
                  RepairAgent ──loops back to── ComplianceAgent
                        │fail (2nd time, already repaired once)
                        ▼
                     END (blocked_safety)

You'll build the five specialist-agent nodes plus the graph wiring:
  1. _escalation_agent, 2. _tiering_agent, 3. _compliance_agent +
  _route_after_compliance, 4. _repair_agent, 5. _send_agent,
  6. _build_graph
"""

import json
import random
import sys
from datetime import datetime
from pathlib import Path
from typing import Literal, TypedDict

from anthropic import Anthropic
from dotenv import load_dotenv
from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field

load_dotenv()

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

MODEL_CHEAP = "claude-haiku-4-5-20251001"
MODEL_DRAFT = "claude-sonnet-5"

DATA_DIR = Path(__file__).parent
with open(DATA_DIR / "retail_offer_catalog.json") as f:
    CATALOG = json.load(f)

client = Anthropic()

CUSTOMERS = [
    {"customer_id": "RET-01", "name": "Talia Brooks", "locale": "en-US", "segment": "loyalty_gold",
     "consent": {"sms": True, "email": True}, "do_not_contact": False,
     "last_contacted_days_ago": 10, "timezone_offset_hours": -5, "at_risk_churn": False},
    {"customer_id": "RET-02", "name": "Marco Ruiz", "locale": "es-MX", "segment": "new_customer",
     "consent": {"sms": True, "email": True}, "do_not_contact": False,
     "last_contacted_days_ago": 20, "timezone_offset_hours": -6, "at_risk_churn": False},
    {"customer_id": "RET-03", "name": "Hana Kobayashi", "locale": "ja-JP", "segment": "loyalty_gold",
     "consent": {"sms": True, "email": True}, "do_not_contact": False,
     "last_contacted_days_ago": 40, "timezone_offset_hours": 3, "at_risk_churn": True},
    {"customer_id": "RET-04", "name": "Owen Baxter", "locale": "en-US", "segment": "new_customer",
     "consent": {"sms": False, "email": True}, "do_not_contact": False,
     "last_contacted_days_ago": 30, "timezone_offset_hours": -5, "at_risk_churn": False},
    {"customer_id": "RET-05", "name": "Ines Fischer", "locale": "de-DE", "segment": "loyalty_gold",
     "consent": {"sms": True, "email": True}, "do_not_contact": True,
     "last_contacted_days_ago": 50, "timezone_offset_hours": 1, "at_risk_churn": False},
]

LOCALE_PERSONAS = {
    "en-US": {"language_name": "English", "tone": "friendly and casual"},
    "es-MX": {"language_name": "Spanish", "tone": "warm and respectful, formal 'usted'"},
    "ja-JP": {"language_name": "Japanese", "tone": "highly formal and polite"},
    "de-DE": {"language_name": "German", "tone": "formal and precise, 'Sie' form"},
}


class TierClassification(BaseModel):
    tier: Literal["low", "high"] = Field(
        description="'high' if this customer's case warrants a bespoke personalised message; 'low' if a template offer is enough."
    )
    reason: str


class HandoffSummary(BaseModel):
    summary: str = Field(description="2-3 sentence summary, in English, for a human retention specialist.")
    key_facts: list[str]
    recommended_action: str
    sentiment: Literal["positive", "neutral", "negative"]


def in_quiet_hours(local_hour: int, window: list[int]) -> bool:
    """Given — same wrap-aware quiet-hours check as PM_H1."""
    start, end = window
    if start > end:
        return local_hour >= start or local_hour < end
    return start <= local_hour < end


def pick_channel(customer: dict) -> str | None:
    """Given — sms preferred if opted in, else email, else no channel to send on at all."""
    if customer["consent"].get("sms"):
        return "sms"
    if customer["consent"].get("email"):
        return "email"
    return None


class LanguageRouter:
    @staticmethod
    def route(locale: str) -> dict:
        return LOCALE_PERSONAS.get(locale, LOCALE_PERSONAS["en-US"])


class ConsentGate:
    """Given — do-not-contact + "is there ANY opted-in channel"."""

    @staticmethod
    def check(customer: dict) -> dict:
        if customer["do_not_contact"]:
            return {"allowed": False, "reason": "do_not_contact", "channel": None}
        channel = pick_channel(customer)
        if channel is None:
            return {"allowed": False, "reason": "no_opted_in_channel", "channel": None}
        return {"allowed": True, "reason": "ok", "channel": channel}


class EligibilityEngine:
    """Given — frequency cap + quiet hours."""

    @staticmethod
    def check(customer: dict, channel: str, now: datetime) -> dict:
        if customer["last_contacted_days_ago"] < CATALOG["frequency_cap_days"]:
            return {"eligible": False, "reason": "frequency_cap"}
        local_hour = (now.hour + customer["timezone_offset_hours"]) % 24
        quiet_window = CATALOG["channel_tiers"][channel]["quiet_hours"]
        if in_quiet_hours(local_hour, quiet_window):
            return {"eligible": False, "reason": "quiet_hours"}
        return {"eligible": True, "reason": "ok"}


class JourneyMemoryStore:
    """Given."""

    def __init__(self):
        self._facts: dict[str, list[str]] = {}

    def add_fact(self, customer_id: str, fact: str) -> None:
        self._facts.setdefault(customer_id, []).append(fact)

    def get_facts(self, customer_id: str) -> list[str]:
        return self._facts.get(customer_id, [])


class BrandSafetyLinter:
    """Given."""

    @staticmethod
    def check(draft_text: str) -> dict:
        text_lower = draft_text.lower()
        violations = [p for p in CATALOG["banned_phrases"] if p in text_lower]
        required = CATALOG["required_disclosure"]
        missing_disclosure = required.lower() not in text_lower
        return {
            "passed": not violations and not missing_disclosure,
            "banned_phrase_violations": violations,
            "missing_disclosure": required if missing_disclosure else None,
        }


def classify_tier(customer: dict, segment_data: dict) -> TierClassification:
    """Given — real haiku call, same shape as PM_H1's classify_urgency."""
    system = (
        "You triage outbound retail win-back offers. Decide 'high' if this customer's case "
        "warrants a personally-drafted message (e.g. a high-value loyalty customer, or a customer "
        "whose profile suggests a generic message would land poorly) or 'low' if a standard "
        "templated offer is sufficient."
    )
    user = f"Customer: {json.dumps({k: v for k, v in customer.items() if k != 'consent'})}\nOffer: {segment_data}"
    response = client.messages.create(
        model=MODEL_CHEAP, max_tokens=300, system=system,
        messages=[{"role": "user", "content": user}],
        tools=[{"name": "classify", "description": "Return the tier classification.",
                "input_schema": TierClassification.model_json_schema()}],
        tool_choice={"type": "tool", "name": "classify"},
    )
    tool_call = next(b for b in response.content if b.type == "tool_use")
    return TierClassification(**tool_call.input)


def draft_personalized_offer(customer: dict, segment_data: dict) -> str:
    """Given — real sonnet call, persona (locale) + offer (segment) combined."""
    persona = LanguageRouter.route(customer["locale"])
    required = CATALOG["required_disclosure"]
    system = (
        f"You write short outbound retail marketing messages. Respond in {persona['language_name']}. "
        f"Tone: {persona['tone']}. Never use absolute claims like guaranteed pricing or risk-free "
        f"offers. You MUST include this exact disclosure sentence verbatim, unmodified, as the "
        f"final sentence: \"{required}\""
    )
    user = f"Customer name: {customer['name']}\nSegment: {customer['segment']}\nOffer: {segment_data['offer_text']}"
    response = client.messages.create(
        model=MODEL_DRAFT, max_tokens=300, system=system, messages=[{"role": "user", "content": user}]
    )
    return next(b for b in response.content if b.type == "text").text.strip()


def template_offer_message(customer: dict, segment_data: dict) -> str:
    """Given — zero-token path for the "low" tier."""
    first_name = customer["name"].split()[0]
    return f"Hi {first_name}, here's an offer just for you: {segment_data['offer_text']}. {CATALOG['required_disclosure']}"


def repair_message(draft_text: str, lint_result: dict) -> str:
    """Given — one-shot, violation-specific repair, same as PM_H3."""
    problems = []
    if lint_result["banned_phrase_violations"]:
        problems.append(f"Remove/rephrase these banned phrases: {lint_result['banned_phrase_violations']}")
    if lint_result["missing_disclosure"]:
        problems.append(f"Add this exact disclosure sentence verbatim: \"{lint_result['missing_disclosure']}\"")
    system = "You rewrite outbound retail marketing messages to fix specific compliance problems, keeping the rest of the message's intent intact."
    user = f"Original message: {draft_text}\n\nProblems to fix:\n" + "\n".join(problems)
    response = client.messages.create(
        model=MODEL_DRAFT, max_tokens=300, system=system, messages=[{"role": "user", "content": user}]
    )
    return next(b for b in response.content if b.type == "text").text.strip()


class HandoffPackager:
    @staticmethod
    def build_handoff(customer: dict, reason: str, memory: JourneyMemoryStore) -> HandoffSummary:
        """Given — real sonnet call, always English."""
        facts = memory.get_facts(customer["customer_id"])
        system = (
            "You summarize a retail customer's situation for a human retention specialist who is "
            "about to reach out. Write summary, key_facts, and recommended_action in ENGLISH "
            "regardless of the customer's locale."
        )
        user = (
            f"Customer: {customer['name']} ({customer['locale']}, segment={customer['segment']})\n"
            f"Reason for hand-off: {reason}\nKnown facts: {facts or '(none yet)'}"
        )
        response = client.messages.create(
            model=MODEL_DRAFT, max_tokens=1024, system=system,
            messages=[{"role": "user", "content": user}],
            tools=[{"name": "summarize_handoff", "description": "Return the structured handoff bundle.",
                    "input_schema": HandoffSummary.model_json_schema()}],
            tool_choice={"type": "tool", "name": "summarize_handoff"},
        )
        tool_call = next(b for b in response.content if b.type == "tool_use")
        return HandoffSummary(**tool_call.input)


class ProactiveValueMeter:
    """Given — H1's uplift meter, unchanged in shape."""

    def __init__(self, seed: int | None = 11):
        self.rng = random.Random(seed)

    def measure_uplift(self, trigger_id: str, contacted_customers: list, control_size: int | None = None) -> dict:
        rates = CATALOG["baseline_conversion_rates"][trigger_id]
        control_size = control_size or max(len(contacted_customers), 1)
        contacted_conversions = sum(1 for _ in contacted_customers if self.rng.random() < rates["if_contacted"])
        control_conversions = sum(1 for _ in range(control_size) if self.rng.random() < rates["control"])
        contacted_rate = contacted_conversions / len(contacted_customers) if contacted_customers else 0.0
        control_rate = control_conversions / control_size if control_size else 0.0
        return {
            "trigger": trigger_id, "contacted_n": len(contacted_customers), "control_n": control_size,
            "contacted_rate": round(contacted_rate, 3), "control_rate": round(control_rate, 3),
            "uplift_pp": round((contacted_rate - control_rate) * 100, 1),
        }


class JourneyState(TypedDict, total=False):
    """Given — shared scratchpad every node reads from and writes partial
    updates into; LangGraph merges each node's returned dict into this
    state, same shallow-merge behavior Day6 PM_H2's ActionState relied on."""
    customer: dict
    trigger_id: str
    now: datetime
    channel: str | None
    event: str | None
    reason: str | None
    segment_data: dict | None
    tier: str | None
    model_used: str | None
    message: str | None
    lint_passed: bool
    violations: dict | None
    repaired: bool
    repair_attempted: bool
    handoff_summary: str | None
    recommended_action: str | None
    sentiment: str | None
    cost_units: int | None


class PersonalizedOutboundJourneyAgent:
    def __init__(self):
        self.memory = JourneyMemoryStore()
        self.analytics_log: list[dict] = []
        self.meter = ProactiveValueMeter()
        self.graph = self._build_graph()

    # ---------- Gate nodes (given — deterministic, no model call) ----------

    def _consent_node(self, state: JourneyState) -> dict:
        consent = ConsentGate.check(state["customer"])
        if not consent["allowed"]:
            return {"event": "blocked_consent", "reason": consent["reason"]}
        return {"channel": consent["channel"]}

    def _route_after_consent(self, state: JourneyState) -> Literal["eligibility", "end"]:
        return "end" if state.get("event") else "eligibility"

    def _eligibility_node(self, state: JourneyState) -> dict:
        eligibility = EligibilityEngine.check(state["customer"], state["channel"], state["now"])
        if not eligibility["eligible"]:
            return {"event": "blocked_eligibility", "reason": eligibility["reason"]}
        return {}

    def _route_after_eligibility(self, state: JourneyState) -> Literal["escalation_agent", "tiering_agent", "end"]:
        if state.get("event"):
            return "end"
        return "escalation_agent" if state["customer"]["at_risk_churn"] else "tiering_agent"

    def _blocked_safety_node(self, state: JourneyState) -> dict:
        return {"event": "blocked_safety"}

    # ---------- Specialist agents (TODO) ----------

    def _escalation_agent(self, state: JourneyState) -> dict:
        """
        TODO 1: handoff = HandoffPackager.build_handoff(state["customer"],
        a reason string mentioning state["trigger_id"], self.memory).
        Return {"event": "escalated", "handoff_summary": handoff.summary,
        "recommended_action": handoff.recommended_action, "sentiment":
        handoff.sentiment}.
        """
        raise NotImplementedError

    def _tiering_agent(self, state: JourneyState) -> dict:
        """
        TODO 2: customer = state["customer"]. segment_data =
        CATALOG["segments"].get(customer["segment"],
        CATALOG["segments"]["standard"]). tier = classify_tier(customer,
        segment_data). If tier.tier == "high": draft =
        draft_personalized_offer(customer, segment_data); model_used =
        MODEL_DRAFT. Else: draft = template_offer_message(customer,
        segment_data); model_used = "template". Return {"segment_data":
        segment_data, "tier": tier.tier, "model_used": model_used,
        "message": draft}.
        """
        raise NotImplementedError

    def _compliance_agent(self, state: JourneyState) -> dict:
        """
        TODO 3a: lint = BrandSafetyLinter.check(state["message"]). If
        lint["passed"], return {"lint_passed": True}. Otherwise return
        {"lint_passed": False, "violations": lint}. This node doesn't
        care whether state["message"] is the tiering agent's first draft
        or the repair agent's rewrite — it only ever looks at the
        current value.
        """
        raise NotImplementedError

    def _route_after_compliance(self, state: JourneyState) -> Literal["repair_agent", "send_agent", "blocked"]:
        """
        TODO 3b: If state.get("lint_passed"), return "send_agent". If
        state.get("repair_attempted") is already True (this is the SECOND
        time compliance has failed), return "blocked" — don't retry
        forever. Otherwise return "repair_agent".
        """
        raise NotImplementedError

    def _repair_agent(self, state: JourneyState) -> dict:
        """
        TODO 4: repaired_text = repair_message(state["message"],
        state["violations"]). Return {"message": repaired_text,
        "repaired": True, "repair_attempted": True} — this hands control
        back to compliance_agent (wired in _build_graph) to re-judge the
        rewritten draft.
        """
        raise NotImplementedError

    def _send_agent(self, state: JourneyState) -> dict:
        """
        TODO 5: customer, channel, segment_data = state["customer"],
        state["channel"], state["segment_data"]. Call
        self.memory.add_fact(customer["customer_id"], a fact string
        describing the offer sent (segment_data['discount_pct']) and
        channel). Return {"event": "sent", "cost_units":
        CATALOG["channel_tiers"][channel]["cost_units"]}.
        """
        raise NotImplementedError

    # ---------- Graph wiring (TODO) ----------

    def _build_graph(self):
        """
        TODO 6: Wire the StateGraph(JourneyState):
          - add_node for: "consent" (self._consent_node), "eligibility"
            (self._eligibility_node), "escalation_agent"
            (self._escalation_agent), "tiering_agent" (self._tiering_agent),
            "compliance_agent" (self._compliance_agent), "repair_agent"
            (self._repair_agent), "blocked_safety_node"
            (self._blocked_safety_node), "send_agent" (self._send_agent)
          - set_entry_point("consent")
          - add_conditional_edges("consent", self._route_after_consent,
            {"eligibility": "eligibility", "end": END})
          - add_conditional_edges("eligibility",
            self._route_after_eligibility, {"escalation_agent":
            "escalation_agent", "tiering_agent": "tiering_agent", "end": END})
          - add_edge("escalation_agent", END)
          - add_edge("tiering_agent", "compliance_agent")
          - add_conditional_edges("compliance_agent",
            self._route_after_compliance, {"repair_agent": "repair_agent",
            "send_agent": "send_agent", "blocked": "blocked_safety_node"})
          - add_edge("repair_agent", "compliance_agent")  <- the loop
          - add_edge("blocked_safety_node", END)
          - add_edge("send_agent", END)
          - return builder.compile()
        """
        raise NotImplementedError

    # ---------- Public API (given) ----------

    def run_customer(self, customer: dict, trigger_id: str, now: datetime) -> dict:
        result = self.graph.invoke({
            "customer": customer, "trigger_id": trigger_id, "now": now,
            "repaired": False, "repair_attempted": False,
        })
        entry = {"event": result["event"], "customer_id": customer["customer_id"], "timestamp": now.isoformat()}
        if result["event"] == "blocked_consent":
            entry["reason"] = result["reason"]
        elif result["event"] == "blocked_eligibility":
            entry.update({"channel": result.get("channel"), "reason": result["reason"]})
        elif result["event"] == "escalated":
            entry.update({
                "channel": result.get("channel"), "handoff_summary": result["handoff_summary"],
                "recommended_action": result["recommended_action"], "sentiment": result["sentiment"],
            })
        elif result["event"] == "blocked_safety":
            entry.update({"channel": result.get("channel"), "violations": result["violations"]})
        elif result["event"] == "sent":
            entry.update({
                "channel": result.get("channel"), "tier": result["tier"], "model_used": result["model_used"],
                "cost_units": result["cost_units"], "message": result["message"],
                "repaired": result.get("repaired", False),
            })
        self.analytics_log.append(entry)
        return entry

    def run_campaign(self, customers: list[dict], trigger_id: str, now: datetime) -> list[dict]:
        return [self.run_customer(customer, trigger_id, now) for customer in customers]


def demo_pm_recap():
    """Given — standalone, cheap rerun of one concept from each of
    H1/H2/H3, so this capstone is runnable with no dependency on those
    labs having run live first."""
    print("\n=== PM recap 1/3 — H1's quiet-hours eligibility check ===")
    ret02 = next(c for c in CUSTOMERS if c["customer_id"] == "RET-02")
    local_hour = (13 + ret02["timezone_offset_hours"]) % 24
    quiet = CATALOG["channel_tiers"]["sms"]["quiet_hours"]
    print(f"  RET-02 local hour at 13:00 dispatch = {local_hour}, sms quiet window = {quiet} -> "
          f"in_quiet_hours = {in_quiet_hours(local_hour, quiet)}")

    print("\n=== PM recap 2/3 — H2's locale persona routing ===")
    for locale in LOCALE_PERSONAS:
        persona = LanguageRouter.route(locale)
        print(f"  {locale}: {persona['language_name']} | {persona['tone']}")

    print("\n=== PM recap 3/3 — H3's brand-safety linter on an adversarial draft ===")
    bad = "This deal has no risk and everyone qualifies, guaranteed lowest price!"
    print(f"  Draft: \"{bad}\"")
    print(f"  Lint: {BrandSafetyLinter.check(bad)}")


if __name__ == "__main__":
    NOW = datetime(2026, 8, 3, 13, 0)
    agent = PersonalizedOutboundJourneyAgent()

    print("=== Campaign: win_back ===")
    results = agent.run_campaign(CUSTOMERS, "win_back", NOW)
    for entry in results:
        if entry["event"] == "sent":
            print(f"  {entry['customer_id']}: SENT via {entry['channel']} "
                  f"(tier={entry['tier']}, model={entry['model_used']}, repaired={entry['repaired']})")
            print(f"    \"{entry['message']}\"")
        elif entry["event"] == "escalated":
            print(f"  {entry['customer_id']}: ESCALATED — {entry['handoff_summary']}")
            print(f"    Recommended action: {entry['recommended_action']}")
        else:
            print(f"  {entry['customer_id']}: {entry['event']} — {entry.get('reason') or entry.get('violations')}")

    contacted = [c for c in CUSTOMERS if any(
        e["customer_id"] == c["customer_id"] and e["event"] == "sent" for e in agent.analytics_log
    )]
    uplift = agent.meter.measure_uplift("win_back", contacted)
    print(f"\nProactive value: contacted_rate={uplift['contacted_rate']} vs control_rate={uplift['control_rate']} "
          f"-> uplift={uplift['uplift_pp']}pp (n_contacted={uplift['contacted_n']})")

    print(f"\n=== Journey memory ===")
    for customer in CUSTOMERS:
        facts = agent.memory.get_facts(customer["customer_id"])
        if facts:
            print(f"  {customer['customer_id']}: {facts}")

    demo_pm_recap()
