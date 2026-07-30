"""
PM · H1 — Banking Idempotent, Audited Transactional Action (REFERENCE SOLUTION)
"""

import json
from datetime import datetime, timezone
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

client = Anthropic()
MODEL = "claude-sonnet-5"

REFUND_LEDGER = []
PROCESSED_KEYS = {}
AUDIT_LOG = []

PROCESS_REFUND_TOOL = {
    "name": "process_refund",
    "description": "Process a refund for a transaction. Requires an idempotency key.",
    "input_schema": {
        "type": "object",
        "properties": {
            "transaction_id": {"type": "string"},
            "amount": {"type": "number"},
            "idempotency_key": {"type": "string"},
        },
        "required": ["transaction_id", "amount", "idempotency_key"],
    },
}


def audit_log(actor: str, action: str, details: dict, result: dict):
    AUDIT_LOG.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "actor": actor,
        "action": action,
        "details": details,
        "result": result,
    })


def process_refund(transaction_id: str, amount: float, idempotency_key: str) -> dict:
    if idempotency_key in PROCESSED_KEYS:
        stored_result = PROCESSED_KEYS[idempotency_key]
        audit_log("agent", "process_refund_replay",
                   {"transaction_id": transaction_id, "amount": amount, "idempotency_key": idempotency_key},
                   stored_result)
        return stored_result

    REFUND_LEDGER.append({"transaction_id": transaction_id, "amount": amount, "idempotency_key": idempotency_key})
    result = {"status": "refunded", "transaction_id": transaction_id, "amount": amount}
    PROCESSED_KEYS[idempotency_key] = result
    audit_log("agent", "process_refund",
              {"transaction_id": transaction_id, "amount": amount, "idempotency_key": idempotency_key},
              result)
    return result


SYSTEM_PROMPT = """You are a banking support agent. When a customer
requests a refund, use process_refund with a fresh, unique idempotency_key
you generate yourself (e.g. a random-looking string) for this specific
customer request."""


def run_turn(messages: list) -> list:
    response = client.messages.create(
        model=MODEL, max_tokens=300, system=SYSTEM_PROMPT,
        tools=[PROCESS_REFUND_TOOL], messages=messages,
    )
    tool_use = next((b for b in response.content if b.type == "tool_use"), None)
    if tool_use is None:
        text = next(b.text for b in response.content if b.type == "text")
        messages.append({"role": "assistant", "content": text})
        return messages

    result = process_refund(**tool_use.input)

    messages.append({"role": "assistant", "content": response.content})
    messages.append({"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": tool_use.id, "content": json.dumps(result)}
    ]})
    followup = client.messages.create(
        model=MODEL, max_tokens=300, system=SYSTEM_PROMPT,
        tools=[PROCESS_REFUND_TOOL], messages=messages,
    )
    text = next(b.text for b in followup.content if b.type == "text")
    messages.append({"role": "assistant", "content": text})
    return messages


if __name__ == "__main__":
    convo = [{"role": "user", "content": "I was double-charged $45 for order #8821, please refund the duplicate charge."}]
    convo = run_turn(convo)
    print("AGENT:", convo[-1]["content"])

    if PROCESSED_KEYS:
        replay_key = next(iter(PROCESSED_KEYS))
        stored = PROCESSED_KEYS[replay_key]
        print("\n--- Simulating retry with same idempotency key ---")
        retry_result = process_refund(stored["transaction_id"], stored["amount"], replay_key)
        print("Retry result:", retry_result)

    print("\n[REFUND_LEDGER]:", json.dumps(REFUND_LEDGER, indent=2))
    print("\n[AUDIT_LOG]:", json.dumps(AUDIT_LOG, indent=2))

# Expected: REFUND_LEDGER has exactly ONE entry even though process_refund
# was called twice. AUDIT_LOG has TWO entries: "process_refund" then
# "process_refund_replay" — both timestamped and attributed, giving a full
# record of both the original action and the duplicate attempt.
