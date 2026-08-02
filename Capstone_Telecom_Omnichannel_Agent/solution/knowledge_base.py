# -*- coding: utf-8 -*-
"""Shared knowledge base for the Northwind Telecom capstone.
This file is PROVIDED - you don't need to edit it, just import from it.

12 clean policy/support docs in the same doc_id/title/text format used
throughout the course (Day1 H1's KB, Day5 lab30's POLICY_CLAUSES). Two
docs are load-bearing: TEL-BILL-03's credit cap feeds directly into
apply_billing_credit's role limit, and TEL-NET-03's priority matrix feeds
create_service_ticket's priority derivation - grounding and action are
coupled here, not parallel.
"""

KB_DOCS = [
    {
        "doc_id": "TEL-PLAN-01",
        "title": "Northwind Mobile Plan Catalog",
        "category": "plans",
        "text": (
            "Northwind Telecom offers three postpaid plans: Essential with "
            "5GB data for $30 per month, Plus with 30GB data for $50 per "
            "month, and Unlimited with unlimited data for $70 per month. "
            "All three plans include unlimited calls and texts within the "
            "Northwind network."
        ),
    },
    {
        "doc_id": "TEL-PLAN-02",
        "title": "Plan Changes: Upgrades and Downgrades",
        "category": "plans",
        "text": (
            "Upgrading to a higher-tier plan takes effect immediately, with "
            "the remaining days in the current cycle billed at the new "
            "plan's rate. Downgrading to a lower-tier plan takes effect at "
            "the start of the next monthly cycle, not immediately. "
            "Customers still in a fixed-term contract pay a twenty-five "
            "dollar in-contract downgrade fee unless a supervisor override "
            "waives it."
        ),
    },
    {
        "doc_id": "TEL-BILL-01",
        "title": "Billing Proration",
        "category": "billing",
        "text": (
            "Billing proration works as follows: when a plan change happens "
            "mid-cycle, the charge for that billing cycle is prorated by "
            "taking the days remaining in the cycle, dividing by the total "
            "days in the cycle, and multiplying by the price difference "
            "between the old and new plan."
        ),
    },
    {
        "doc_id": "TEL-BILL-02",
        "title": "Data Overage Charges",
        "category": "billing",
        "text": (
            "Data overage charges apply once a customer exceeds their "
            "plan's monthly data allowance. The overage charge is billed "
            "at ten dollars per additional five-gigabyte block, rounded up "
            "to the nearest block."
        ),
    },
    {
        "doc_id": "TEL-BILL-03",
        "title": "Goodwill Credit Policy",
        "category": "billing",
        "text": (
            "Goodwill credits may be issued to resolve billing disputes. "
            "There is a cap: credits are capped at fifty dollars per "
            "account within any rolling ninety-day window, and every "
            "goodwill credit must include a documented reason before it "
            "can be applied."
        ),
    },
    {
        "doc_id": "TEL-BILL-04",
        "title": "International Roaming",
        "category": "billing",
        "text": (
            "International roaming is available two ways: a ten-dollar "
            "daily roaming pass covering all use in supported countries "
            "for that day, or pay-as-you-go roaming billed at ten cents "
            "per megabyte with no daily pass purchased."
        ),
    },
    {
        "doc_id": "TEL-BILL-05",
        "title": "Late Payment Fee",
        "category": "billing",
        "text": (
            "A late fee of fifteen dollars applies to any bill unpaid ten "
            "days after the due date. Customers who anticipate missing a "
            "due date can request a payment arrangement before the "
            "account becomes overdue to avoid the late fee."
        ),
    },
    {
        "doc_id": "TEL-NET-01",
        "title": "Outage Service Credit (SLA)",
        "category": "network",
        "text": (
            "Customers affected by a confirmed network outage lasting more "
            "than four hours are eligible for a one-day service credit "
            "under the outage SLA, applied automatically to the next bill "
            "without requiring a request."
        ),
    },
    {
        "doc_id": "TEL-NET-02",
        "title": "Troubleshooting Ladder",
        "category": "network",
        "text": (
            "The standard troubleshooting ladder for a slow or dropping "
            "connection is: restart the device, toggle airplane mode off "
            "and on, check that automatic APN settings are enabled, and "
            "only then escalate to a service ticket if the issue persists."
        ),
    },
    {
        "doc_id": "TEL-NET-03",
        "title": "Ticket Priority Matrix",
        "category": "network",
        "text": (
            "Service tickets are prioritized using a three-level priority "
            "matrix: P1 tickets indicate complete loss of service, P2 "
            "tickets indicate degraded or significantly slowed service, "
            "and P3 tickets indicate intermittent or occasional issues. "
            "Priority matrix tickets marked P1 receive the fastest "
            "response."
        ),
    },
    {
        "doc_id": "TEL-POL-01",
        "title": "Identity Verification",
        "category": "policy",
        "text": (
            "Before disclosing or discussing any account detail, an agent "
            "must verify the customer's identity using at least one "
            "verification factor beyond the account number - for example "
            "the last four digits of the payment method on file, or a "
            "security PIN. Identity verification must happen before "
            "account details are shared."
        ),
    },
    {
        "doc_id": "TEL-POL-02",
        "title": "AI Disclosure and Recording Consent",
        "category": "policy",
        "text": (
            "Every voice or chat interaction must begin with a clear "
            "disclosure to the customer, and the agent must disclose that "
            "the customer is speaking with an artificial intelligence "
            "agent. The agent must then request explicit consent to "
            "record the interaction before any account-specific "
            "discussion begins."
        ),
    },
]
