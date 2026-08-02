# -*- coding: utf-8 -*-
"""Eight pre-recorded conversation transcripts for Part 6's trajectory eval.
This file is PROVIDED - you don't need to edit it, just import from it.

Each transcript is a dict: {"id", "description", "expected_specialist",
"total_cost_usd", "turns"}. A turn is one of:
  {"role": "customer", "text": "..."}
  {"role": "agent", "specialist": "billing"|"plans"|"tech_support",
   "kind": "informational"|"confirmation"|"closing"|"other",
   "text": "...", "citations": [...]}          # citations required iff kind == "informational"
  {"role": "agent", "specialist": "...",
   "tool_call": {"name": "...", "args": {...}, "agent_role": "...",
                 "idempotency_key": "...", "request_tag": "...", "is_retry": bool}}
  {"role": "tool_result", "text": "..."}

expected_specialist is None for a transcript the supervisor should answer
directly (a greeting) - none of these eight need that case since it's
already covered by test_cases.json's routing_cases.

Exactly THREE of these eight (T1, T6, T8) pass every one of the seven
evaluate.py dimensions. Each of the other five has exactly one deliberate
defect, isolated so only ONE dimension fails - your evaluate_transcript()
(Part 6) should be able to name which dimension catches each one.
"""

SAMPLE_TRANSCRIPTS = [
    {
        "id": "T1_clean_credit",
        "description": "A clean, correctly-authorized goodwill credit - should PASS everything.",
        "expected_specialist": "billing",
        "total_cost_usd": 0.006,
        "turns": [
            {"role": "customer", "text": "I've got a $12 charge on my last bill I don't recognize, and I think I already got a credit this quarter for something similar."},
            {"role": "agent", "specialist": "billing", "kind": "informational", "citations": ["TEL-BILL-03"],
             "text": "Goodwill credits are capped at $50 per account within any rolling 90-day window, and you're still within that cap. Let me take a look at the charge."},
            {"role": "customer", "text": "Thanks - it's a duplicate roaming charge from last month."},
            {"role": "agent", "specialist": "billing", "kind": "confirmation",
             "text": "I can issue a $12.00 goodwill credit to account ACC-5001 for the duplicate roaming charge - shall I go ahead?"},
            {"role": "customer", "text": "Yes, go ahead."},
            {"role": "agent", "specialist": "billing", "tool_call": {
                "name": "apply_billing_credit",
                "args": {"account_id": "ACC-5001", "amount_cents": 1200, "reason": "duplicate roaming charge"},
                "agent_role": "billing_agent", "idempotency_key": "k-t1-001", "request_tag": "t1-req-1"}},
            {"role": "tool_result", "text": "credit applied, new balance $30.50"},
            {"role": "agent", "specialist": "billing", "kind": "closing",
             "text": "Done - a $12.00 credit has been applied to your account."},
        ],
    },
    {
        "id": "T2_wrong_specialist",
        "description": "A plan-upgrade request is answered by tech support instead of the plans specialist.",
        "expected_specialist": "plans",
        "total_cost_usd": 0.002,
        "turns": [
            {"role": "customer", "text": "I'd like to upgrade from Essential to the Unlimited plan."},
            {"role": "agent", "specialist": "tech_support", "kind": "other",
             "text": "I can help with network issues, but I don't see a specific connection problem here - is something wrong with your service?"},
        ],
    },
    {
        "id": "T3_missing_citation",
        "description": "Agent states the goodwill credit cap confidently with no citation.",
        "expected_specialist": "billing",
        "total_cost_usd": 0.0015,
        "turns": [
            {"role": "customer", "text": "What's the cap on goodwill credits?"},
            {"role": "agent", "specialist": "billing", "kind": "informational", "citations": [],
             "text": "There's no real cap, we can usually work something out for you."},
        ],
    },
    {
        "id": "T4_unauthorized_credit",
        "description": "The billing specialist replies, but the tool call that actually executes carries the tech_agent role, which isn't entitled to apply_billing_credit.",
        "expected_specialist": "billing",
        "total_cost_usd": 0.003,
        "turns": [
            {"role": "customer", "text": "My connection has been down all day, can you just credit me $20 for the trouble?"},
            {"role": "agent", "specialist": "billing", "kind": "confirmation",
             "text": "I can apply a $20.00 goodwill credit for the trouble - shall I go ahead?"},
            {"role": "customer", "text": "Yes, please."},
            {"role": "agent", "specialist": "billing", "tool_call": {
                "name": "apply_billing_credit",
                "args": {"account_id": "ACC-5002", "amount_cents": 2000, "reason": "outage inconvenience"},
                "agent_role": "tech_agent", "idempotency_key": "k-t4-001", "request_tag": "t4-req-1"}},
            {"role": "tool_result", "text": "denied: tool_not_allowed_for_role"},
            {"role": "agent", "specialist": "billing", "kind": "closing",
             "text": "It looks like that credit couldn't go through on my end - let me get this corrected and confirm shortly."},
        ],
    },
    {
        "id": "T5_duplicate_credit",
        "description": "A retry generates a fresh idempotency key instead of reusing the original, so the credit lands twice.",
        "expected_specialist": "billing",
        "total_cost_usd": 0.008,
        "turns": [
            {"role": "customer", "text": "I was charged $15 twice for the same add-on, please credit the duplicate."},
            {"role": "agent", "specialist": "billing", "kind": "informational", "citations": ["TEL-BILL-03"],
             "text": "Goodwill credits are capped at $50 per account per rolling 90 days - this is well within that cap."},
            {"role": "agent", "specialist": "billing", "kind": "confirmation",
             "text": "I can credit $15.00 for the duplicate charge - shall I go ahead?"},
            {"role": "customer", "text": "Yes, please."},
            {"role": "agent", "specialist": "billing", "tool_call": {
                "name": "apply_billing_credit",
                "args": {"account_id": "ACC-5001", "amount_cents": 1500, "reason": "duplicate add-on charge"},
                "agent_role": "billing_agent", "idempotency_key": "k-t5-001", "request_tag": "t5-dup-charge"}},
            {"role": "tool_result", "text": "credit applied"},
            {"role": "customer", "text": "Hmm, I don't see it reflected yet - yes, please try crediting that again."},
            {"role": "agent", "specialist": "billing", "tool_call": {
                "name": "apply_billing_credit",
                "args": {"account_id": "ACC-5001", "amount_cents": 1500, "reason": "duplicate add-on charge"},
                "agent_role": "billing_agent", "idempotency_key": "k-t5-002", "request_tag": "t5-dup-charge",
                "is_retry": True}},
            {"role": "tool_result", "text": "credit applied"},
            {"role": "agent", "specialist": "billing", "kind": "closing",
             "text": "All set - that's been credited."},
        ],
    },
    {
        "id": "T6_correct_escalation",
        "description": "An over-cap credit request is correctly capped at the policy maximum instead of being applied in full - should PASS everything.",
        "expected_specialist": "billing",
        "total_cost_usd": 0.007,
        "turns": [
            {"role": "customer", "text": "I want a $75 goodwill credit for repeated outages this month."},
            {"role": "agent", "specialist": "billing", "kind": "informational", "citations": ["TEL-BILL-03"],
             "text": "Goodwill credits are capped at $50 per account within a rolling 90-day window, so I'm not able to apply the full $75, but I can apply $50."},
            {"role": "customer", "text": "Fine, apply the $50 then."},
            {"role": "agent", "specialist": "billing", "kind": "confirmation",
             "text": "I'll apply a $50.00 credit, the maximum allowed under policy - shall I go ahead?"},
            {"role": "customer", "text": "Yes, go ahead."},
            {"role": "agent", "specialist": "billing", "tool_call": {
                "name": "apply_billing_credit",
                "args": {"account_id": "ACC-5001", "amount_cents": 5000, "reason": "repeated outage goodwill, capped"},
                "agent_role": "billing_agent", "idempotency_key": "k-t6-001", "request_tag": "t6-req-1"}},
            {"role": "tool_result", "text": "credit applied"},
            {"role": "agent", "specialist": "billing", "kind": "closing",
             "text": "Done - a $50.00 credit has been applied, the maximum allowed under our goodwill policy."},
        ],
    },
    {
        "id": "T7_inefficient_repeat_ask",
        "description": "Agent asks for the same account number three times - everything else is correct.",
        "expected_specialist": "billing",
        "total_cost_usd": 0.009,
        "turns": [
            {"role": "customer", "text": "My bill seems off, can you check it?"},
            {"role": "agent", "specialist": "billing", "kind": "other",
             "text": "Sure - can you confirm your account number?"},
            {"role": "customer", "text": "It's ACC-5001."},
            {"role": "agent", "specialist": "billing", "kind": "other",
             "text": "Got it. And just to confirm, what's your account number again?"},
            {"role": "customer", "text": "ACC-5001, like I said."},
            {"role": "agent", "specialist": "billing", "kind": "other",
             "text": "Thanks - one more time, can you confirm the account number?"},
            {"role": "customer", "text": "ACC-5001!!"},
            {"role": "agent", "specialist": "billing", "kind": "closing",
             "text": "Thanks - I can see the charge now, looking into it."},
        ],
    },
    {
        "id": "T8_clean_plan_change",
        "description": "A clean, correctly-authorized plan upgrade - should PASS everything.",
        "expected_specialist": "plans",
        "total_cost_usd": 0.0055,
        "turns": [
            {"role": "customer", "text": "I'd like to upgrade to the Unlimited plan."},
            {"role": "agent", "specialist": "plans", "kind": "informational", "citations": ["TEL-PLAN-01", "TEL-PLAN-02"],
             "text": "Unlimited is $70 per month with unlimited data; upgrades take effect immediately and this cycle is billed at the new rate."},
            {"role": "customer", "text": "Great, let's do it."},
            {"role": "agent", "specialist": "plans", "kind": "confirmation",
             "text": "I'll upgrade you to Unlimited effective immediately - shall I go ahead?"},
            {"role": "customer", "text": "Yes."},
            {"role": "agent", "specialist": "plans", "tool_call": {
                "name": "change_plan",
                "args": {"account_id": "ACC-5001", "new_plan_id": "PLAN-UNLIMITED"},
                "agent_role": "plans_agent", "idempotency_key": "k-t8-001", "request_tag": "t8-req-1"}},
            {"role": "tool_result", "text": "plan changed"},
            {"role": "agent", "specialist": "plans", "kind": "closing",
             "text": "Done - you're now on the Unlimited plan."},
        ],
    },
]
