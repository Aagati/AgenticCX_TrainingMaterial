"""
PM · H1 — Banking: Outbound & Proactive Orchestration.

An outbound CAMPAIGN is not a chat turn — nobody asked the agent anything.
Something in the business (a due date, a fraud signal) fires a TRIGGER, and
the system has to decide, for every customer that trigger could apply to:
is this customer even allowed to be contacted right now (consent, quiet
hours, how recently we already reached them), and if so, how much attention
does this specific case deserve (a $5.42 balance with a payment due
tomorrow is not the same case as $3,200 with 20 days to go)?

EligibilityEngine answers the first question deterministically — no model
call needed to check a timestamp or a boolean. classify_urgency() answers
the second question with a CHEAP model (haiku) making a real forced-tool
call, and only the "high" urgency bucket pays for a CAPABLE model
(draft_message(), sonnet) to write a bespoke message; everyone else gets a
templated reminder. That's cost-tiered routing applied jointly to CHANNEL
(sms/email are cheap async sends, voice is an expensive synchronous one)
and MODEL (haiku classifies, sonnet only drafts for the segment that earns
it) — the same "not every path needs the same capability" idea Day6's
PM_H2 applied to model choice alone, one level broader here.

ProactiveValueMeter then asks the question a stakeholder actually cares
about: did reaching out early change anything? It simulates a contacted
group against a held-out control group from the same baseline conversion
fixture and reports the observed uplift — "measuring proactive value" as
an actual computation over two simulated cohorts, not a hand-wavy claim.
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
        """Returns the subset of `customers` that are (a) matched by the
        trigger, (b) have given consent on their preferred channel, (c)
        weren't contacted more recently than campaign_policies.json's
        frequency_cap_days, and (d) aren't currently in that channel's
        quiet hours in their OWN timezone. Order of checks matters for
        readability, not correctness — a customer failing any one check
        is excluded."""
        rule = POLICIES["triggers"][trigger_id]["match"]
        freq_cap = POLICIES["frequency_cap_days"]
        eligible = []
        for customer in customers:
            if not matches_trigger(customer, rule):
                continue
            channel = customer["preferred_channel"]
            if not customer["consent"].get(channel, False):
                continue
            if customer["last_contacted_days_ago"] < freq_cap:
                continue
            local_hour = (now.hour + customer["timezone_offset_hours"]) % 24
            quiet_window = POLICIES["channel_tiers"][channel]["quiet_hours"]
            if in_quiet_hours(local_hour, quiet_window):
                continue
            eligible.append(customer)
        return eligible


def classify_urgency(customer: dict, trigger_id: str) -> UrgencyClassification:
    """Real haiku call, forced tool use — cheap enough to run on every
    eligible customer before deciding whether to pay for a draft."""
    trigger = POLICIES["triggers"][trigger_id]
    system = (
        "You are a triage classifier for an outbound banking campaign. Given a customer's "
        "account state and the campaign trigger that matched them, decide whether this case "
        "needs a personally-drafted message from a capable model (\"high\") or whether a "
        "generic templated reminder is sufficient (\"low\"). Fraud alerts and customers with "
        "a low balance relative to an imminent due date should usually be \"high\"."
    )
    user = (
        f"Trigger: {trigger['description']}\n"
        f"Customer: {json.dumps({k: v for k, v in customer.items() if k != 'consent'})}"
    )
    response = client.messages.create(
        model=MODEL_CHEAP,
        max_tokens=300,
        system=system,
        messages=[{"role": "user", "content": user}],
        tools=[{
            "name": "classify",
            "description": "Return the urgency classification for this outbound case.",
            "input_schema": UrgencyClassification.model_json_schema(),
        }],
        tool_choice={"type": "tool", "name": "classify"},
    )
    tool_call = next(b for b in response.content if b.type == "tool_use")
    return UrgencyClassification(**tool_call.input)


def draft_message(customer: dict, trigger_id: str) -> str:
    """Real sonnet call — only reached for the "high" urgency bucket."""
    trigger = POLICIES["triggers"][trigger_id]
    system = (
        "You write short, plain-language outbound banking messages. Be direct, warm, and "
        "specific to the customer's situation. No preamble, no signature block, no more than "
        "3 sentences."
    )
    user = (
        f"Trigger: {trigger['description']}\n"
        f"Customer name: {customer['name']}\n"
        f"Balance: ${customer['balance']:.2f}\n"
        f"Days until payment due: {customer['days_until_payment_due']}\n"
        f"Fraud flag: {customer['fraud_flag']}"
    )
    response = client.messages.create(
        model=MODEL_DRAFT, max_tokens=200, system=system, messages=[{"role": "user", "content": user}]
    )
    return next(b for b in response.content if b.type == "text").text.strip()


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
        """Eligibility -> tier -> draft/template -> simulated send -> log.
        Returns the list of events this run produced (also appended to
        self.analytics_log)."""
        eligible = EligibilityEngine.filter_eligible(CUSTOMERS, trigger_id, now)
        events = []
        for customer in eligible:
            classification = classify_urgency(customer, trigger_id)
            channel = customer["preferred_channel"]
            if classification.urgency == "high":
                message = draft_message(customer, trigger_id)
                model_used = MODEL_DRAFT
            else:
                message = template_message(customer, trigger_id)
                model_used = "template"
            event = {
                "customer_id": customer["customer_id"],
                "trigger": trigger_id,
                "channel": channel,
                "urgency": classification.urgency,
                "urgency_reason": classification.reason,
                "model_used": model_used,
                "cost_units": POLICIES["channel_tiers"][channel]["cost_units"],
                "timestamp": now.isoformat(),
                "message": message,
            }
            self.analytics_log.append(event)
            events.append(event)
        return events


class ProactiveValueMeter:
    """Given — simulates a contacted cohort against a held-out control
    cohort using campaign_policies.json's baseline_conversion_rates, so
    "measuring proactive value" produces an actual number, not a slide."""

    def __init__(self, seed: int | None = 7):
        self.rng = random.Random(seed)

    def measure_uplift(self, trigger_id: str, contacted_customers: list[dict], control_size: int | None = None) -> dict:
        rates = POLICIES["baseline_conversion_rates"][trigger_id]
        control_size = control_size or max(len(contacted_customers), 1)
        contacted_conversions = sum(1 for _ in contacted_customers if self.rng.random() < rates["if_contacted"])
        control_conversions = sum(1 for _ in range(control_size) if self.rng.random() < rates["control"])
        contacted_rate = contacted_conversions / len(contacted_customers) if contacted_customers else 0.0
        control_rate = control_conversions / control_size if control_size else 0.0
        return {
            "trigger": trigger_id,
            "contacted_n": len(contacted_customers),
            "control_n": control_size,
            "contacted_conversions": contacted_conversions,
            "control_conversions": control_conversions,
            "contacted_rate": round(contacted_rate, 3),
            "control_rate": round(control_rate, 3),
            "uplift_pp": round((contacted_rate - control_rate) * 100, 1),
        }


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

# Expected: payment_due_soon eligible = [CUST-001, CUST-005, CUST-010]
# (CUST-003 blocked by email quiet hours, CUST-007 blocked by no consent on
# any channel, CUST-009 blocked by sms quiet hours, CUST-004/CUST-006 don't
# match the trigger — due date too far out). fraud_alert eligible =
# [CUST-008] (CUST-002 blocked by frequency cap — contacted 1 day ago).
# CUST-001/005 have a due date and a balance that can't cover it — expect
# "high" and a real sonnet draft; CUST-010 has the same due date but a
# $5,000 balance — expect "low" and a zero-token template; classification
# is a REAL haiku call, so watch model_used in the analytics log rather
# than assuming the bucket, the model earns that call. Uplift numbers are
# drawn from campaign_policies.json's baseline rates with a fixed seed, so
# a given trigger's uplift is reproducible across runs.
