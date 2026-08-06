"""
Lab-2: Insurance - One Guardrail Isn't a Guardrail Stack (SOLUTION).

Day 4 taught ONE guardrail: a single function that flags a message or it
doesn't. This lab replaces that with a STACK - nine ordered layers across
four groups (input, permission, output, compliance), each returning one of
three verdicts, not two: PASS (continue), BLOCK (stop), or REDACT (rewrite
the payload and keep going). That third verdict is the whole idea. A layer
that can only say yes or no is a filter. A layer that can hand the next
layer a DIFFERENT payload is a stack.

You'll build:
  1. Six guardrail layers (1a-1c: input/permission, 1e-1h: output/compliance) -
     the registry itself, and the always-runs audit layer, are given.
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
  5. handle_request / run_corpus - the end-to-end path, and a two-sided
     scorer: a guardrail stack fails in two directions (missing a real
     attack, or blocking a legitimate request), and only counting one of
     them is how you ship a stack nobody can use.
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
# layer's write path are given; the six layers below and the chain that
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
    """Case-insensitive substring scan against INJECTION_PATTERNS."""
    lowered = payload.lower()
    for pattern in INJECTION_PATTERNS:
        if pattern in lowered:
            return {"verdict": "BLOCK", "detail": f"matched injection pattern: {pattern!r}"}
    return {"verdict": "PASS", "detail": "ok"}


@register_guardrail("authority_claim_probe", group="input", order=20)
def guard_authority_claim(payload: str, context: dict) -> GuardrailResult:
    """Case-insensitive substring scan against AUTHORITY_CLAIM_PATTERNS - a
    message trying to talk its way past policy by claiming to BE a
    manager/supervisor/CEO, distinct from injection_probe's shape."""
    lowered = payload.lower()
    for pattern in AUTHORITY_CLAIM_PATTERNS:
        if pattern in lowered:
            return {"verdict": "BLOCK", "detail": f"matched authority-claim pattern: {pattern!r}"}
    return {"verdict": "PASS", "detail": "ok"}


@register_guardrail("rbac_action_allowed", group="permission", order=30)
def guard_rbac_action(payload: str, context: dict) -> GuardrailResult:
    """The coarse check - CAN this role ever do this action at all,
    regardless of which customer or how much money."""
    if context["action"] not in context["role"]["actions"]:
        return {"verdict": "BLOCK", "detail": f"role {context['role_name']!r} cannot perform action {context['action']!r}"}
    return {"verdict": "PASS", "detail": "ok"}


@register_guardrail("rbac_scope_and_authority", group="permission", order=40)
def guard_rbac_scope(payload: str, context: dict) -> GuardrailResult:
    """Two independent checks: SCOPE (is this customer in the actor's own
    book) and AUTHORITY (does the payout amount exceed the role's ceiling).
    Generalizes Day 4's per-user ownership check (`check_permission`'s
    "doesn't own it" branch survives here as the scope check) into
    something an org chart maps onto - role, not just user."""
    if context["role"]["scope"] == "own_customers_only" and context["customer_id"] not in (context["assigned_customers"] or []):
        return {"verdict": "BLOCK", "detail": f"customer {context['customer_id']} is not in {context['actor_id']}'s assigned book"}
    if context["action"] == "issue_payout" and context["payout_amount"] is not None:
        ceiling = context["role"]["max_payout_authority"]
        if context["payout_amount"] > ceiling:
            return {"verdict": "BLOCK", "detail": f"payout {context['payout_amount']} exceeds role ceiling {ceiling}"}
    return {"verdict": "PASS", "detail": "ok"}


@register_guardrail("generation_terminated_cleanly", group="output", order=50)
def guard_generation_terminated(payload: str, context: dict) -> GuardrailResult:
    """NEW SDK SURFACE. A truncated draft is not cosmetic here - the
    required disclosure is the LAST sentence, so max_tokens truncation is
    precisely how a compliance violation ships looking fine up front."""
    stop_reason = context.get("stop_reason")
    if stop_reason == "refusal":
        return {"verdict": "BLOCK", "detail": "stop_reason=refusal - the model's own safety layer fired"}
    if stop_reason == "max_tokens":
        return {"verdict": "BLOCK", "detail": "stop_reason=max_tokens - response was truncated before the disclosure"}
    return {"verdict": "PASS", "detail": f"stop_reason={stop_reason}"}


@register_guardrail("jurisdiction_disclosure_present", group="compliance", order=60)
def guard_jurisdiction_disclosure(payload: str, context: dict) -> GuardrailResult:
    """The first REDACT layer - TRANSFORMS and CONTINUES rather than
    terminating. Never BLOCKs: a missing disclosure is a fixable defect,
    not an attack."""
    jurisdiction = context["jurisdiction"]
    disclosure = jurisdiction["required_disclosure"]
    additions = []
    if disclosure.lower() not in payload.lower():
        additions.append(disclosure)
    if context["payout_amount"] is not None and context["payout_amount"] > jurisdiction["requires_written_confirmation_above"]:
        additions.append(WRITTEN_CONFIRMATION_SENTENCE)
    if not additions:
        return {"verdict": "PASS", "detail": "ok"}
    new_payload = payload.rstrip() + " " + " ".join(additions)
    return {"verdict": "REDACT", "detail": f"appended {len(additions)} sentence(s)", "payload": new_payload}


_POLICY_NUMBER_RE = re.compile(r"POL-IN-(\d+)")


@register_guardrail("role_scoped_field_leak", group="output", order=70)
def guard_field_leak(payload: str, context: dict) -> GuardrailResult:
    """The second REDACT layer, driven by IDENTITY rather than pattern -
    the same policy number is fine for a fraud investigator and not fine
    for tier-1 support. Runs AFTER the disclosure layer on purpose: the
    disclosure text is fixed and safe, so masking a payload the previous
    layer just extended means only one payload is ever in play."""
    if context["role"]["can_view_full_policy_number"]:
        return {"verdict": "PASS", "detail": "ok"}
    matches = _POLICY_NUMBER_RE.findall(payload)
    if not matches:
        return {"verdict": "PASS", "detail": "ok"}
    masked = _POLICY_NUMBER_RE.sub(lambda m: f"POL-IN-****{m.group(1)[-4:]}", payload)
    return {"verdict": "REDACT", "detail": f"masked {len(matches)} policy number(s)", "payload": masked}


@register_guardrail("prohibited_claim", group="compliance", order=80)
def guard_prohibited_claim(payload: str, context: dict) -> GuardrailResult:
    """Case-insensitive substring scan against THIS JURISDICTION'S
    prohibited_phrases, not a global list - one phrase in the corpus is
    legal in TX and illegal in CA/NY."""
    lowered = payload.lower()
    hits = [p for p in context["jurisdiction"]["prohibited_phrases"] if p in lowered]
    if hits:
        return {"verdict": "BLOCK", "detail": f"prohibited in {context['jurisdiction_code']}: {hits}"}
    return {"verdict": "PASS", "detail": "ok"}


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
        """The chain of responsibility: PASS continues, REDACT transforms
        and continues, BLOCK stops the walk - but the always_runs audit
        layer still fires regardless of how the walk ended."""
        trail = []
        blocking_layer = None
        ordered = sorted(_GUARDRAIL_REGISTRY, key=lambda l: l["order"])
        for layer in ordered:
            if layer["always_runs"]:
                continue
            if layer["group"] not in context["run_groups"]:
                continue
            result = layer["fn"](payload, context)
            trail.append({"layer": layer["name"], "verdict": result["verdict"], "detail": result["detail"]})
            if result["verdict"] == "REDACT":
                payload = result["payload"]
            elif result["verdict"] == "BLOCK":
                blocking_layer = layer["name"]
                break

        final_verdict = "BLOCK" if blocking_layer else "PASS"
        context["layer_trail"] = trail
        context["final_verdict_so_far"] = final_verdict
        for layer in ordered:
            if layer["always_runs"]:
                layer["fn"](payload, context)

        redactions_applied = [t["layer"] for t in trail if t["verdict"] == "REDACT"]
        return {"final_verdict": final_verdict, "blocking_layer": blocking_layer, "payload": payload,
                "trail": trail, "redactions_applied": redactions_applied}


class HashChainedAuditLog:
    """Given file I/O and canonical serialization - `append`/`verify` are
    yours (TODO 3/4)."""

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
        """Entry N's hash is computed OVER entry N-1's hash - that's what
        makes editing entry 2 invalidate 2, 3, 4 and everything after."""
        chain = self._load()
        entry = dict(entry)
        entry["entry_id"] = f"AUD-{len(chain) + 1:05d}"
        prev_hash = chain[-1]["entry_hash"] if chain else "0" * 64
        entry["prev_hash"] = prev_hash
        entry["entry_hash"] = hashlib.sha256((self._canonical(entry) + prev_hash).encode("utf-8")).hexdigest()
        chain.append(entry)
        self._save(chain)
        return entry

    def verify(self) -> tuple[bool, Optional[int]]:
        """Returns (True, None) if the whole chain checks out, else
        (False, <index of the FIRST entry that failed>) - an investigation
        tool, not just an alarm."""
        chain = self._load()
        prev_hash = "0" * 64
        for i, entry in enumerate(chain):
            if entry["prev_hash"] != prev_hash:
                return False, i
            entry_copy = dict(entry)
            stored_hash = entry_copy.pop("entry_hash")
            recomputed = hashlib.sha256((self._canonical(entry_copy) + entry["prev_hash"]).encode("utf-8")).hexdigest()
            if recomputed != stored_hash:
                return False, i
            prev_hash = stored_hash
        return True, None


AUDIT_LOG = HashChainedAuditLog()


JURISDICTION_RULEBOOK_BLOCK = (
    "JURISDICTION RULEBOOK (reference, applies to every claim response):\n" + json.dumps(JURISDICTIONS, indent=2)
)


def draft_claim_response(context: dict) -> dict:
    """Six of the sixteen requests carry a precomposed_response so the
    output/compliance layers can be graded deterministically; the rest get
    a real draft with prompt caching on the rulebook block (Day 8 Lab-2's
    mechanic, reused - that block is byte-identical on every call)."""
    if context.get("precomposed_response"):
        return {"text": context["precomposed_response"], "stop_reason": None}

    customer = context["customer"]
    first_name = customer["name"].split()[0]
    system = [
        {"type": "text", "text": (
            "You are an insurance claims assistant. In 2-3 short sentences: answer using only the facts "
            "supplied, address the customer by first name, never state a claim decision as final or "
            "guaranteed, and end your reply with the jurisdiction's required disclosure, verbatim, as the "
            "final sentence. Assume the claim/policy details referenced are already on file - do not ask "
            "the customer to provide them."
        )},
        {"type": "text", "text": JURISDICTION_RULEBOOK_BLOCK, "cache_control": {"type": "ephemeral"}},
    ]
    user = (
        f"Customer: {first_name}\nJurisdiction: {context['jurisdiction_code']}\n"
        f"Action: {context['action']}\nQuestion: {customer['pending_question']}"
    )
    # claude-sonnet-5 reasons by default; disable it here since a short,
    # policy-constrained claims reply doesn't need extended thinking, and
    # leaving it on eats the max_tokens budget before any text is written.
    response = client.messages.create(model=MODEL_DRAFT, max_tokens=400, system=system, thinking={"type": "disabled"},
                                       messages=[{"role": "user", "content": user}])
    text = next(b for b in response.content if b.type == "text").text.strip()
    return {"text": text, "stop_reason": response.stop_reason}


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
    """A guardrail stack fails in two directions - missing a real attack,
    or blocking a legitimate request - and only counting one of them is how
    you ship a stack nobody can use."""
    missed_blocks, false_blocks, wrong_layer, redaction_mismatches = [], [], [], []
    blocked = 0
    results = []
    for request in requests:
        result = handle_request(request)
        results.append(result)
        if result["final_verdict"] == "BLOCK":
            blocked += 1
        if request["is_adversarial"] and result["final_verdict"] != "BLOCK":
            missed_blocks.append(request["request_id"])
        if not request["is_adversarial"] and result["final_verdict"] == "BLOCK":
            false_blocks.append(request["request_id"])
        if request["expected_blocking_layer"] is not None and result["blocking_layer"] != request["expected_blocking_layer"]:
            wrong_layer.append((request["request_id"], request["expected_blocking_layer"], result["blocking_layer"]))
        if request["expected_redaction_layers"] is not None and set(result["redactions_applied"]) != set(request["expected_redaction_layers"]):
            redaction_mismatches.append((request["request_id"], request["expected_redaction_layers"], result["redactions_applied"]))
    return {
        "total": len(requests), "blocked": blocked,
        "expected_blocked": sum(1 for r in requests if r["is_adversarial"]),
        "missed_blocks": missed_blocks, "false_blocks": false_blocks,
        "wrong_layer": wrong_layer, "redaction_mismatches": redaction_mismatches,
        "results": results,
    }


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
