"""
PM · H2 — Telecom: Multilingual Journeys, Personas & Hand-off.

A "journey" spans more than one touch — a chat today, a voice call
tomorrow, maybe an SMS follow-up next week. If the agent starts from zero
on every touch, the customer re-explains their problem every time, and
that's the single most common complaint about "AI support" today. This lab
makes journey CONTINUITY a real object (JourneyMemoryStore) instead of a
concept: a fact extracted from a CHAT turn is available to the VOICE turn
that happens later, keyed on customer_id, not on channel or session.

LanguageRouter is "localisation" made concrete as data, not a hardcoded
if/elif per language: locale_policies.json carries the language, the
PERSONA tone (a Japanese-locale customer gets a more formal register than
a US one — same underlying agent, different persona), and the legal
disclosure string, all looked up once per turn and folded into the system
prompt. JourneyOrchestrator.advance_turn is a real Claude call per turn
that reads accumulated memory + persona and returns a forced-schema
decision: keep going, resolve, or escalate. HandoffPackager only fires on
escalate — it turns the full multilingual, multi-channel journey into an
English-language bundle a human agent (who may not speak the customer's
language) can act on immediately.
"""

import json
import sys
from pathlib import Path
from typing import Literal

from anthropic import Anthropic
from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

MODEL = "claude-sonnet-5"

DATA_DIR = Path(__file__).parent
with open(DATA_DIR / "locale_policies.json", encoding="utf-8") as f:
    LOCALE_POLICIES = json.load(f)

client = Anthropic()


class TurnResult(BaseModel):
    stage: Literal["diagnosing", "resolved", "escalate"] = Field(
        description="'diagnosing' if more info/troubleshooting is still needed, "
        "'resolved' if the issue is fixed, 'escalate' if this needs a human specialist."
    )
    reply: str = Field(description="The reply to send back to the customer, in their locale's language.")
    fact: str | None = Field(
        default=None,
        description="A short, durable fact worth remembering for the rest of this customer's "
        "journey across ANY channel (e.g. 'recurring evening outage, likely capacity-related'), "
        "or null if nothing new/durable came up this turn.",
    )


class HandoffSummary(BaseModel):
    summary: str = Field(description="2-3 sentence summary of the journey so far, in English.")
    key_facts: list[str] = Field(description="The durable facts a human agent needs, in English.")
    recommended_action: str = Field(description="What the human agent should do next, in English.")
    sentiment: Literal["positive", "neutral", "negative"]


class LanguageRouter:
    @staticmethod
    def route(locale: str) -> dict:
        """Given — looks up the persona/localisation bundle for a locale.
        Falls back to en-US if an unknown locale is passed rather than
        crashing mid-journey."""
        return LOCALE_POLICIES.get(locale, LOCALE_POLICIES["en-US"])


class JourneyMemoryStore:
    """Given — facts accumulate per customer_id, independent of which
    channel produced them. This is what makes the journey a JOURNEY
    instead of a series of unrelated sessions."""

    def __init__(self):
        self._facts: dict[str, list[str]] = {}

    def add_fact(self, customer_id: str, fact: str) -> None:
        self._facts.setdefault(customer_id, []).append(fact)

    def get_facts(self, customer_id: str) -> list[str]:
        return self._facts.get(customer_id, [])


class JourneyOrchestrator:
    def __init__(self, memory: JourneyMemoryStore):
        self.memory = memory

    def advance_turn(self, customer_id: str, channel: str, locale: str, utterance: str) -> TurnResult:
        """Real sonnet call, forced tool use. The system prompt folds in
        locale persona/disclosure AND accumulated cross-channel memory —
        the model sees facts from channels it never actually ran in."""
        persona = LanguageRouter.route(locale)
        known_facts = self.memory.get_facts(customer_id)
        system = (
            f"You are a telecom support agent. Respond in {persona['language_name']}. "
            f"Tone: {persona['tone']}. This is a multi-touch journey — the customer may have "
            f"contacted us before on a different channel. Known facts about this customer so far: "
            f"{known_facts or '(none yet)'}. Use them naturally; don't make the customer repeat "
            f"themselves if the answer is already in the known facts. Decide the stage: "
            f"'diagnosing' if you need more info or a fix hasn't been confirmed, 'resolved' if the "
            f"issue is fixed, 'escalate' if this needs a human specialist (e.g. a truck roll or "
            f"account-level exception). If something durable and worth remembering came up this "
            f"turn, capture it in `fact`; otherwise leave it null."
        )
        user = f"[channel: {channel}] {utterance}"
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": user}],
            tools=[{
                "name": "advance",
                "description": "Return this turn's stage, reply, and any durable fact to remember. "
                "ALL of stage and reply are required fields; fact may be null but must be present.",
                "input_schema": TurnResult.model_json_schema(),
            }],
            tool_choice={"type": "tool", "name": "advance"},
        )
        tool_call = next(b for b in response.content if b.type == "tool_use")
        result = TurnResult(**tool_call.input)
        if result.fact:
            self.memory.add_fact(customer_id, result.fact)
        return result


class HandoffPackager:
    @staticmethod
    def build_handoff(customer_id: str, locale: str, transcript: list[str], memory: JourneyMemoryStore) -> HandoffSummary:
        """Real sonnet call — the OUTPUT is deliberately always English,
        regardless of the customer's locale, because the human agent
        receiving this bundle may not speak the customer's language."""
        facts = memory.get_facts(customer_id)
        system = (
            "You summarize a multilingual customer support journey for a human agent who is "
            "taking over. Write summary, key_facts, and recommended_action in ENGLISH regardless "
            "of what language the customer spoke — the receiving agent may not read that language."
        )
        user = (
            f"Locale: {locale}\nKnown facts: {facts}\nTranscript so far (may include non-English "
            f"customer turns, translated inline):\n" + "\n".join(transcript)
        )
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": user}],
            tools=[{
                "name": "summarize_handoff",
                "description": "Return the structured handoff bundle for the human agent. All fields required.",
                "input_schema": HandoffSummary.model_json_schema(),
            }],
            tool_choice={"type": "tool", "name": "summarize_handoff"},
        )
        tool_call = next(b for b in response.content if b.type == "tool_use")
        return HandoffSummary(**tool_call.input)


if __name__ == "__main__":
    print("=== LanguageRouter across locales ===")
    for locale in LOCALE_POLICIES:
        persona = LanguageRouter.route(locale)
        print(f"  {locale}: {persona['language_name']} | tone={persona['tone'][:40]}... | disclosure=\"{persona['disclosure_text'][:30]}...\"")

    print("\n=== Journey: CUST-J1, ja-JP, chat then voice next day ===")
    memory = JourneyMemoryStore()
    orchestrator = JourneyOrchestrator(memory)
    transcript = []

    turn1 = orchestrator.advance_turn(
        "CUST-J1", "chat", "ja-JP",
        "My router keeps disconnecting every evening around 8pm, three nights in a row now.",
    )
    transcript.append(f"[chat] Customer: My router keeps disconnecting every evening around 8pm, three nights in a row now.")
    transcript.append(f"[chat] Agent: {turn1.reply}")
    print(f"Turn 1 (chat) -> stage={turn1.stage}")
    print(f"  Agent: {turn1.reply}")
    print(f"  Fact captured: {turn1.fact}")

    turn2_utterance = (
        "Hi, it's the same customer following up on the router issue from yesterday. It's now the "
        "fourth night in a row, I've already power-cycled the router twice and even swapped the "
        "ethernet cable — none of that helped. I want this escalated to a technician, not another "
        "round of basic troubleshooting."
    )
    turn2 = orchestrator.advance_turn("CUST-J1", "voice", "ja-JP", turn2_utterance)
    transcript.append(f"[voice] Customer: {turn2_utterance}")
    transcript.append(f"[voice] Agent: {turn2.reply}")
    print(f"\nTurn 2 (voice, next day) -> stage={turn2.stage}")
    print(f"  Agent: {turn2.reply}")
    print(f"  Fact captured: {turn2.fact}")
    print(f"  Memory now holds: {memory.get_facts('CUST-J1')}")

    label = "triggered by stage=escalate" if turn2.stage == "escalate" else f"demoed anyway (this run landed on stage={turn2.stage})"
    handoff = HandoffPackager.build_handoff("CUST-J1", "ja-JP", transcript, memory)
    print(f"\n=== Hand-off bundle (English, for the human agent) — {label} ===")
    print(f"  Summary: {handoff.summary}")
    print(f"  Key facts: {handoff.key_facts}")
    print(f"  Recommended action: {handoff.recommended_action}")
    print(f"  Sentiment: {handoff.sentiment}")

    print("\n=== Journey: CUST-J2, de-DE, single-touch resolution ===")
    memory2 = JourneyMemoryStore()
    orchestrator2 = JourneyOrchestrator(memory2)
    turn = orchestrator2.advance_turn(
        "CUST-J2", "chat", "de-DE",
        "Wie viel Datenvolumen habe ich diesen Monat noch uebrig?",
    )
    print(f"Turn (chat) -> stage={turn.stage}")
    print(f"  Agent: {turn.reply}")

# Expected: LanguageRouter prints a distinct persona/tone/disclosure per
# locale straight from locale_policies.json. CUST-J1's turn 1 (chat, ja-JP)
# should land on stage="diagnosing" and capture a fact about the recurring
# evening outage; turn 2 (voice, next day, SAME customer_id) should show
# the agent's reply referencing that history without the customer having
# re-explained it — check memory.get_facts('CUST-J1') has at least one
# entry BEFORE turn 2 runs. A recurring, unresolved multi-night outage is a
# plausible candidate for stage="escalate" (capacity/truck-roll issue a
# chat agent can't fix alone), in which case HandoffPackager produces an
# ENGLISH bundle even though the whole journey was conducted in Japanese —
# that's the point of building it as a separate, always-English call
# rather than just forwarding the transcript. CUST-J2's German request is
# a simple single-touch case — expect stage="resolved" or "diagnosing"
# depending on whether the model can answer a data-balance question with
# no account lookup tool available (it can't, so expect it to ask a
# clarifying question or explain it needs account access — either is a
# reasonable real-model answer, not a scripted one).
