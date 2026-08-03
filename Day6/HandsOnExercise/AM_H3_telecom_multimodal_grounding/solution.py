"""
AM · H3 — Telecom: Real-Time Multimodality + Tool Use & Grounding (REFERENCE SOLUTION)

Three Gemini capabilities, one telecom device-support scenario (a customer's
router status light):
  1. Real-time multimodality — one Live API turn that takes an IMAGE (a
     photo of the router's status light) and a spoken/text question
     TOGETHER, not as two separate round trips.
  2. Tool use — function calling against a local device-diagnostics lookup.
  3. Grounding — the Google Search tool, for questions the model's training
     data can't answer (current outage status, today's date-sensitive info).

No camera in the classroom, so `make_status_png()` generates a real, valid
PNG in pure stdlib (no Pillow) standing in for "customer sends a photo" —
solid color = router light color. Every Gemini call is REAL if
GEMINI_API_KEY/GOOGLE_API_KEY is set, with a deterministic simulated
fallback otherwise.
"""

import json
import os
import struct
import sys
import zlib
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Non-live model for the function-calling and grounding rounds; check
# ai.google.dev/gemini-api/docs/models for the current recommended flash id.
TEXT_MODEL = "gemini-flash-latest"

# Live-capable model for the real-time multimodal (image+text) turn — this
# one doesn't need the native-audio-dialog variant, any Live model handles
# streamed audio/video/text. Check ai.google.dev/gemini-api/docs/live-api
# for the current id before class.
MULTIMODAL_LIVE_MODEL = "gemini-3.1-flash-live-preview"

ROUTER_LIGHT_COLORS = {
    "red": (220, 20, 20),
    "amber": (230, 160, 20),
    "green": (30, 180, 60),
}

DATA_DIR = Path(__file__).parent
with open(DATA_DIR / "diagnostics_kb.json") as f:
    DIAGNOSTICS_DB = json.load(f)

GET_DIAGNOSTICS_DECL = {
    "name": "get_diagnostics",
    "description": "Look up the known issue and recommended fix for a router status-light color.",
    "parameters": {
        "type": "object",
        "properties": {"light_color": {"type": "string", "enum": ["red", "amber", "green"]}},
        "required": ["light_color"],
    },
}

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _vertex_client import get_genai_client

genai_client, genai_types = get_genai_client()
if genai_client is None:
    print("No working Gemini credentials — all three paths will use simulation.")


def make_status_png(rgb: tuple, size: int = 64) -> bytes:
    """Given — pure-stdlib minimal PNG encoder (no Pillow). Returns a
    real, valid solid-color PNG standing in for a photo of a router's
    status light."""
    def chunk(chunk_type: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(
            ">I", zlib.crc32(chunk_type + data)
        )

    r, g, b = rgb
    raw_row = b"\x00" + bytes([r, g, b]) * size
    raw = raw_row * size
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)  # 8-bit truecolor
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


def get_diagnostics(light_color: str) -> dict:
    return DIAGNOSTICS_DB.get(light_color, {"issue": "unknown", "fix": "escalate to a technician"})


def run_diagnostics_tool_call(user_question: str) -> dict:
    """Real function-calling round: the model decides whether to call
    get_diagnostics based on the question, we execute it locally."""
    if genai_client is None:
        for color in DIAGNOSTICS_DB:
            if color in user_question.lower():
                return {"tool_called": True, "light_color": color, "result": get_diagnostics(color), "real": False}
        return {"tool_called": False, "light_color": None, "result": None, "real": False}

    tool = genai_types.Tool(function_declarations=[GET_DIAGNOSTICS_DECL])
    config = genai_types.GenerateContentConfig(
        tools=[tool],
        system_instruction="You are a telecom device-diagnostics assistant. "
        "Use get_diagnostics when the caller mentions a router light color.",
    )
    response = genai_client.models.generate_content(model=TEXT_MODEL, contents=user_question, config=config)

    call = next(
        (p.function_call for c in response.candidates for p in c.content.parts if p.function_call),
        None,
    )
    if call is None:
        return {"tool_called": False, "light_color": None, "result": None, "real": True}

    args = dict(call.args)
    light_color = args.get("light_color", "")
    return {"tool_called": True, "light_color": light_color, "result": get_diagnostics(light_color), "real": True}


def run_grounded_search(query: str) -> dict:
    """Real Google Search grounding round: an up-to-date, cited answer
    instead of whatever the model memorized at training time."""
    if genai_client is None:
        return {"text": f"(simulated) General troubleshooting steps for: {query}", "citations": [], "real": False}

    tool = genai_types.Tool(google_search=genai_types.GoogleSearch())
    config = genai_types.GenerateContentConfig(tools=[tool])
    response = genai_client.models.generate_content(model=TEXT_MODEL, contents=query, config=config)

    citations = []
    if response.candidates and response.candidates[0].grounding_metadata:
        chunks = response.candidates[0].grounding_metadata.grounding_chunks or []
        citations = [c.web.uri for c in chunks if c.web]
    return {"text": response.text, "citations": citations, "real": True}


def _run_multimodal_turn(image_bytes: bytes, question_text: str) -> str:
    """MULTIMODAL_LIVE_MODEL isn't in this project's Vertex catalog (no
    id/region combination reaches it — confirmed via client.models.list()).
    TEXT_MODEL is real and multimodal-capable via plain generate_content,
    so image+question still go in as ONE call, just not over the Live
    websocket. Same "real-time multimodality" point (model sees both
    together), minus the streaming transport."""
    image_part = genai_types.Part.from_bytes(data=image_bytes, mime_type="image/png")
    config = genai_types.GenerateContentConfig(
        system_instruction="You are a telecom support agent. The customer sent a "
        "photo of their router's status light plus a question — use both together.",
    )
    response = genai_client.models.generate_content(
        model=TEXT_MODEL, contents=[image_part, question_text], config=config,
    )
    return response.text or "(no text reply returned)"


def run_multimodal_turn(image_bytes: bytes, question_text: str, light_color_hint: str) -> dict:
    if genai_client is not None:
        try:
            reply = _run_multimodal_turn(image_bytes, question_text)
            return {"reply": reply, "real": True}
        except Exception as exc:
            print(f"Gemini multimodal call failed ({exc}) — falling back to simulated multimodal reply.")

    diag = get_diagnostics(light_color_hint)
    reply = (
        f"(simulated) I can see the light is {light_color_hint} — that usually "
        f"means {diag['issue']}. Try this: {diag['fix']}"
    )
    return {"reply": reply, "real": False}


if __name__ == "__main__":
    print("=== Real-time multimodality: image + question, one turn ===")
    for color_name, rgb in ROUTER_LIGHT_COLORS.items():
        img = make_status_png(rgb)
        result = run_multimodal_turn(img, "What's wrong with my internet? Here's a photo of my router.", color_name)
        print(f"\n[{color_name} light, {len(img)}-byte PNG, {'real' if result['real'] else 'sim'}]")
        print(f"  {result['reply']}")

    print("\n=== Tool use: function calling for device diagnostics ===")
    for q in ["My router light is red and nothing works.", "Is my plan eligible for a loyalty discount?"]:
        result = run_diagnostics_tool_call(q)
        print(f"\n\"{q}\"")
        print(f"  tool_called={result['tool_called']} ({'real' if result['real'] else 'sim'})", end="")
        if result["tool_called"]:
            print(f" light_color={result['light_color']} -> {result['result']}")
        else:
            print()

    print("\n=== Grounding: Google Search tool for current info ===")
    result = run_grounded_search("What is a typical current outage-status page for a major ISP called?")
    print(f"  ({'real' if result['real'] else 'sim'}) {result['text'][:400]}")
    if result["citations"]:
        print(f"  Citations: {result['citations'][:3]}")

# Expected: all 3 router-light PNGs produce a distinct diagnosis matching
# ROUTER_LIGHT_COLORS/DIAGNOSTICS_DB (red -> "no internet connection", amber
# -> "degraded signal", green -> "no issue detected") whether real or
# simulated. The diagnostics tool call fires (tool_called=True) on the
# router-light question and should NOT fire on the loyalty-discount
# question (no light color mentioned, no matching tool). The grounded
# search call, when real, returns citations pointing at live web sources —
# in simulation citations is always empty, which is itself worth noticing:
# a fallback can't fabricate real grounding, so a "no key" run should never
# be mistaken for a genuinely grounded answer.
