# -*- coding: utf-8 -*-
"""
Part 2 - Permissions & Entitlements (REFERENCE SOLUTION)

Extends Day4 AM_H3_retail_permissions's one-dimensional ownership check to
TWO dimensions:
  (A) does the customer own the account (accounts.json)
  (B) does the CALLING SPECIALIST'S ROLE have the capability for this tool,
      and is it within the role's amount limit (entitlements.json)

tech_agent calling apply_billing_credit is denied even when the customer
owns the account - that's what makes multi-agent + permissions load-bearing
together, and it's the structural defense against a confused-deputy
handoff attack (see malicious_kb_docs.json's MAL-01).

Check order matters, same contract as AM_H3: ownership is verified before
capability, so a request that would fail both always reports the
ownership failure first.
"""

import json
from pathlib import Path

DATA_DIR = Path(__file__).parent

with open(DATA_DIR / "accounts.json") as f:
    _ACCOUNTS_DATA = json.load(f)

with open(DATA_DIR / "entitlements.json") as f:
    _ENTITLEMENTS_DATA = json.load(f)


def load_entitlements() -> dict:
    """Given: returns the parsed agent_roles entitlement map."""
    return _ENTITLEMENTS_DATA["agent_roles"]


def check_permission(customer_id: str, account_id: str, agent_role: str,
                      tool_name: str, amount_cents: int | None = None) -> tuple[bool, str]:
    """Two-dimensional entitlement gate. Five sequential checks, in order:

      1. customer_id must be a known customer -> else "unknown_customer"
      2. account_id must exist and belong to customer_id -> else "not_owner"
         (checked BEFORE role capability, same as AM_H3 - ownership always
         fails first even when the role would also have failed)
      3. agent_role must be a known role -> else "unknown_role"
      4. tool_name must be in that role's allowed_tools -> else
         "tool_not_allowed_for_role"
      5. if amount_cents is given and the role has a max_credit_cents
         limit, amount_cents must not EXCEED it (equal to the limit is
         allowed) -> else "limit_exceeded"

    Returns (True, "allowed") only if every check passes.
    """
    if customer_id not in _ACCOUNTS_DATA["customers"]:
        return False, "unknown_customer"

    account = _ACCOUNTS_DATA["accounts"].get(account_id)
    if account is None or account["customer_id"] != customer_id:
        return False, "not_owner"

    roles = load_entitlements()
    role = roles.get(agent_role)
    if role is None:
        return False, "unknown_role"

    if tool_name not in role["allowed_tools"]:
        return False, "tool_not_allowed_for_role"

    max_credit = role.get("limits", {}).get("max_credit_cents")
    if amount_cents is not None and max_credit is not None and amount_cents > max_credit:
        return False, "limit_exceeded"

    return True, "allowed"


def redact_for_role(account_record: dict, agent_role: str) -> dict:
    """Field-level minimization: return a copy of account_record with
    fields the calling role has no business seeing removed.

      - tech_agent never sees balance_cents or payment_method_last4
        (billing data, irrelevant to network troubleshooting)
      - billing_agent never sees sim_iccid (SIM/device data, irrelevant
        to billing)
      - plans_agent and billing_agent both need contract_end (contract
        terms feed plan-change and credit decisions); tech_agent does not
        and does not see it either

    Every role keeps customer_id and plan_id - both are needed by all
    three specialists for routine lookups.
    """
    record = dict(account_record)
    if agent_role == "tech_agent":
        record.pop("balance_cents", None)
        record.pop("payment_method_last4", None)
        record.pop("contract_end", None)
    elif agent_role == "billing_agent":
        record.pop("sim_iccid", None)
    elif agent_role == "plans_agent":
        record.pop("sim_iccid", None)
        record.pop("payment_method_last4", None)
    return record


if __name__ == "__main__":
    print(check_permission("cust_1001", "ACC-5001", "billing_agent", "apply_billing_credit", 2000))
    print(check_permission("cust_2002", "ACC-5001", "billing_agent", "apply_billing_credit", 2000))
    print(check_permission("cust_1001", "ACC-5001", "tech_agent", "apply_billing_credit", 2000))
    print(check_permission("cust_1001", "ACC-5001", "billing_agent", "apply_billing_credit", 999999))
    print(redact_for_role(_ACCOUNTS_DATA["accounts"]["ACC-5001"], "tech_agent"))

# Expected:
#   cust_1001/ACC-5001/billing_agent, $20 -> (True, "allowed")
#   cust_2002/ACC-5001/billing_agent, $20 -> (False, "not_owner") - cust_2002 owns ACC-5002, not ACC-5001
#   cust_1001/ACC-5001/tech_agent, $20     -> (False, "tool_not_allowed_for_role")
#   cust_1001/ACC-5001/billing_agent, $9999.99 -> (False, "limit_exceeded")
#   redact_for_role(..., "tech_agent") -> dict with balance_cents, payment_method_last4, contract_end removed
