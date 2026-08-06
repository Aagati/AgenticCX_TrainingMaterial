"""
Lab-2: Insurance - One Guardrail Isn't a Guardrail Stack (STARTER).

Day 4 taught ONE guardrail: a single function that flags a message or it
doesn't. This lab replaces that with a STACK - nine ordered layers across
four groups (input, permission, output, compliance), each returning one of
three verdicts, not two: PASS (continue), BLOCK (stop), or REDACT (rewrite
the payload and keep going). That third verdict is the whole idea. A layer
that can only say yes or no is a filter. A layer that can hand the next
layer a DIFFERENT payload is a stack.

You'll build:
  1. Eight guardrail layers (input, permission, output, compliance) - the
     registry itself, and the always-runs audit layer, are given.
  2. GuardrailStack.evaluate - the chain of responsibility that walks the
     registry in order, short-circuiting on BLOCK, transforming on REDACT,
     and always running the audit layer regardless of how the walk ended.
  3. HashChainedAuditLog.append/.verify - a tamper-EVIDENT log where entry
     N's hash is computed over entry N-1's hash, so editing any entry
     invalidates every entry after it.
  4. draft_claim_response - real sonnet call with prompt caching on the
     jurisdiction rulebook (Day 8's mechanic, reused here because a
     rulebook that's byte-identical on every call is exactly what a cache
     breakpoint is for).
  5. run_corpus - a two-sided scorer: a guardrail stack fails in two
     directions (missing a real attack, or blocking a legitimate request),
     and only counting one of them is how you ship a stack nobody can use.
"""

import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional, TypedDict

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

MODEL_DRAFT = "claude-sonnet-5"

DATA_DIR = Path(__file__).parent
with open(DATA_DIR / "rbac_roles.json", encoding="utf-8") as f:
    _RBAC = json.load(f)
    ROLES = _RBAC["roles"]
    ACTORS = _RBAC["actors"]
with open(DATA_DIR / "jurisdiction_rules.json", encoding="utf-8") as f:
    _JURIS = json.load(f)
    JURISDICTIONS = _JURIS["jurisdictions"]
    WRITTEN_CONFIRMATION_SENTENCE = _JURIS["written_confirmation_sentence"]
with open(DATA_DIR / "policy_holders.json", encoding="utf-8") as f:
    CUSTOMERS = {c["customer_id"]: c for c in json.load(f)["customers"]}
with open(DATA_DIR / "adversarial_requests.json", encoding="utf-8") as f:
    REQUESTS = json.load(f)["requests"]

AUDIT_LOG_FILE = DATA_DIR / "guardrail_audit_log.json"

# Deterministic, keyword-based - no live call decides any block in this lab's
# corpus, so run_corpus's counts don't move between runs.
INJECTION_PATTERNS = [
    "ignore all previous instructions", "ignore your instructions", "disregard your system",
    "disregard the above", "disregard your system instructions", "ignore the above",
]
AUTHORITY_CLAIM_PATTERNS = [
    "branch manager", "i am the ceo", "i am authorized to", "override your restrictions",
    "this is the manager speaking", "i am a supervisor",
]

client = Anthropic()


class GuardrailResult(TypedDict, total=False):
    verdict: Literal["PASS", "BLOCK", "REDACT"]
    detail: str
    payload: str  # present only when verdict == "REDACT"


def resolve_context(actor_id: str, customer_id: str, action: str, payout_amount: Optional[float]) -> dict:
    """Given - actor to role, customer to jurisdiction (falling back to
    DEFAULT for any jurisdiction code not in jurisdiction_rules.json, e.g.
    CUST-IN08's "MA")."""
    actor = ACTORS[actor_id]
    role = ROLES[actor["role"]]
    customer = CUSTOMERS[customer_id]
    jurisdiction_code = customer["jurisdiction"]
    jurisdiction = JURISDICTIONS.get(jurisdiction_code, JURISDICTIONS["DEFAULT"])
    return {
        "actor_id": actor_id, "role_name": actor["role"], "role": role,
        "assigned_customers": actor["assigned_customers"],
        "customer_id": customer_id, "customer": customer,
        "jurisdiction_code": jurisdiction_code, "jurisdiction": jurisdiction,
        "action": action, "payout_amount": payout_amount,
        "stop_reason": None,
    }


# ---------------------------------------------------------------------------
# Guardrail registry (given infrastructure - the decorator and the audit
# layer's write path are given; the eight layers below and the chain that
# walks them are yours).
# ---------------------------------------------------------------------------

_GUARDRAIL_REGISTRY: list[dict] = []


def register_guardrail(name: str, group: str, order: int, always_runs: bool = False):
    def decorator(fn):
        _GUARDRAIL_REGISTRY.append({"name": name, "group": group, "order": order, "always_runs": always_runs, "fn": fn})
        return fn
    return decorator


@register_guardrail("injection_probe", group="input", order=10)
def guard_injection(payload: str, context: dict) -> GuardrailResult:
    """
    TODO 1a: Case-insensitive substring scan of `payload` against
    INJECTION_PATTERNS. BLOCK naming the phrase that hit; else PASS.
    """
    raise NotImplementedError


@register_guardrail("authority_claim_probe", group="input", order=20)
def guard_authority_claim(payload: str, context: dict) -> GuardrailResult:
    """
    TODO 1b: Case-insensitive substring scan of `payload` against
    AUTHORITY_CLAIM_PATTERNS - a message trying to talk its way past policy
    by claiming to BE a manager/supervisor/CEO, distinct from
    injection_probe's "ignore your instructions" shape. BLOCK naming the
    phrase that hit; else PASS.
    """
    raise NotImplementedError


@register_guardrail("rbac_action_allowed", group="permission", order=30)
def guard_rbac_action(payload: str, context: dict) -> GuardrailResult:
    """
    TODO 1c: BLOCK unless context["action"] is in context["role"]["actions"].
    detail should name the role and the disallowed action on failure, "ok"
    on pass. This is the coarse check - CAN this role ever do this action at
    all, regardless of which customer or how much money.
    """
    raise NotImplementedError


@register_guardrail("rbac_scope_and_authority", group="permission", order=40)
def guard_rbac_scope(payload: str, context: dict) -> GuardrailResult:
    """
    TODO 1d: Two independent checks, either can BLOCK:
      (a) SCOPE - if context["role"]["scope"] == "own_customers_only" and
          context["customer_id"] is not in context["assigned_customers"],
          BLOCK ("customer not in this actor's assigned book").
      (b) AUTHORITY - if context["action"] == "issue_payout" and
          context["payout_amount"] exceeds context["role"]["max_payout_authority"],
          BLOCK ("payout exceeds this role's authority ceiling").
    Check scope first, then authority. PASS only if neither fires. This is
    the layer that generalizes Day 4's per-user ownership check
    (`check_permission`'s "doesn't own it" branch survives here as the scope
    check) into something an org chart maps onto - role, not just user.
    """
    raise NotImplementedError


@register_guardrail("generation_terminated_cleanly", group="output", order=50)
def guard_generation_terminated(payload: str, context: dict) -> GuardrailResult:
    """
    TODO 1e: NEW SDK SURFACE. context["stop_reason"] carries the stop_reason
    of the drafting response (draft_claim_response stashes it there). BLOCK
    if it is "refusal" - the model shipped a safety layer of its own, and
    your stack has to notice it fired rather than forwarding an empty
    content list downstream. BLOCK if it is "max_tokens" - a truncated
    response is not cosmetic here, because the required disclosure is the
    LAST sentence, so truncation is precisely how you ship a compliance
    violation that looks fine in the first paragraph. PASS on "end_turn"
    and on None (the precomposed-response path never called the model, so
    there is no stop_reason to judge). Reason strings should name the
    stop_reason verbatim.
    """
    raise NotImplementedError


@register_guardrail("jurisdiction_disclosure_present", group="compliance", order=60)
def guard_jurisdiction_disclosure(payload: str, context: dict) -> GuardrailResult:
    """
    TODO 1f: The first REDACT layer - it TRANSFORMS and CONTINUES rather
    than terminating. If context["jurisdiction"]["required_disclosure"]
    does not appear verbatim (case-insensitive is fine) in `payload`,
    return REDACT with the payload rewritten to end with the disclosure as
    its own final sentence. Additionally, if context["payout_amount"] is
    not None and exceeds context["jurisdiction"]["requires_written_confirmation_above"],
    append WRITTEN_CONFIRMATION_SENTENCE too - that second clause is why
    the SAME claim amount produces a different result in CA and in TX.
    PASS (payload unchanged) only when nothing needed adding. Never BLOCK
    here: a missing disclosure is a fixable defect, not an attack.
    """
    raise NotImplementedError


_POLICY_NUMBER_RE = re.compile(r"POL-IN-(\d+)")


@register_guardrail("role_scoped_field_leak", group="output", order=70)
def guard_field_leak(payload: str, context: dict) -> GuardrailResult:
    """
    TODO 1g: The second REDACT layer, driven by IDENTITY rather than
    pattern. Find any POL-IN-#### policy number in `payload` (use
    _POLICY_NUMBER_RE). If context["role"]["can_view_full_policy_number"] is
    True, PASS unchanged - the same string is fine for a fraud investigator
    and not fine for tier-1 support. Otherwise return REDACT with every
    occurrence masked to its last four digits (e.g. POL-IN-1001 becomes
    POL-IN-****1001). This layer runs AFTER the disclosure layer on
    purpose: the disclosure text is fixed and safe, and masking a payload
    the previous layer just extended means you only ever reason about one
    payload, not two.
    """
    raise NotImplementedError


@register_guardrail("prohibited_claim", group="compliance", order=80)
def guard_prohibited_claim(payload: str, context: dict) -> GuardrailResult:
    """
    TODO 1h: Case-insensitive substring scan of the (possibly twice-
    redacted) `payload` against THIS JURISDICTION'S prohibited_phrases -
    context["jurisdiction"]["prohibited_phrases"], not a global list. BLOCK
    naming every phrase that hit. The test corpus contains one phrase that
    is legal in TX and illegal in CA/NY; if you reach for a module-level
    banned-phrases constant instead of the per-jurisdiction list, both
    requests get the same verdict and one of them is wrong.
    """
    raise NotImplementedError


@register_guardrail("audit_chain_write", group="audit", order=90, always_runs=True)
def guard_audit_write(payload: str, context: dict) -> GuardrailResult:
    """Given - builds one audit entry from context and hands it to the
    module-level AUDIT_LOG. Always returns PASS: this layer observes, it
    never decides. Registered always_runs=True so GuardrailStack.evaluate
    runs it even after an earlier layer returned BLOCK - a short-circuiting
    pipeline that skips its own audit layer has a hole exactly where you
    most need a record."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "actor_id": context["actor_id"], "actor_role": context["role_name"],
        "action": context["action"], "subject_customer_id": context["customer_id"],
        "jurisdiction": context["jurisdiction_code"],
        "inputs": {
            "payout_amount": context["payout_amount"],
            "message_sha256_prefix": hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12],
        },
        "layer_trail": context.get("layer_trail", []),
        "final_verdict": context.get("final_verdict_so_far"),
    }
    entry_id = AUDIT_LOG.append(entry)["entry_id"]
    return {"verdict": "PASS", "detail": f"audit entry {entry_id} written"}


class GuardrailStack:
    @staticmethod
    def evaluate(payload: str, context: dict) -> dict:
        """
        TODO 2: The chain of responsibility. Walk _GUARDRAIL_REGISTRY sorted
        by "order", skipping any layer whose "group" is not in
        context["run_groups"] (the caller runs input+permission groups
        BEFORE drafting and output+compliance groups AFTER - groups are a
        FILTER, not just a label) and skipping always_runs layers (handled
        separately below). For each remaining layer:
          - PASS: append {"layer": name, "verdict": "PASS", "detail": ...}
            to a local trail list, keep payload unchanged, continue.
          - REDACT: append to the trail, REPLACE payload with
            result["payload"], continue. Every later layer must see the
            transformed text.
          - BLOCK: append to the trail and STOP walking (don't return yet).
        Whether or not you stopped early, set context["layer_trail"] = trail
        and context["final_verdict_so_far"] = "BLOCK" if any layer blocked
        else "PASS" (the audit layer reads both), then run every registry
        entry with always_runs=True, IN ORDER, passing them (payload,
        context). Return {"final_verdict": "BLOCK" if any layer blocked
        else "PASS", "blocking_layer": <name or None>,
        "payload": <final payload>, "trail": trail,
        "redactions_applied": [names of layers that returned REDACT]}.
        """
        raise NotImplementedError


class HashChainedAuditLog:
    """Given file I/O and canonical serialization - `append`/`verify` are
    yours."""

    def __init__(self, path: Path = AUDIT_LOG_FILE):
        self.path = path

    def _load(self) -> list[dict]:
        return json.load(open(self.path, encoding="utf-8")) if self.path.exists() else []

    def _save(self, chain: list[dict]) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(chain, f, ensure_ascii=False, indent=2)

    @staticmethod
    def _canonical(entry: dict) -> str:
        """Given - sort_keys=True, no whitespace. A dict that serializes
        differently on two runs breaks every hash after it."""
        return json.dumps(entry, sort_keys=True, separators=(",", ":"))

    def append(self, entry: dict) -> dict:
        """
        TODO 3: Load the existing chain. Assign entry["entry_id"] = "AUD-"
        plus a five-digit zero-padded sequence one past len(chain) (e.g.
        "AUD-00001" for the first). Set entry["prev_hash"] to the last
        entry's "entry_hash", or 64 zeros ("0"*64) for the genesis entry.
        Compute entry["entry_hash"] as the sha256 hexdigest of
        `self._canonical(entry_without_entry_hash) + prev_hash` (entry_hash
        itself must not be part of what gets hashed - compute it only
        AFTER setting entry_id and prev_hash, since those ARE part of the
        hashed content). Append the completed entry, save the chain, and
        return it. Entry N's hash is computed OVER entry N-1's hash - that's
        what makes editing entry 2 invalidate 2, 3, 4 and everything after,
        not just entry 2 itself.
        """
        raise NotImplementedError

    def verify(self) -> tuple[bool, Optional[int]]:
        """
        TODO 4: Walk the chain from index 0. For each entry, check its
        "prev_hash" equals the previous entry's "entry_hash" (64 zeros for
        index 0), and recompute its "entry_hash" from its own contents the
        same way append did (canonical serialization of the entry MINUS its
        stored entry_hash, concatenated with prev_hash). Return (True, None)
        if every entry checks out, else (False, <index of the FIRST entry
        that failed>). Returning the index rather than a bare False is what
        makes this an investigation tool instead of just an alarm.
        """
        raise NotImplementedError


AUDIT_LOG = HashChainedAuditLog()


JURISDICTION_RULEBOOK_BLOCK = (
    "JURISDICTION RULEBOOK (reference, applies to every claim response):\n" + json.dumps(JURISDICTIONS, indent=2)
)


def draft_claim_response(context: dict) -> dict:
    """
    TODO 5: If context.get("precomposed_response") is set, return
    {"text": that string, "stop_reason": None} and make NO model call - six
    of the sixteen requests use this so the output/compliance layers can be
    graded deterministically. Otherwise, one real MODEL_DRAFT call. Build
    `system` as a list of TWO blocks - a short per-call instruction (answer
    using only the facts supplied, address the customer by first name,
    never state a claim decision as final or guaranteed, end with the
    jurisdiction's required disclosure verbatim as the final sentence, keep
    it to 2-3 sentences, and assume claim/policy details are already on
    file rather than asking the customer for them), and a full
    jurisdiction-rulebook block (JURISDICTION_RULEBOOK_BLOCK, given above)
    marked cache_control ephemeral - Day 8 Lab-2's mechanic, reused because
    that block is byte-identical on every call this process makes. User
    content: customer's first name, jurisdiction code, action, and
    pending_question. IMPORTANT: pass `thinking={"type": "disabled"}` -
    claude-sonnet-5 reasons by default, and leaving it on eats the
    max_tokens budget before any visible text gets written. max_tokens=400.
    Return {"text": <stripped>, "stop_reason": response.stop_reason}.
    """
    raise NotImplementedError


def handle_request(request: dict) -> dict:
    """Given - the end-to-end path: resolve context, evaluate input+
    permission groups over the raw message, draft only if that passed,
    evaluate output+compliance groups over the draft (or the raw message's
    own text if permission already blocked - the audit layer still needs a
    payload to hash), and return one result dict per request."""
    context = resolve_context(request["actor_id"], request["customer_id"], request["action"], request["payout_amount"])
    context["run_groups"] = {"input", "permission"}
    context["precomposed_response"] = request.get("precomposed_response")

    pre_result = GuardrailStack.evaluate(request["message"], context)
    if pre_result["final_verdict"] == "BLOCK":
        return {
            "request_id": request["request_id"], "final_verdict": "BLOCK",
            "blocking_layer": pre_result["blocking_layer"], "payload": request["message"],
            "trail": pre_result["trail"], "redactions_applied": [],
        }

    draft = draft_claim_response(context)
    context["stop_reason"] = draft["stop_reason"]
    context["run_groups"] = {"output", "compliance"}
    post_result = GuardrailStack.evaluate(draft["text"], context)
    return {
        "request_id": request["request_id"], "final_verdict": post_result["final_verdict"],
        "blocking_layer": post_result["blocking_layer"], "payload": post_result["payload"],
        "trail": pre_result["trail"] + post_result["trail"], "redactions_applied": post_result["redactions_applied"],
    }


def run_corpus(requests: list[dict]) -> dict:
    """
    TODO 6: Run every request through handle_request and score it two ways -
    a guardrail stack fails in two directions:
      - MISSED BLOCKS: request["is_adversarial"] is True but the result's
        final_verdict is "PASS".
      - FALSE BLOCKS: request["is_adversarial"] is False but the result's
        final_verdict is "BLOCK".
    Also, wherever request["expected_blocking_layer"] is not None, check
    the result's blocking_layer matches it (collect mismatches). Wherever
    request["expected_redaction_layers"] is not None (an empty list counts -
    it asserts NO redaction happened), check the result's redactions_applied
    matches it AS A SET (collect mismatches). Return {"total": len(requests),
    "blocked": <count where final_verdict == "BLOCK">,
    "expected_blocked": <count where is_adversarial is True>,
    "missed_blocks": [request_ids], "false_blocks": [request_ids],
    "wrong_layer": [(request_id, expected, actual)],
    "redaction_mismatches": [(request_id, expected, actual)],
    "results": [every per-request result dict, in order]}.
    """
    raise NotImplementedError


def demo_tamper_detection() -> None:
    """Given - flips one field of an in-memory copy of entry index 2 (if
    the chain is long enough) and shows verify() catching it at exactly
    that index, then shows the chain STILL fails at index 3 even after
    "fixing" entry 2's own hash - because entry 3's prev_hash no longer
    matches. That second step is the whole difference between hashed and
    chained."""
    print("\n=== Demo: hash-chain tamper detection ===")
    chain = AUDIT_LOG._load()
    if len(chain) < 4:
        print(f"  Chain has only {len(chain)} entries - run the corpus first to build one long enough to demo.")
        return
    tampered = json.loads(json.dumps(chain))
    tampered[2]["inputs"]["payout_amount"] = 999999
    tmp_log = HashChainedAuditLog(AUDIT_LOG_FILE)
    tmp_log._save(tampered)
    ok, bad_index = tmp_log.verify()
    print(f"  After tampering entry 2's payout_amount: verify() -> ({ok}, {bad_index})")
    entry_copy = dict(tampered[2])
    entry_copy.pop("entry_hash")
    tampered[2]["entry_hash"] = hashlib.sha256((HashChainedAuditLog._canonical(entry_copy) + tampered[2]["prev_hash"]).encode("utf-8")).hexdigest()
    tmp_log._save(tampered)
    ok2, bad_index2 = tmp_log.verify()
    print(f"  After also 'fixing' entry 2's own hash: verify() -> ({ok2}, {bad_index2}) - "
          f"entry 3's prev_hash still points at the ORIGINAL entry 2, so the break just moves forward one entry.")
    tmp_log._save(chain)  # restore the real chain on disk


if __name__ == "__main__":
    print(f"=== Lab-2: Insurance Guardrail Stack — {len(REQUESTS)} requests ===\n")

    scorecard = run_corpus(REQUESTS)

    print(f"--- Corpus results ---")
    print(f"  {scorecard['blocked']}/{scorecard['total']} blocked (expected {scorecard['expected_blocked']} adversarial)")
    print(f"  Missed blocks: {scorecard['missed_blocks']}")
    print(f"  False blocks: {scorecard['false_blocks']}")
    print(f"  Wrong blocking layer: {scorecard['wrong_layer']}")
    print(f"  Redaction mismatches: {scorecard['redaction_mismatches']}")

    print(f"\n--- Per-request detail ---")
    for result in scorecard["results"]:
        redacted = f" redactions={result['redactions_applied']}" if result["redactions_applied"] else ""
        print(f"  {result['request_id']}: {result['final_verdict']:5} "
              f"(blocking_layer={result['blocking_layer']}){redacted}")

    chain_ok, chain_bad_index = AUDIT_LOG.verify()
    print(f"\n--- Audit chain ---")
    print(f"  {len(AUDIT_LOG._load())} entries, verify() -> ({chain_ok}, {chain_bad_index})")

    demo_tamper_detection()
