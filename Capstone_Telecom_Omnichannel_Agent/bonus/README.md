# Bonus Tiers - ungraded, take-home, no solution files

**Complete Parts 0-6 in `starter/` first.** Everything here assumes a working
`starter/permissions.py`, `starter/guardrails.py`, `starter/mcp_server.py`,
`starter/agent_team.py`, and `starter/cost.py` - the scripts in this folder
import from `starter/` directly (each one adds `../starter` to `sys.path`
automatically, no file copying needed).

All three tiers below are **ungraded and open-ended by design**, for the
same three reasons `Day4/HandsOnExercise/Capstone_Banking_MCP_Agent`'s
Part 4 red-team section is:

1. A LangGraph/Agent-SDK/voice "solution" would rot faster than the raw-SDK
   reference code above it, and a voice solution can't be verified without
   a live Deepgram key plus real audio hardware.
2. The red-team tier's pedagogy *depends on there being no answer key* -
   see `red_team_challenge.py`'s own docstring.
3. The user framed all three of these as extra credit. Deterministic
   grading would silently make them required and blow the time-box past a
   single day.

Only exception: `red_team_challenge_INSTRUCTOR_REFERENCE.py`, gitignored
(`**/red_team_challenge_INSTRUCTOR_REFERENCE.py`), headed **DO NOT SHARE
WITH CANDIDATES** - same convention as the Day4 capstone's own instructor
reference.

---

## Tier A - Red Team Challenge

```
python red_team_challenge.py       # your own defense, scored against 6 novel attacks
python red_team_live_fire.py       # attack the REAL live agent (needs ANTHROPIC_API_KEY)
```

`red_team_kb_docs.json` has 6 techniques, none of which the required Part 5
guardrails are built to catch (confirmed: the given baseline scores 0/6).
Rewrite `your_defense_layer()` in `red_team_challenge.py` to catch as many
as you reasonably can, **and be ready to explain the ones you don't catch**.

**Grading signal is judgment, not the raw score.** A low score with a clear
write-up of *why* a technique is hard to catch, and *what it would cost in
false positives* to catch it, is worth more than a high score with no
reasoning.

Discussion questions (facilitator-led, no code required to answer):

- RT-01 is a confused-deputy attack across the handoff chain itself, not
  against a single tool. `red_team_live_fire.py` fires a keyword-free
  version of this at the real agent - did the STRUCTURAL role gate
  (`secure_call_tool`'s allowlist) hold even when your text filter had
  nothing to match? That's the one result that actually matters here; a
  model that simply "chose" not to comply proves nothing about the gate.
- RT-03 stuffs the exact vocabulary your own `retrieve()` scores on. Is
  there a way to defend against relevance-poisoning that doesn't involve
  changing the retrieval algorithm itself?
- RT-05's homoglyph attack defeats any check keyed on the literal string
  `apply_billing_credit`. What's the false-positive risk of Unicode
  normalization against a genuinely multilingual customer base?
- If you only had budget to ship ONE new defense layer before a real
  launch, which of the 6 would you pick, and what risk are you accepting
  by skipping the other five?

---

## Tier B - Voice Channel

```
python voice_channel_bonus.py
```

**Must use real Deepgram if attempted - no simulated fallback.** The point
of this bonus is proving Day2's "channel-agnostic core" claim with an
actually-different input modality, not asserting it. Reuses:

- The real Deepgram Nova-3 STT / Aura TTS calling convention from
  `Day3/HandsOnExercise/AM_H1_banking_latency/solution.py`.
- The AI-disclosure + recording-consent gate from
  `Day3/HandsOnExercise/PM_H3_telecom_compliance/solution.py` - required by
  this capstone's own `TEL-POL-02` KB doc, and the live target of the
  red-team tier's RT-06.
- `agent_team.run_turn()` **completely unmodified** - if you find yourself
  editing it to make voice work, that's a real finding, not a shortcut to
  take.

Setup needs `DEEPGRAM_API_KEY` in the repo-root `.env`, `pip install -r
../../requirements-voice.txt` (installed **second**, after the root
`requirements.txt` - see that file's own header comment on why order
matters), and 1-2 short WAV files - see the script's own docstring.

Discussion questions:

- What in `agent_team.py` had to change to support this channel? (The
  honest answer should be "nothing" - if it's not, why not?)
- Extra credit inside the extra credit: gate a money-moving action on a
  *spoken* confirmation, not just a transcribed "yes." What's actually
  different about verifying spoken consent versus a typed one?

---

## Tier C - Alt-Stack Reimplementation

```
python agent_team_langgraph.py           # needs: pip install langgraph langchain-anthropic
python agent_team_claude_agent_sdk.py    # needs: pip install claude-agent-sdk (already pinned at repo root)
```

Both are **scaffolds, not finished reimplementations** - the graph/options
wiring is real and verified against the installed packages, but the
tool-calling node bodies are marked TODO. **Both must talk to the SAME
unmodified `starter/mcp_server.py`** (spawned exactly the way
`agent_team.main()` does) **and reuse `starter/permissions.py` /
`starter/guardrails.py` / `starter/cost.py` as-is** - only the
orchestration layer is allowed to change.

Discussion questions:

- Which of `agent_team.secure_call_tool()`'s hand-written checks did the
  framework's native primitives (`can_use_tool`, `PreToolUse` hooks,
  `AgentDefinition.tools` as a capability allowlist) make genuinely
  redundant, and which did they not cover at all? "The framework handles
  security" is not an answer - name the specific check.
- `agent_team_claude_agent_sdk.py`'s `can_use_tool` callback calls
  `permissions.check_permission()` **unchanged**. Did the SDK replace any
  of Part 2's logic, or just give it a different place to live?
- The Claude Agent SDK has a documented gotcha: a tool present in an
  `AgentDefinition`'s `tools` allowlist can silently **shadow**
  `can_use_tool` entirely (`CanUseToolShadowedWarning`), turning a
  permission callback into a no-op that every offline unit test would
  still pass. Deliberately trigger this once so you know what it looks
  like before it bites you in a real deployment.
