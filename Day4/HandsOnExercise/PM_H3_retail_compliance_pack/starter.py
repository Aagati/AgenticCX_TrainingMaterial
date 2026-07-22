"""
PM · H3 — Retail CX Compliance Pack (STARTER)
No API key needed — pure record-keeping and regex logic.
"""

import re
from datetime import datetime, timedelta, timezone

CARD_NUMBER_PATTERN = re.compile(r"\b(?:\d[ -]?){13,19}\b")
SSN_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")


def mask_pii_pci(text: str) -> str:
    """
    TODO 1: Replace any CARD_NUMBER_PATTERN match in `text` with
    "[CARD_REDACTED]", and any SSN_PATTERN match with "[GOVT_ID_REDACTED]".
    Return the redacted text.
    """
    raise NotImplementedError


class CompliancePack:
    def __init__(self):
        self.records = {}

    def _add_record(self, customer_id: str, record: dict):
        self.records.setdefault(customer_id, []).append(record)

    def disclose(self, customer_id: str) -> str:
        """
        TODO 2: Add a record {"type": "disclosure", "timestamp": now}.
        Return the disclosure statement string.
        """
        raise NotImplementedError

    def capture_consent(self, customer_id: str, purpose: str, granted: bool):
        """
        TODO 3: Add a record {"type": "consent", "purpose": purpose,
        "granted": granted, "timestamp": now}.
        """
        raise NotImplementedError

    def check_consent(self, customer_id: str, purpose: str) -> bool:
        """
        TODO 4: Find all consent records for customer_id with this purpose,
        sort by timestamp, and return the "granted" value of the MOST
        RECENT one. Return False if no such record exists.
        """
        raise NotImplementedError

    def log_interaction(self, customer_id: str, raw_text: str):
        """
        TODO 5: Run raw_text through mask_pii_pci() FIRST, then add a
        record {"type": "interaction_log", "text": <redacted>, "timestamp": now}.
        The raw, unredacted text must never be stored, even transiently.
        """
        raise NotImplementedError

    def apply_retention_policy(self, retention_days: int):
        """
        TODO 6: For every customer_id, remove any record whose timestamp
        is older than retention_days from now. Remove customer_id entries
        entirely if they end up with zero records.
        """
        raise NotImplementedError

    def handle_deletion_request(self, customer_id: str) -> str:
        """
        TODO 7: Remove customer_id entirely from self.records (no error if
        already absent). Return a confirmation string.
        """
        raise NotImplementedError


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
