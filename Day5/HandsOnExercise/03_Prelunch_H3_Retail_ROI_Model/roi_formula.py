"""
Day 5 · Pre-Lunch Lab H3 (Retail) — ROI Formula, Programmatic Version
=========================================================================
SUPPLEMENTARY FILE — added in response to reviewer feedback.

Retail_ROI_Calculator_TEMPLATE.xlsx is still the primary deliverable
for this lab: an ROI business case is usually built and presented by
business/operations stakeholders in Excel, not in a script, and that's
who this lab is really written for.

This file exists for teams who ALSO want a code version of the same
net-savings formula from the workbook — useful if you want to wire it
directly to live telemetry later, e.g. in Day 8's analytics pipeline.
The numbers below match the Excel solution workbook's example exactly,
so you can use this to sanity-check that workbook by hand.

Usage:
    python roi_formula.py
"""

from dataclasses import dataclass


@dataclass
class ROIInputs:
    monthly_contact_volume: int
    human_aht_minutes: float
    human_cost_per_hour: float
    agent_resolution_rate: float      # 0.0-1.0
    agent_cost_per_contact: float     # blended tokens + infra
    csat_live: float                  # out of 5
    csat_floor: float                 # out of 5


@dataclass
class ROIResult:
    approved: bool
    human_cost_per_contact: float
    monthly_savings: float
    annualised_savings: float
    blended_cost_per_contact: float
    rejection_reason: str = ""


def calculate_roi(inputs: ROIInputs) -> ROIResult:
    """
    Mirrors the 'ROI Model' sheet in Retail_ROI_Calculator_SOLUTION.xlsx,
    formula for formula:

        human_cost_per_contact = (human_aht_minutes / 60) * human_cost_per_hour
        contacts_resolved_by_agent = volume * resolution_rate
        contacts_needing_human = volume - contacts_resolved_by_agent
        cost_if_all_human = volume * human_cost_per_contact
        blended_cost = (resolved * agent_cost_per_contact) + (needing_human * human_cost_per_contact)
        monthly_savings = cost_if_all_human - blended_cost
        CSAT floor is a hard gate: below floor, the business case is not approved,
        regardless of how large the savings number is.
    """
    # Quality floor gate, checked FIRST — a savings number under a failed
    # CSAT floor is not a valid business case, same principle as Week 1's
    # ROI topic: never chase cost savings at the expense of experience.
    if inputs.csat_live < inputs.csat_floor:
        return ROIResult(
            approved=False,
            human_cost_per_contact=0.0,
            monthly_savings=0.0,
            annualised_savings=0.0,
            blended_cost_per_contact=0.0,
            rejection_reason=(
                f"CSAT floor not met: {inputs.csat_live:.2f} < required {inputs.csat_floor:.2f}. "
                f"Savings are not reportable until this is resolved."
            ),
        )

    human_cost_per_contact = (inputs.human_aht_minutes / 60) * inputs.human_cost_per_hour
    resolved_by_agent = inputs.monthly_contact_volume * inputs.agent_resolution_rate
    needing_human = inputs.monthly_contact_volume - resolved_by_agent

    cost_if_all_human = inputs.monthly_contact_volume * human_cost_per_contact
    blended_cost = (resolved_by_agent * inputs.agent_cost_per_contact) + (needing_human * human_cost_per_contact)

    monthly_savings = cost_if_all_human - blended_cost
    blended_cost_per_contact = blended_cost / inputs.monthly_contact_volume

    return ROIResult(
        approved=True,
        human_cost_per_contact=round(human_cost_per_contact, 2),
        monthly_savings=round(monthly_savings, 2),
        annualised_savings=round(monthly_savings * 12, 2),
        blended_cost_per_contact=round(blended_cost_per_contact, 2),
    )


if __name__ == "__main__":
    print("--- Case 1: matches the Excel solution workbook's example ---")
    case1 = ROIInputs(
        monthly_contact_volume=20000,
        human_aht_minutes=9.5,
        human_cost_per_hour=28,
        agent_resolution_rate=0.72,
        agent_cost_per_contact=0.35,
        csat_live=4.1,
        csat_floor=4.0,
    )
    result1 = calculate_roi(case1)
    print(result1)
    assert result1.monthly_savings == 58800.0, "Should match the corrected Excel workbook's $58,800/month exactly"
    assert result1.annualised_savings == 705600.0, "Should match the corrected Excel workbook's $705,600/year exactly"
    print("Matches the Excel workbook. ✓")

    print("\n--- Case 2: CSAT floor failure (business case rejected) ---")
    case2 = ROIInputs(
        monthly_contact_volume=20000,
        human_aht_minutes=9.5,
        human_cost_per_hour=28,
        agent_resolution_rate=0.85,   # higher resolution...
        agent_cost_per_contact=0.35,
        csat_live=3.6,                # ...but CSAT collapsed
        csat_floor=4.0,
    )
    result2 = calculate_roi(case2)
    print(result2)
    assert not result2.approved
    print("Correctly rejected despite higher resolution rate. ✓")
