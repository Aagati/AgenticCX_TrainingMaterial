"""
PM · H3 — Retail CX Compliance Pack (REFERENCE SOLUTION)
"""

import re
from datetime import datetime, timedelta, timezone

CARD_NUMBER_PATTERN = re.compile(r"\b(?:\d[ -]?){13,19}\b")
SSN_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")


def mask_pii_pci(text: str) -> str:
    """Redact card-number-like and SSN-like sequences BEFORE anything is
    stored. This runs on every piece of free text that enters the compliance
    pack — logging raw sensitive data and redacting it later is not
    acceptable; it must never be written in the first place."""
    text = CARD_NUMBER_PATTERN.sub("[CARD_REDACTED]", text)
    text = SSN_PATTERN.sub("[GOVT_ID_REDACTED]", text)
    return text


class CompliancePack:
    def __init__(self):
        self.records = {}

    def _add_record(self, customer_id: str, record: dict):
        self.records.setdefault(customer_id, []).append(record)

    def disclose(self, customer_id: str) -> str:
        self._add_record(customer_id, {"type": "disclosure", "timestamp": datetime.now(timezone.utc)})
        return "You're interacting with an automated assistant, not a human agent."

    def capture_consent(self, customer_id: str, purpose: str, granted: bool):
        self._add_record(customer_id, {
            "type": "consent", "purpose": purpose, "granted": granted,
            "timestamp": datetime.now(timezone.utc),
        })

    def check_consent(self, customer_id: str, purpose: str) -> bool:
        records = self.records.get(customer_id, [])
        consent_records = [r for r in records if r["type"] == "consent" and r["purpose"] == purpose]
        if not consent_records:
            return False
        most_recent = max(consent_records, key=lambda r: r["timestamp"])
        return most_recent["granted"]

    def log_interaction(self, customer_id: str, raw_text: str):
        """Store a free-text interaction log entry — ALWAYS through
        mask_pii_pci() first. This is the one place in the pack where
        arbitrary customer-typed text could reach storage, so it's the one
        place PCI/PII redaction is non-negotiable."""
        redacted = mask_pii_pci(raw_text)
        self._add_record(customer_id, {
            "type": "interaction_log", "text": redacted, "timestamp": datetime.now(timezone.utc),
        })

    def apply_retention_policy(self, retention_days: int):
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        for customer_id in list(self.records.keys()):
            kept = [r for r in self.records[customer_id] if r["timestamp"] >= cutoff]
            if kept:
                self.records[customer_id] = kept
            else:
                del self.records[customer_id]

    def handle_deletion_request(self, customer_id: str) -> str:
        self.records.pop(customer_id, None)
        return f"All records for {customer_id} have been deleted."


if __name__ == "__main__":
    pack = CompliancePack()
    cid = "cust_9001"

    print(pack.disclose(cid))
    pack.capture_consent(cid, "data_processing", True)
    pack.capture_consent(cid, "marketing_contact", False)
    print("data_processing consent:", pack.check_consent(cid, "data_processing"))
    print("marketing_contact consent:", pack.check_consent(cid, "marketing_contact"))

    pack.capture_consent(cid, "marketing_contact", True)
    print("marketing_contact consent (after change):", pack.check_consent(cid, "marketing_contact"))

    print("\n--- PII/PCI redaction on interaction logging ---")
    pack.log_interaction(cid, "My card number is 4532-1102-8821-9901, please charge the return fee.")
    pack.log_interaction(cid, "My SSN is 000-12-3456 if you need it for verification.")
    for r in pack.records[cid]:
        if r["type"] == "interaction_log":
            print(" logged:", r["text"])

    pack._add_record(cid, {"type": "interaction_log", "text": "old note", "timestamp": datetime.now(timezone.utc) - timedelta(days=400)})
    print("\nrecords before retention:", len(pack.records[cid]))
    pack.apply_retention_policy(retention_days=365)
    print("records after retention (400-day-old one purged):", len(pack.records[cid]))

    print(pack.handle_deletion_request(cid))
    print("records for customer after deletion:", pack.records.get(cid))

# Expected: the two log_interaction() calls store "[CARD_REDACTED]" and
# "[GOVT_ID_REDACTED]" in place of the raw card number and SSN — the raw
# sensitive values should never appear in pack.records at all, not even
# transiently. Records before retention=7 (disclosure + 3 consents + 2
# interaction logs + 1 backdated), after retention=6.
