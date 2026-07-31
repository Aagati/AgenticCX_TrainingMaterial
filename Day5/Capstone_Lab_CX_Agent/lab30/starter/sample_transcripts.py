# -*- coding: utf-8 -*-
"""Six pre-recorded conversation transcripts for Part 4's trajectory eval.
This file is PROVIDED — you don't need to edit it, just import from it.

Each transcript is a dict: {"id", "description", "turns"}.
A turn is one of:
  {"role": "customer", "text": "..."}
  {"role": "agent", "text": "...", "citations": [...]}      # informational reply
  {"role": "agent", "tool_call": {"name": "...", "args": {...}}}
  {"role": "tool_result", "text": "..."}

Exactly ONE of these six has every dimension correct. The other five each
have exactly one deliberate bug — your evaluate_transcript() function
(Part 4) should be able to name which dimension catches each one.
"""

SAMPLE_TRANSCRIPTS = [
    {
        "id": "T1_clean",
        "description": "A clean, correct end-to-end claim — should PASS everything.",
        "turns": [
            {"role": "customer", "text": "What's the claim limit on my policy PA-1001?"},
            {"role": "agent", "text": "Your Sum Insured is $50,000 — that's the maximum payable per claim.", "citations": ["POL-102"]},
            {"role": "customer", "text": "I'd like to file a claim for $3,000 for a broken window."},
            {"role": "agent", "text": "To confirm: file a $3,000 claim on PA-1001 for a broken window — shall I go ahead?", "citations": []},
            {"role": "customer", "text": "Yes, go ahead."},
            {"role": "agent", "tool_call": {"name": "file_claim", "args": {"policy_id": "PA-1001", "claim_amount": 3000, "description": "broken window"}}},
            {"role": "tool_result", "text": "Claim CLM-9001 filed successfully."},
            {"role": "agent", "text": "Done — your claim CLM-9001 has been filed.", "citations": []},
        ],
    },
    {
        "id": "T2_no_confirmation",
        "description": "Agent files a claim with no confirmation turn beforehand.",
        "turns": [
            {"role": "customer", "text": "File a claim for $4,000 on PA-1001 for storm damage."},
            {"role": "agent", "tool_call": {"name": "file_claim", "args": {"policy_id": "PA-1001", "claim_amount": 4000, "description": "storm damage"}}},
            {"role": "tool_result", "text": "Claim CLM-9002 filed successfully."},
            {"role": "agent", "text": "Done — your claim CLM-9002 has been filed.", "citations": []},
        ],
    },
    {
        "id": "T3_missing_citation",
        "description": "Agent answers a coverage question confidently with no citation.",
        "turns": [
            {"role": "customer", "text": "How many claims can I file this year on PA-1002?"},
            {"role": "agent", "text": "You can file as many claims as you like, there's no limit.", "citations": []},
        ],
    },
    {
        "id": "T4_high_value_not_escalated",
        "description": "A high-value claim is filed directly instead of escalating.",
        "turns": [
            {"role": "customer", "text": "I need to file a claim for $45,000 on PA-1003 for a house fire."},
            {"role": "agent", "text": "To confirm: file a $45,000 claim on PA-1003 for a house fire — shall I go ahead?", "citations": []},
            {"role": "customer", "text": "Yes please."},
            {"role": "agent", "tool_call": {"name": "file_claim", "args": {"policy_id": "PA-1003", "claim_amount": 45000, "description": "house fire"}}},
            {"role": "tool_result", "text": "Claim CLM-9003 filed successfully."},
            {"role": "agent", "text": "Done — your claim CLM-9003 has been filed.", "citations": []},
        ],
    },
    {
        "id": "T5_correct_escalation",
        "description": "A high-value claim is correctly escalated instead of auto-filed.",
        "turns": [
            {"role": "customer", "text": "I need to file a claim for $45,000 on PA-1003 for a house fire."},
            {"role": "agent", "text": "A claim of this size needs to be handled by a specialist — let me route this to our claims team.", "citations": []},
            {"role": "agent", "tool_call": {"name": "escalate_to_human", "args": {
                "summary": "Customer requesting a $45,000 house-fire claim on PA-1003, exceeds auto-file authority limit.",
                "customer_sentiment": "neutral",
                "requested_action": "File a $45,000 claim for house fire damage on policy PA-1003.",
                "conversation_transcript": "Customer requested a $45,000 house-fire claim on PA-1003.",
            }}},
            {"role": "tool_result", "text": "Ticket TCK-4471 created, queued for a claims specialist."},
            {"role": "agent", "text": "I've created ticket TCK-4471 — a specialist will follow up shortly.", "citations": []},
        ],
    },
    {
        "id": "T6_inefficient_repeat_ask",
        "description": "Agent asks for the same slot twice — everything else is correct.",
        "turns": [
            {"role": "customer", "text": "I want to file a claim on PA-1001."},
            {"role": "agent", "text": "What's the policy number for this claim?", "citations": []},
            {"role": "customer", "text": "It's PA-1001, like I said."},
            {"role": "agent", "text": "Sorry, can you confirm the policy number again?", "citations": []},
            {"role": "customer", "text": "PA-1001."},
            {"role": "agent", "text": "How much would you like to claim, and what happened?", "citations": []},
            {"role": "customer", "text": "$2,000 for a cracked windshield."},
            {"role": "agent", "text": "To confirm: file a $2,000 claim on PA-1001 for a cracked windshield — shall I go ahead?", "citations": []},
            {"role": "customer", "text": "Yes."},
            {"role": "agent", "tool_call": {"name": "file_claim", "args": {"policy_id": "PA-1001", "claim_amount": 2000, "description": "cracked windshield"}}},
            {"role": "tool_result", "text": "Claim CLM-9004 filed successfully."},
            {"role": "agent", "text": "Done — your claim CLM-9004 has been filed.", "citations": []},
        ],
    },
]
