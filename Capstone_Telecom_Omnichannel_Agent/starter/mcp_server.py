# -*- coding: utf-8 -*-
"""
CAPSTONE - Telecom: Full MCP Server

See README.md for the full walkthrough. Summary of what's below:
  - get_account / list_charges  -> ownership-gated read tools, GIVEN complete
  - check_network_status        -> ungated read tool (public info), GIVEN
  - search_kb                   -> thin wrapper over retrieve() (TODO)
  - create_service_ticket       -> gate -> idempotent -> audit, GIVEN complete
                                    (the worked reference for the shape
                                    apply_billing_credit/change_plan follow)
  - apply_billing_credit /
    change_plan                 -> TODO, same gate->idempotent->audit shape
  - get_audit_log                -> read-only introspection, GIVEN

Setup:
    pip install mcp
    No API key needed - this process never calls an LLM.

Run directly (for manual inspection):
    python mcp_server.py
"""

import json
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from permissions import check_permission, redact_for_role, load_entitlements

mcp = FastMCP("northwind-telecom-agent")


def log(msg: str):
    # stdio transport uses stdout AS THE WIRE - diagnostics must go to
    # stderr only. A stray print() to stdout here would silently corrupt
    # every message the client tries to parse.
    print(f"[server] {msg}", file=sys.stderr, flush=True)


with open(Path(__file__).parent / "accounts.json") as f:
    _ACCOUNTS_DATA = json.load(f)

from knowledge_base import KB_DOCS  # noqa: E402  (after accounts.json load, before first use)

AUDIT_LOG: list[dict] = []
PROCESSED_KEYS: dict[str, dict] = {}
TICKET_STORE: dict[str, dict] = {}

PLAN_TIERS = {"PLAN-ESSENTIAL": 0, "PLAN-PLUS": 1, "PLAN-UNLIMITED": 2}

STOPWORDS = {
    "the", "is", "a", "an", "of", "to", "for", "my", "does", "do", "what",
    "how", "if", "and", "on", "in", "it", "am", "i", "while", "this",
    "that", "are", "can", "you", "me", "with", "or", "at", "be", "have",
}


def audit_log(action: str, actor: str, detail: dict) -> None:
    """Given: append-only audit trail. Called on EVERY path through a
    gated tool - allowed, denied, fresh, replayed, or conflicted - never
    only on success."""
    AUDIT_LOG.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "actor": actor,
        "detail": detail,
    })


def _tokenize(text: str) -> set[str]:
    words = re.findall(r"[a-z]+", text.lower())
    return {w for w in words if w not in STOPWORDS and len(w) > 2}


# TODO 3
def retrieve(query: str, k: int = 3) -> list[dict]:
    """Keyword/token-overlap retrieval over KB_DOCS - same Day1 approach
    (tokenize, set-intersect against each doc, sort desc, keep only
    score > 0), no embeddings/vector DB needed at this scale. This exact
    scoring function is what the bonus tier's RT-03 attacks by stuffing a
    malicious doc with high-frequency billing tokens.

    Steps:
      1. query_words = _tokenize(query).
      2. For each doc in KB_DOCS, doc_words = _tokenize(doc["title"] + " " + doc["text"]);
         score = len(query_words & doc_words) (set intersection size).
      3. Sort (score, doc) pairs descending by score.
      4. Return the top k docs, but ONLY those with score > 0 - a
         zero-overlap query must return an empty list, not a "closest
         guess." This is what forces the specialist to say "I don't
         have that information" instead of hallucinating.
    """
    raise NotImplementedError("TODO: implement retrieve()")


@mcp.tool()
def get_account(account_id: str, customer_id: str, agent_role: str) -> dict:
    """Look up an account record. Ownership-gated (the customer must own
    the account) and field-redacted for the calling role.

    Args:
        account_id: The account to look up.
        customer_id: The authenticated customer this call is on behalf of.
        agent_role: Which specialist role is making this call.
    """
    allowed, reason = check_permission(customer_id, account_id, agent_role, "get_account")
    if not allowed:
        audit_log("get_account_denied", agent_role, {"account_id": account_id, "reason": reason})
        return {"error": reason}
    record = _ACCOUNTS_DATA["accounts"][account_id]
    return redact_for_role(record, agent_role)


@mcp.tool()
def list_charges(account_id: str, customer_id: str, agent_role: str) -> list[dict]:
    """Return recent charges on an account. Ownership-gated.

    Args:
        account_id: The account to list charges for.
        customer_id: The authenticated customer this call is on behalf of.
        agent_role: Which specialist role is making this call.
    """
    allowed, reason = check_permission(customer_id, account_id, agent_role, "list_charges")
    if not allowed:
        audit_log("list_charges_denied", agent_role, {"account_id": account_id, "reason": reason})
        return [{"error": reason}]
    return [
        {"date": "2026-07-01", "description": "Monthly plan charge", "amount_cents": 3000},
        {"date": "2026-06-28", "description": "International roaming - duplicate charge", "amount_cents": 1200},
        {"date": "2026-06-15", "description": "Data overage", "amount_cents": 1000},
    ]


@mcp.tool()
def check_network_status(area_code: str) -> dict:
    """Check for known network outages in an area code. Deliberately NOT
    ownership-gated - network status is public information, unlike a
    customer's own account or billing data.

    Args:
        area_code: The area code to check.
    """
    known_outages = {"415": "Degraded service reported in this area, ETA 2 hours."}
    return {"area_code": area_code, "status": known_outages.get(area_code, "No known issues.")}


@mcp.tool()
def search_kb(query: str) -> list[dict]:
    """Search the Northwind Telecom knowledge base and return matching
    policy/support docs.

    Args:
        query: The customer's question, in their own words.
    """
    return retrieve(query, k=3)


# TODO 4
def _idempotent(tool_name: str, idempotency_key: str, args: dict, compute) -> dict:
    """Three-branch idempotency core, extending Day4 PM_H1's
    single-branch PROCESSED_KEYS check with real 409-conflict semantics.

    Steps:
      1. key = f"{tool_name}:{idempotency_key}".
      2. If key is already in PROCESSED_KEYS:
         a. stored = PROCESSED_KEYS[key]. If stored["args"] == args
            (the SAME request retried): audit_log(f"{tool_name}_replay",
            "agent", {"idempotency_key": ..., "args": ...}) and return
            stored["result"] verbatim - NO re-mutation.
         b. Otherwise (a DIFFERENT request reusing the same key):
            build result = {"status": "conflict", "reason": "idempotency_key
            reused with different arguments"}; audit_log(f"{tool_name}_conflict",
            "agent", {"idempotency_key": ..., "args": ..., "stored_args": stored["args"]});
            return result. Still no mutation.
      3. Otherwise (key never seen): result = compute(); store
         PROCESSED_KEYS[key] = {"args": args, "result": result};
         audit_log(tool_name, "agent", {"idempotency_key": ..., "args": ..., "result": result});
         return result.

    PROCESSED_KEYS lives in this server process, never the client/agent
    process - a network retry re-invokes the external system, not
    whichever agent process happened to be running (the same anti-pattern
    Day4's PM_H1 warns about).
    """
    raise NotImplementedError("TODO: implement _idempotent()")


@mcp.tool()
def create_service_ticket(account_id: str, customer_id: str, agent_role: str,
                           issue_description: str, priority: str, idempotency_key: str) -> dict:
    """Create a network service ticket. Idempotent: calling this twice
    with the same idempotency_key returns the identical result without
    creating a second ticket. GIVEN COMPLETE - this is the worked
    reference for the gate -> idempotent -> audit composition that
    apply_billing_credit and change_plan below must follow.

    Args:
        account_id: The account the ticket is for.
        customer_id: The authenticated customer this call is on behalf of.
        agent_role: Which specialist role is making this call.
        issue_description: What the customer reported.
        priority: One of "P1", "P2", "P3" - see the ticket priority matrix.
        idempotency_key: Caller-generated key; same key on retry returns
            the same result instead of creating a duplicate ticket.
    """
    allowed, reason = check_permission(customer_id, account_id, agent_role, "create_service_ticket")
    if not allowed:
        audit_log("create_service_ticket_denied", agent_role, {"account_id": account_id, "reason": reason})
        return {"error": reason}

    args = {"account_id": account_id, "issue_description": issue_description, "priority": priority}

    def compute():
        ticket_id = f"TCK-{uuid.uuid4().hex[:6].upper()}"
        TICKET_STORE[ticket_id] = {**args, "status": "open"}
        return {"ticket_id": ticket_id, "status": "open"}

    result = _idempotent("create_service_ticket", idempotency_key, args, compute)
    log(f"create_service_ticket -> {result}")
    return result


# TODO 5
@mcp.tool()
def apply_billing_credit(account_id: str, customer_id: str, agent_role: str,
                          amount_cents: int, reason: str, idempotency_key: str) -> dict:
    """Apply a goodwill billing credit to an account. Same shape as
    create_service_ticket above: gate -> idempotent -> audit.

    Args:
        account_id: The account to credit.
        customer_id: The authenticated customer this call is on behalf of.
        agent_role: Which specialist role is making this call.
        amount_cents: The credit amount in cents.
        reason: Why the credit is being issued (required, never a placeholder).
        idempotency_key: Caller-generated key; same key on retry returns
            the same result instead of crediting twice.

    Steps:
      1. allowed, deny_reason = check_permission(customer_id, account_id,
         agent_role, "apply_billing_credit", amount_cents=amount_cents).
         If not allowed: audit_log("apply_billing_credit_denied", agent_role,
         {...}) and return {"error": deny_reason}.
      2. Build args = {"account_id", "amount_cents", "reason"}.
      3. Define compute(): looks up the account in
         _ACCOUNTS_DATA["accounts"][account_id], subtracts amount_cents
         from its balance_cents (a credit reduces what the customer
         owes), and returns {"status": "applied", "credit_id": f"CR-{uuid.uuid4().hex[:6].upper()}",
         "new_balance_cents": <the updated balance>}.
      4. result = _idempotent("apply_billing_credit", idempotency_key, args, compute).
      5. log(f"apply_billing_credit -> {result}"); return result.
    """
    raise NotImplementedError("TODO: implement apply_billing_credit()")


# TODO 6
@mcp.tool()
def change_plan(account_id: str, customer_id: str, agent_role: str,
                 new_plan_id: str, idempotency_key: str) -> dict:
    """Change an account's plan. Gated by check_permission, then a
    contract-aware business rule (an in-contract downgrade is refused
    unless the role has can_override_contract), then idempotent, then
    audited.

    Args:
        account_id: The account to change.
        customer_id: The authenticated customer this call is on behalf of.
        agent_role: Which specialist role is making this call.
        new_plan_id: One of "PLAN-ESSENTIAL", "PLAN-PLUS", "PLAN-UNLIMITED".
        idempotency_key: Caller-generated key; same key on retry returns
            the same result instead of changing the plan twice.

    Steps:
      1. allowed, deny_reason = check_permission(customer_id, account_id,
         agent_role, "change_plan"). If not allowed: audit_log(...) and
         return {"error": deny_reason}.
      2. account = _ACCOUNTS_DATA["accounts"][account_id].
      3. is_downgrade = PLAN_TIERS.get(new_plan_id, 0) < PLAN_TIERS.get(account["plan_id"], 0)
         (PLAN_TIERS is given above: ESSENTIAL=0, PLUS=1, UNLIMITED=2).
      4. can_override = load_entitlements().get(agent_role, {}).get("limits", {}).get("can_override_contract", False).
      5. If is_downgrade AND account.get("contract_end") AND not can_override:
         audit_log("change_plan_denied", agent_role, {..., "reason": "in_contract_downgrade_requires_override"})
         and return {"error": "in_contract_downgrade_requires_override"}.
      6. Build args = {"account_id", "new_plan_id"}.
      7. Define compute(): sets account["plan_id"] = new_plan_id and
         returns {"status": "applied", "account_id": account_id, "new_plan_id": new_plan_id}.
      8. result = _idempotent("change_plan", idempotency_key, args, compute).
      9. log(f"change_plan -> {result}"); return result.
    """
    raise NotImplementedError("TODO: implement change_plan()")


@mcp.tool()
def get_audit_log() -> list[dict]:
    """Return the full audit trail - every gated tool call, allowed or
    denied, fresh, replayed, or conflicted, each attributed and
    timestamped."""
    return AUDIT_LOG


if __name__ == "__main__":
    log("northwind-telecom-agent MCP server starting - stdio transport, waiting for a client to connect...")
    log("(this will sit here silently until a client sends it something over stdin - that's normal, not a hang)")
    mcp.run(transport="stdio")
    log("server stopped")

# Expected standalone checks:
#   apply_billing_credit("ACC-5001", "cust_1001", "billing_agent", 1200, "x", "k1") -> applied
#   apply_billing_credit("ACC-5001", "cust_1001", "billing_agent", 1200, "x", "k1") again -> IDENTICAL result, AUDIT_LOG grows by one "_replay" entry, balance unchanged
#   apply_billing_credit("ACC-5001", "cust_1001", "billing_agent", 900, "x", "k1")  -> {"status": "conflict", ...}, balance unchanged
#   apply_billing_credit("ACC-5001", "cust_1001", "tech_agent", 1200, "x", "k2")    -> {"error": "tool_not_allowed_for_role"}
