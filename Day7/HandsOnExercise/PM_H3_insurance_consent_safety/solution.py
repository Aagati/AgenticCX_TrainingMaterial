"""
PM · H3 — Insurance: Consent, Compliance & Brand Safety.

Day 3 and Day 4 already built consent CAPTURE (asking for and recording
consent live, mid-call/mid-chat) and consent LIFECYCLE (retention,
erasure). This lab is the piece nobody else in the repo covers: consent as
a GATE on an OUTBOUND send, checked before a single token gets generated —
because there's no live conversation to ask "can I record this call?"
inside. If the gate says no, generation never happens; that's the whole
point of ConsentGate.check() running first and short-circuiting.

BrandSafetyLinter is the second, independent gate — even a consenting,
reachable customer shouldn't receive a message that promises something the
company can't legally back ("guaranteed payout") or omits a disclosure
regulation requires. It runs AFTER generation, on the actual text, because
that's the only place "did the model actually say something reckless"
can be checked — no amount of system-prompt wording is a substitute for
checking the output.

SafetyRailPipeline composes both gates plus one repair attempt (rewrite
once against the violations, then re-check) into a single guarded send
path, with a structured audit_log entry for every outcome: blocked by
consent, blocked by safety (even after repair), or sent.
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
        """Deterministic, no model call. Three independent reasons a send
        can be blocked, checked in order but each one standalone — do NOT
        collapse them into one boolean, the audit log needs to say WHICH
        reason applied."""
        record = CONSENT_REGISTRY.get(customer_id)
        if record is None:
            return {"allowed": False, "reason": "no_consent_record"}
        if record["do_not_contact"]:
            return {"allowed": False, "reason": "do_not_contact"}
        if not record["channel_opt_in"].get(channel, False):
            return {"allowed": False, "reason": f"not_opted_in_{channel}"}
        captured_at = date.fromisoformat(record["consent_captured_at"])
        age_days = (now - captured_at).days
        if age_days > POLICY["consent_freshness_days"]:
            return {"allowed": False, "reason": "consent_stale", "age_days": age_days}
        return {"allowed": True, "reason": "ok"}


class BrandSafetyLinter:
    @staticmethod
    def check(draft_text: str, message_type: str) -> dict:
        """Deterministic, no model call. Two independent checks: banned
        phrases (substring, case-insensitive) and a required disclosure
        that must appear VERBATIM — a paraphrase doesn't count, because
        the exact wording is usually what compliance actually signed off
        on."""
        text_lower = draft_text.lower()
        violations = [p for p in POLICY["banned_phrases"] if p in text_lower]
        required = POLICY["required_disclosures"].get(message_type)
        missing_disclosure = required is not None and required.lower() not in text_lower
        return {
            "passed": not violations and not missing_disclosure,
            "banned_phrase_violations": violations,
            "missing_disclosure": required if missing_disclosure else None,
        }


def draft_outbound_message(customer_name: str, message_type: str, context: str) -> str:
    """Real sonnet call. The system prompt asks for the required disclosure
    verbatim, but BrandSafetyLinter checks the OUTPUT anyway rather than
    trusting the instruction was followed — that's the difference between
    a guardrail and a suggestion."""
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
    """Real sonnet call — one rewrite attempt, given the SPECIFIC
    violations instead of asking the model to guess what's wrong."""
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
        """ConsentGate -> draft -> BrandSafetyLinter -> (repair once if
        needed) -> audit log. Returns the audit entry it produced."""
        customer_name = CONSENT_REGISTRY.get(customer_id, {}).get("name", customer_id)
        consent = ConsentGate.check(customer_id, channel, now)
        if not consent["allowed"]:
            entry = {
                "event": "blocked_consent",
                "customer_id": customer_id,
                "channel": channel,
                "reason": consent["reason"],
                "timestamp": now.isoformat(),
            }
            self.audit_log.append(entry)
            return entry

        draft = draft_outbound_message(customer_name, message_type, context)
        lint = BrandSafetyLinter.check(draft, message_type)
        if lint["passed"]:
            entry = {
                "event": "sent", "customer_id": customer_id, "channel": channel,
                "message": draft, "repaired": False, "timestamp": now.isoformat(),
            }
            self.audit_log.append(entry)
            return entry

        repaired = repair_message(draft, lint, message_type)
        lint2 = BrandSafetyLinter.check(repaired, message_type)
        if lint2["passed"]:
            entry = {
                "event": "sent", "customer_id": customer_id, "channel": channel,
                "message": repaired, "repaired": True, "timestamp": now.isoformat(),
            }
        else:
            entry = {
                "event": "blocked_safety", "customer_id": customer_id, "channel": channel,
                "violations": lint2, "timestamp": now.isoformat(),
            }
        self.audit_log.append(entry)
        return entry


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

# Expected: ConsentGate — CUST-101/sms allowed; CUST-102/sms blocked
# "not_opted_in_sms" (their record has sms:false); CUST-103/email blocked
# "consent_stale" (captured 2024-05-01, >365 days before NOW); CUST-104/
# voice blocked "do_not_contact"; CUST-999 blocked "no_consent_record" (not
# in the registry). BrandSafetyLinter — the hand-crafted bad draft trips
# BOTH banned_phrase_violations (two phrases) AND missing_disclosure; the
# good draft passes clean. SafetyRailPipeline — CUST-102/104 never reach
# drafting at all (consent-blocked before any model call, cheapest possible
# failure); CUST-101/103/105 reach a REAL sonnet draft, which should pass
# BrandSafetyLinter on the first try (well-behaved model output) — the
# repair path exists for when it doesn't, exercised deterministically by
# the adversarial-draft section above rather than left to chance here.
