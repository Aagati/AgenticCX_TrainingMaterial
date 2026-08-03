"""
PM · H3 — Insurance: Consent, Compliance & Brand Safety (STARTER)

Consent as a GATE on an OUTBOUND send, checked before a single token gets
generated — there's no live conversation to ask "can I record this call?"
inside, so the check has to run first and short-circuit generation
entirely when it fails.

BrandSafetyLinter is a second, independent gate that runs AFTER
generation, on the actual output text — no amount of system-prompt
wording is a substitute for checking what the model actually said.

You'll build:
  1. ConsentGate.check — deterministic, three independent block reasons.
  2. BrandSafetyLinter.check — deterministic, two independent checks.
  3. SafetyRailPipeline.send — composes both gates + one repair attempt
     into a single guarded send path with a structured audit log.
"""

import json
import sys
from datetime import date
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

MODEL = "claude-sonnet-5"

DATA_DIR = Path(__file__).parent
with open(DATA_DIR / "consent_registry.json") as f:
    CONSENT_REGISTRY = json.load(f)
with open(DATA_DIR / "brand_safety_policy.json") as f:
    POLICY = json.load(f)

client = Anthropic()


class ConsentGate:
    @staticmethod
    def check(customer_id: str, channel: str, now: date) -> dict:
        """
        TODO 1: Look up record = CONSENT_REGISTRY.get(customer_id).
          - If record is None, return {"allowed": False, "reason": "no_consent_record"}
          - If record["do_not_contact"] is True, return
            {"allowed": False, "reason": "do_not_contact"}
          - If not record["channel_opt_in"].get(channel, False), return
            {"allowed": False, "reason": f"not_opted_in_{channel}"}
          - Otherwise, compute age_days = (now -
            date.fromisoformat(record["consent_captured_at"])).days. If
            age_days > POLICY["consent_freshness_days"], return
            {"allowed": False, "reason": "consent_stale", "age_days": age_days}
          - Otherwise return {"allowed": True, "reason": "ok"}
        Check each condition independently — don't collapse them into one
        boolean, the audit log needs to say WHICH reason applied.
        """
        raise NotImplementedError


class BrandSafetyLinter:
    @staticmethod
    def check(draft_text: str, message_type: str) -> dict:
        """
        TODO 2: text_lower = draft_text.lower(). violations = the subset of
        POLICY["banned_phrases"] that appear as a substring of text_lower.
        required = POLICY["required_disclosures"].get(message_type) (may
        be None if this message_type has no required disclosure).
        missing_disclosure = required is not None AND required.lower() not
        in text_lower — a paraphrase doesn't count, it must appear
        verbatim. Return {"passed": not violations and not
        missing_disclosure, "banned_phrase_violations": violations,
        "missing_disclosure": required if missing_disclosure else None}.
        """
        raise NotImplementedError


def draft_outbound_message(customer_name: str, message_type: str, context: str) -> str:
    """Given — real sonnet call. Note BrandSafetyLinter checks the OUTPUT
    anyway even though this prompt asks for the disclosure verbatim — a
    guardrail checks results, an instruction is just a suggestion."""
    required = POLICY["required_disclosures"].get(message_type)
    system = (
        "You write short outbound insurance messages. Be clear and warm. Never use absolute "
        "guarantee language (e.g. claiming something is guaranteed, risk-free, or automatically "
        "approved) — insurance outcomes always depend on policy terms. "
        + (f"You MUST include this exact disclosure sentence verbatim, unmodified, as the final "
           f"sentence: \"{required}\"" if required else "")
    )
    user = f"Message type: {message_type}\nCustomer: {customer_name}\nContext: {context}"
    response = client.messages.create(
        model=MODEL, max_tokens=300, system=system, messages=[{"role": "user", "content": user}]
    )
    return next(b for b in response.content if b.type == "text").text.strip()


def repair_message(draft_text: str, lint_result: dict, message_type: str) -> str:
    """Given — one rewrite attempt, given the SPECIFIC violations instead
    of asking the model to guess what's wrong."""
    required = POLICY["required_disclosures"].get(message_type)
    system = "You rewrite outbound insurance messages to fix specific compliance problems, keeping the rest of the message's intent intact."
    problems = []
    if lint_result["banned_phrase_violations"]:
        problems.append(f"Remove/rephrase these banned phrases: {lint_result['banned_phrase_violations']}")
    if lint_result["missing_disclosure"]:
        problems.append(f"Add this exact disclosure sentence verbatim: \"{lint_result['missing_disclosure']}\"")
    user = f"Original message: {draft_text}\n\nProblems to fix:\n" + "\n".join(problems)
    response = client.messages.create(
        model=MODEL, max_tokens=300, system=system, messages=[{"role": "user", "content": user}]
    )
    return next(b for b in response.content if b.type == "text").text.strip()


class SafetyRailPipeline:
    def __init__(self):
        self.audit_log: list[dict] = []

    def send(self, customer_id: str, channel: str, message_type: str, context: str, now: date) -> dict:
        """
        TODO 3: customer_name = CONSENT_REGISTRY.get(customer_id, {}).get(
        "name", customer_id). consent = ConsentGate.check(customer_id,
        channel, now). If not consent["allowed"], build an entry dict
        {"event": "blocked_consent", "customer_id": customer_id,
        "channel": channel, "reason": consent["reason"], "timestamp":
        now.isoformat()}, append it to self.audit_log, and return it
        immediately — do NOT call draft_outbound_message.

        Otherwise: draft = draft_outbound_message(customer_name,
        message_type, context). lint = BrandSafetyLinter.check(draft,
        message_type). If lint["passed"], build a "sent" entry with
        message=draft, repaired=False. Otherwise: repaired =
        repair_message(draft, lint, message_type); lint2 =
        BrandSafetyLinter.check(repaired, message_type); if lint2["passed"]
        build a "sent" entry with message=repaired, repaired=True;
        otherwise build a "blocked_safety" entry with
        violations=lint2. Every entry needs customer_id, channel, and
        timestamp=now.isoformat(). Append the final entry to
        self.audit_log and return it.
        """
        raise NotImplementedError


if __name__ == "__main__":
    NOW = date(2026, 8, 3)

    print("=== ConsentGate — one case per block reason ===")
    for customer_id, channel in [
        ("CUST-101", "sms"),      # fresh consent, opted in -> allowed
        ("CUST-102", "sms"),      # opted out of sms specifically
        ("CUST-103", "email"),    # consent captured 2024-05-01 -> stale
        ("CUST-104", "voice"),    # do_not_contact
        ("CUST-999", "sms"),      # not in the registry at all
    ]:
        result = ConsentGate.check(customer_id, channel, NOW)
        print(f"  {customer_id} via {channel}: {result}")

    print("\n=== BrandSafetyLinter — hand-crafted adversarial drafts (not model output) ===")
    bad_draft = "Great news — your renewal comes with a guaranteed payout, no questions asked!"
    print(f"  Draft: \"{bad_draft}\"")
    print(f"  Lint: {BrandSafetyLinter.check(bad_draft, 'renewal_reminder')}")

    good_draft = (
        "Your policy renews next month at the same rate. Coverage details are subject to your "
        "policy terms and conditions."
    )
    print(f"  Draft: \"{good_draft}\"")
    print(f"  Lint: {BrandSafetyLinter.check(good_draft, 'renewal_reminder')}")

    print("\n=== SafetyRailPipeline — end to end, real drafting model ===")
    pipeline = SafetyRailPipeline()
    cases = [
        ("CUST-101", "sms", "renewal_reminder", "Auto policy renews in 14 days, same coverage and rate."),
        ("CUST-102", "sms", "claim_status_update", "Water damage claim #4471 is under review."),
        ("CUST-103", "email", "renewal_reminder", "Home policy renews in 30 days."),
        ("CUST-104", "voice", "claim_status_update", "Auto claim #5522 approved for partial payout."),
        ("CUST-105", "email", "claim_status_update", "Claim #6100 needs an additional document."),
    ]
    for customer_id, channel, message_type, context in cases:
        entry = pipeline.send(customer_id, channel, message_type, context, NOW)
        print(f"  {customer_id} via {channel} ({message_type}): {entry['event']}"
              + (f" — {entry.get('reason') or entry.get('violations')}" if entry["event"] != "sent" else ""))
        if entry["event"] == "sent":
            print(f"    \"{entry['message']}\" (repaired={entry['repaired']})")

    print(f"\n=== Audit log ({len(pipeline.audit_log)} entries) ===")
    for entry in pipeline.audit_log:
        print(f"  {entry['timestamp']} | {entry['customer_id']} | {entry['event']}")
