"""
Shared Gemini client init for the Day 6 labs.

Tries Vertex AI first (GCP_CREDS_BASE64 service account — real GCP billing,
works even when the AI Studio key's free-tier quota is exhausted), then
falls back to the AI Studio key (GEMINI_API_KEY/GOOGLE_API_KEY). Returns
(None, None) if neither is usable, so callers keep their existing
"genai_client is None -> simulate" fallback untouched.

Two things this project's Vertex catalog gets you wrong if you copy the
AI-Studio-style names/defaults:
  1. Model id: this project's actual native-audio Live model (verified via
     client.models.list()) is `gemini-live-2.5-flash-native-audio`, not the
     AI-Studio-style `gemini-2.5-flash-native-audio-preview-<date>` id.
     `gemini-3.1-flash-live-preview` (the multimodal-live id some labs use)
     is NOT in this project's catalog at all — no id/region fix helps that
     one, it's a genuine access gap.
  2. Location: `aio.live.connect()` (the websocket/bidi Live API) does not
     work on `location="global"`, even though plain `generate_content()`
     does and is what get_genai_client() defaults to. Live calls need a
     real region — confirmed working on "us-central1". Use
     get_genai_client(location="us-central1") for labs whose ONLY genai
     usage is native-audio Live (AM_H1, AM_H2, PM_H3); leave the default
     "global" for labs that call generate_content (tool use, grounding,
     plain text turns).
"""

import base64
import json
import os
import wave


def save_pcm_wav(pcm_bytes: bytes, path: str, sample_rate: int = 24000) -> str:
    """Gemini Live's AUDIO response modality returns raw PCM (confirmed
    mime_type="audio/pcm" on this project) at 24kHz/16-bit/mono per the
    Live API spec — wrap it in a .wav header so any player can open it.
    Returns the path written."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sample_rate)
        f.writeframes(pcm_bytes)
    return path


def get_genai_client(location: str = "global"):
    gcp_b64 = os.environ.get("GCP_CREDS_BASE64")
    if gcp_b64:
        try:
            from google import genai
            from google.oauth2 import service_account

            sa_info = json.loads(base64.b64decode(gcp_b64))
            creds = service_account.Credentials.from_service_account_info(
                sa_info, scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
            client = genai.Client(
                vertexai=True,
                project=sa_info["project_id"],
                location=location,
                credentials=creds,
            )
            from google.genai import types as _types

            return client, _types
        except Exception as exc:
            print(f"Vertex AI setup failed ({exc}) — trying AI Studio key.")

    studio_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if studio_key:
        try:
            from google import genai
            from google.genai import types as _types

            client = genai.Client(http_options=_types.HttpOptions(api_version="v1alpha"))
            return client, _types
        except Exception as exc:
            print(f"AI Studio Gemini setup failed ({exc}) — falling back to simulation.")

    return None, None


def get_gemini_chat_model(model_name: str, tools=None):
    """LangChain-compatible chat model for nodes that need .bind_tools()/
    .invoke() (e.g. PM_H2's langgraph node). Same Vertex-first, Studio-key
    fallback order as get_genai_client(). Returns None if neither works."""
    gcp_b64 = os.environ.get("GCP_CREDS_BASE64")
    if gcp_b64:
        try:
            from google.oauth2 import service_account
            from langchain_google_genai import ChatGoogleGenerativeAI

            sa_info = json.loads(base64.b64decode(gcp_b64))
            creds = service_account.Credentials.from_service_account_info(
                sa_info, scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
            llm = ChatGoogleGenerativeAI(
                model=model_name,
                vertexai=True,
                project=sa_info["project_id"],
                location="global",
                credentials=creds,
            )
            return llm.bind_tools(tools) if tools else llm
        except Exception as exc:
            print(f"Vertex AI chat-model setup failed ({exc}) — trying AI Studio key.")

    studio_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if studio_key:
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI

            llm = ChatGoogleGenerativeAI(model=model_name, google_api_key=studio_key)
            return llm.bind_tools(tools) if tools else llm
        except Exception as exc:
            print(f"AI Studio chat-model setup failed ({exc}) — falling back to simulation.")

    return None
