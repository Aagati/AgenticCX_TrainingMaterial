"""
PM · H1 — Banking: Outbound & Proactive Orchestration (STARTER)

An outbound CAMPAIGN is not a chat turn — nobody asked the agent anything.
Something in the business (a due date, a fraud signal) fires a TRIGGER, and
the system has to decide, for every customer that trigger could apply to:
is this customer even allowed to be contacted right now (consent, quiet
hours, how recently we already reached them), and if so, how much attention
does this specific case deserve?

You'll build:
  1. EligibilityEngine.filter_eligible — the deterministic gate (no model
     call needed to check a timestamp or a boolean).
  2. classify_urgency — a CHEAP model (haiku) forced-tool call that decides
     "high" vs "low" urgency for each eligible customer.
  3. draft_message — a CAPABLE model (sonnet) call, only reached for "high".
  4. OutboundOrchestrator.run_campaign — wires eligibility -> tier ->
     draft/template -> log.
  5. ProactiveValueMeter.measure_uplift — simulates a contacted cohort
     against a control cohort to make "measuring proactive value" an
     actual computation.
"""

import json
import random
import sys
from datetime import datetime
from pathlib import Path
from typing import Literal

from anthropic import Anthropic
from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

MODEL_CHEAP = "claude-haiku-4-5-20251001"
MODEL_DRAFT = "claude-sonnet-5"

DATA_DIR = Path(__file__).parent
with open(DATA_DIR / "customer_profiles.json") as f:
    CUSTOMERS = json.load(f)
with open(DATA_DIR / "campaign_policies.json") as f:
    POLICIES = json.load(f)

client = Anthropic()


class UrgencyClassification(BaseModel):
    urgency: Literal["low", "high"] = Field(
        description="'high' if this case needs a bespoke, human-quality message; 'low' if a generic templated reminder is enough."
    )
    reason: str = Field(description="One short sentence justifying the bucket.")


def matches_trigger(customer: dict, rule: dict) -> bool:
    """Given — generic matcher over campaign_policies.json's trigger `match` block."""
    if "fraud_flag" in rule and customer["fraud_flag"] != rule["fraud_flag"]:
        return False
    if "days_until_payment_due_lte" in rule and not (
        customer["days_until_payment_due"] <= rule["days_until_payment_due_lte"]
    ):
        return False
    if "balance_lt" in rule and not (customer["balance"] < rule["balance_lt"]):
        return False
    return True


def in_quiet_hours(local_hour: int, window: list[int]) -> bool:
    """Given — window is [start, end] in the customer's local 24h clock; wraps
    midnight when start > end (e.g. [21, 8] means quiet from 9pm to 8am)."""
    start, end = window
    if start > end:
        return local_hour >= start or local_hour < end
    return start <= local_hour < end


class EligibilityEngine:
    @staticmethod
    def filter_eligible(customers: list[dict], trigger_id: str, now: datetime) -> list[dict]:
        """
        TODO 1: Return the subset of `customers` that pass ALL of:
          - matches_trigger(customer, rule) where rule =
            POLICIES["triggers"][trigger_id]["match"]
          - customer["consent"].get(channel, False) is True, where channel
            = customer["preferred_channel"]
          - customer["last_contacted_days_ago"] >= POLICIES["frequency_cap_days"]
          - NOT in_quiet_hours(local_hour, quiet_window), where local_hour =
            (now.hour + customer["timezone_offset_hours"]) % 24 and
            quiet_window = POLICIES["channel_tiers"][channel]["quiet_hours"]
        A customer failing any one check is excluded — order doesn't matter.
        """
        raise NotImplementedError


def classify_urgency(customer: dict, trigger_id: str) -> UrgencyClassification:
    """
    TODO 2: Make a real haiku call, forced tool use:
      - system prompt: explain this is a triage classifier for an outbound
        banking campaign, deciding "high" (needs a bespoke capable-model
        message) vs "low" (a generic template is enough); fraud alerts and
        low balance relative to an imminent due date should usually be "high"
      - user content: include the trigger's description
        (POLICIES["triggers"][trigger_id]["description"]) and the customer's
        fields (drop "consent" — not relevant to the classifier)
      - client.messages.create(model=MODEL_CHEAP, max_tokens=300,
        system=..., messages=[{"role": "user", "content": ...}],
        tools=[{"name": "classify", "description": ...,
        "input_schema": UrgencyClassification.model_json_schema()}],
        tool_choice={"type": "tool", "name": "classify"})
      - pull the tool_use block via next(b for b in response.content if
        b.type == "tool_use") and return UrgencyClassification(**tool_call.input)
    """
    raise NotImplementedError


def draft_message(customer: dict, trigger_id: str) -> str:
    """
    TODO 3: Make a real sonnet call — plain text, no tool forcing:
      - system prompt: write short, plain-language outbound banking
        messages, direct and warm, no preamble/signature, <=3 sentences
      - user content: trigger description + customer name/balance/days
        until due/fraud flag
      - client.messages.create(model=MODEL_DRAFT, max_tokens=200,
        system=..., messages=[{"role": "user", "content": ...}])
      - return next(b for b in response.content if b.type == "text").text.strip()
    """
    raise NotImplementedError


def template_message(customer: dict, trigger_id: str) -> str:
    """Given — the "low" urgency bucket's message. No model call at all:
    the whole point of tiering is that this path costs zero tokens."""
    first_name = customer["name"].split()[0]
    if trigger_id == "payment_due_soon":
        return (
            f"Hi {first_name}, your payment is due in {customer['days_until_payment_due']} "
            f"day(s) and your balance is ${customer['balance']:.2f}. Reply if you need help."
        )
    if trigger_id == "fraud_alert":
        return (
            f"Hi {first_name}, we noticed unusual activity on your account. "
            "Please call us to verify recent transactions."
        )
    return f"Hi {first_name}, please contact us regarding your account."


class OutboundOrchestrator:
    """Given — owns the analytics_log every dispatch appends a structured
    event to, so PM_H4's capstone (and any real analytics pipeline) has one
    consistent event schema to read from."""

    def __init__(self):
        self.analytics_log: list[dict] = []

    def run_campaign(self, trigger_id: str, now: datetime) -> list[dict]:
        """
        TODO 4: For each customer in EligibilityEngine.filter_eligible(
        CUSTOMERS, trigger_id, now):
          - classification = classify_urgency(customer, trigger_id)
          - channel = customer["preferred_channel"]
          - if classification.urgency == "high": message =
            draft_message(customer, trigger_id); model_used = MODEL_DRAFT
          - else: message = template_message(customer, trigger_id);
            model_used = "template"
          - build an event dict with keys: customer_id, trigger, channel,
            urgency, urgency_reason (classification.reason), model_used,
            cost_units (POLICIES["channel_tiers"][channel]["cost_units"]),
            timestamp (now.isoformat()), message
          - append it to self.analytics_log AND to a local `events` list
        Return `events`.
        """
        raise NotImplementedError


class ProactiveValueMeter:
    """Given — simulates a contacted cohort against a held-out control
    cohort using campaign_policies.json's baseline_conversion_rates, so
    "measuring proactive value" produces an actual number, not a slide."""

    def __init__(self, seed: int | None = 7):
        self.rng = random.Random(seed)

    def measure_uplift(self, trigger_id: str, contacted_customers: list[dict], control_size: int | None = None) -> dict:
        """
        TODO 5: rates = POLICIES["baseline_conversion_rates"][trigger_id].
        control_size defaults to max(len(contacted_customers), 1) if not
        given. Draw contacted_conversions by rolling
        self.rng.random() < rates["if_contacted"] once per contacted
        customer, and control_conversions by rolling
        self.rng.random() < rates["control"] once per control slot (a
        range(control_size) loop, no customer objects needed for the
        control group — it's a held-out comparison group, not real
        customers). Compute contacted_rate and control_rate (guard the
        divide-by-zero case), and return a dict with: trigger, contacted_n,
        control_n, contacted_conversions, control_conversions,
        contacted_rate (rounded 3dp), control_rate (rounded 3dp),
        uplift_pp (rounded 1dp, = (contacted_rate - control_rate) * 100).
        """
        raise NotImplementedError


if __name__ == "__main__":
    NOW = datetime(2026, 8, 3, 13, 0)  # fixed dispatch reference time, kept naive on purpose
    orchestrator = OutboundOrchestrator()
    meter = ProactiveValueMeter()

    for trigger_id in ("payment_due_soon", "fraud_alert"):
        print(f"\n=== Campaign: {trigger_id} ===")
        eligible_ids = [c["customer_id"] for c in EligibilityEngine.filter_eligible(CUSTOMERS, trigger_id, NOW)]
        print(f"Eligible: {eligible_ids or '(none)'}")

        events = orchestrator.run_campaign(trigger_id, NOW)
        for event in events:
            print(
                f"  -> {event['customer_id']} via {event['channel']} "
                f"(urgency={event['urgency']}, model={event['model_used']}, cost_units={event['cost_units']})"
            )
            print(f"     \"{event['message']}\"")

        contacted = [c for c in CUSTOMERS if c["customer_id"] in eligible_ids]
        uplift = meter.measure_uplift(trigger_id, contacted)
        print(
            f"  Proactive value: contacted_rate={uplift['contacted_rate']} "
            f"vs control_rate={uplift['control_rate']} -> uplift={uplift['uplift_pp']}pp "
            f"(n_contacted={uplift['contacted_n']}, n_control={uplift['control_n']})"
        )

    print(f"\n=== Analytics log ({len(orchestrator.analytics_log)} events) ===")
    for event in orchestrator.analytics_log:
        print(f"  {event['timestamp']} | {event['customer_id']} | {event['trigger']} | "
              f"{event['channel']} | {event['urgency']} | {event['model_used']} | cost={event['cost_units']}")
