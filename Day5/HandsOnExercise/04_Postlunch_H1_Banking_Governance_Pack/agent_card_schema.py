"""
Day 5 · Post-Lunch Lab H1 (Banking) — Agent Card, Programmatic Version
=========================================================================
SUPPLEMENTARY FILE — added in response to reviewer feedback.

The Word template (Governance_Pack_Template.docx) is still the primary
deliverable for this lab: compliance and legal reviewers who don't read
code need a document they can open and comment on directly.

This file exists for teams who ALSO want a typed, machine-readable
version of the same Agent Card — the kind you could validate in a
CI/CD pipeline, or render into markdown/HTML automatically, so the
governance pack doesn't go stale as the agent changes.

Requires: pip install pydantic --break-system-packages

Usage:
    python agent_card_schema.py
"""

from enum import Enum
from typing import List
from pydantic import BaseModel, Field, field_validator


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class AutonomyLevel(str, Enum):
    L0 = "L0"  # human does everything; agent only drafts suggestions
    L1 = "L1"  # agent acts; human approves every action before it executes
    L2 = "L2"  # agent acts autonomously within a defined, low-risk scope
    L3 = "L3"  # agent acts broadly; human reviews via sampled audit


class ToolEntitlement(BaseModel):
    """One tool the agent is allowed to call, and the guardrail around it."""
    tool_name: str
    description: str
    risk_level: RiskLevel
    requires_human_approval: bool = Field(
        description="True if a human must approve this specific action before it executes, "
                    "regardless of the agent's overall autonomy level."
    )


class AgentCard(BaseModel):
    """
    Typed equivalent of Section 1 ('Agent Card') in Governance_Pack_Template.docx.
    Field names are deliberately aligned to that template so the two stay in sync.
    """
    agent_id: str
    agent_name: str
    version: str
    purpose: str = Field(description="One-line purpose — what is this agent for?")
    scope_allowed: List[str] = Field(description="Intents/tasks explicitly in scope.")
    scope_prohibited: List[str] = Field(description="Actions explicitly out of scope — should route to a human.")
    autonomy_level: AutonomyLevel
    allowed_tools: List[ToolEntitlement]
    data_touched: List[str] = Field(description="Categories of customer data this agent accesses.")
    known_limitations: List[str] = Field(description="Where it currently fails or needs a human.")
    compliance_standards: List[str] = Field(
        default_factory=lambda: ["EU_AI_Act_Transparency", "DPDP_Act", "ISO_42001"]
    )
    human_fallback_queue: str = Field(description="Where escalations route to.")

    @field_validator("scope_allowed", "scope_prohibited", "known_limitations")
    @classmethod
    def must_not_be_empty(cls, v):
        if not v:
            raise ValueError("This field must list at least one item — an empty governance claim isn't reviewable.")
        return v


def example_banking_agent_card() -> AgentCard:
    """
    A worked example for a banking card-dispute agent — mirrors the level of
    detail expected in the Word template's own worked example appendix.
    """
    return AgentCard(
        agent_id="AG-BANK-009",
        agent_name="Card Dispute & Status Agent",
        version="v1.0.0",
        purpose="Helps customers open a card dispute, check dispute status, and issue a temporary credit for small disputes.",
        scope_allowed=[
            "Open a new card dispute",
            "Check status of an existing dispute",
            "Issue a temporary credit for disputes under $200",
        ],
        scope_prohibited=[
            "Approve a permanent credit or final dispute resolution",
            "Issue a temporary credit for disputes at or above $200",
            "Discuss dispute details before identity verification",
        ],
        autonomy_level=AutonomyLevel.L2,
        allowed_tools=[
            ToolEntitlement(
                tool_name="open_dispute",
                description="Creates a new dispute case in the core banking system.",
                risk_level=RiskLevel.MEDIUM,
                requires_human_approval=False,
            ),
            ToolEntitlement(
                tool_name="issue_temporary_credit",
                description="Issues a temporary credit for a disputed amount under $200.",
                risk_level=RiskLevel.HIGH,
                requires_human_approval=False,
            ),
            ToolEntitlement(
                tool_name="get_dispute_status",
                description="Read-only lookup of an existing dispute's status.",
                risk_level=RiskLevel.LOW,
                requires_human_approval=False,
            ),
        ],
        data_touched=["Account number", "Transaction history", "Dispute case notes"],
        known_limitations=[
            "Cannot handle disputes involving suspected first-party fraud — routes to a human.",
            "Does not currently support joint-account disputes requiring two-party consent.",
        ],
        human_fallback_queue="Tier2_Banking_Disputes",
    )


if __name__ == "__main__":
    card = example_banking_agent_card()
    print("=== Agent Card (validated) ===")
    print(card.model_dump_json(indent=2))

    print("\n=== JSON Schema (for CI/CD validation) ===")
    import json
    print(json.dumps(card.model_json_schema(), indent=2)[:600], "\n... (truncated)")

    print("\n=== Rendered as Markdown (for auto-generated docs) ===")
    print(f"# {card.agent_name} ({card.agent_id})\n")
    print(f"**Version:** {card.version}  ")
    print(f"**Autonomy Level:** {card.autonomy_level.value}  ")
    print(f"**Purpose:** {card.purpose}\n")
    print("**In scope:**")
    for item in card.scope_allowed:
        print(f"- {item}")
    print("\n**Out of scope:**")
    for item in card.scope_prohibited:
        print(f"- {item}")
