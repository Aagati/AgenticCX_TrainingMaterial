"""
PM · H1 — Banking Idempotent, Audited Transactional Action (STARTER)
"""

import json
import uuid
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
    """
    TODO 1: Append {"timestamp": <ISO8601 UTC now>, "actor": actor,
    "action": action, "details": details, "result": result} to AUDIT_LOG.
    """
    raise NotImplementedError


def process_refund(transaction_id: str, amount: float, idempotency_key: str) -> dict:
    """
    TODO 2:
      1. If idempotency_key is already in PROCESSED_KEYS, call audit_log
         with action="process_refund_replay" and the STORED result, then
         return that stored result WITHOUT appending to REFUND_LEDGER again.
      2. Otherwise, append {"transaction_id":..., "amount":..., "idempotency_key":...}
         to REFUND_LEDGER, build a result dict {"status": "refunded",
         "transaction_id":..., "amount":...}, store it in
         PROCESSED_KEYS[idempotency_key], call audit_log with
         action="process_refund", and return the result.
    """
    raise NotImplementedError


def run_turn(messages: list) -> list:
    """
    TODO 3: Standard tool-use loop. When the model calls process_refund,
    execute it via process_refund(**tool_input) (actor for audit_log can
    just be "agent" — pass it through however you like) and feed the
    result back. Append the final assistant reply to `messages` and return it.
    """
    raise NotImplementedError


if __name__ == "__main__":
    convo = [{"role": "user", "content": "I was double-charged $45 for order #8821, please refund the duplicate charge."}]
    convo = run_turn(convo)
    print("AGENT:", convo[-1]["content"])

    # Simulate a network retry: same transaction, amount, AND idempotency
    # key as whatever the agent used above. For the demo, grab the key the
    # model actually used from PROCESSED_KEYS.
    if PROCESSED_KEYS:
        replay_key = next(iter(PROCESSED_KEYS))
        stored = PROCESSED_KEYS[replay_key]
        print("\n--- Simulating retry with same idempotency key ---")
        retry_result = process_refund(stored["transaction_id"], stored["amount"], replay_key)
        print("Retry result:", retry_result)

    print("\n[REFUND_LEDGER]:", json.dumps(REFUND_LEDGER, indent=2))
    print("\n[AUDIT_LOG]:", json.dumps(AUDIT_LOG, indent=2))
