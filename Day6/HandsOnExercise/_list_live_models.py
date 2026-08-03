"""One-off diagnostic: list every model reachable via THIS project's
get_genai_client() helper -- Vertex AI first (GCP_CREDS_BASE64), AI Studio
key fallback (GEMINI_API_KEY/GOOGLE_API_KEY) -- same credential resolution
every Day6 lab already uses, so what you see here is exactly what a lab's
genai_client will see. location="us-central1" because aio.live.connect()
does not work on "global" (see _vertex_client.py's own docstring).

If GCP_CREDS_BASE64 is set, Vertex wins and GEMINI_API_KEY is ignored --
Vertex and AI Studio have DIFFERENT model catalogs, so to check the Studio
catalog instead, temporarily unset GCP_CREDS_BASE64 and rerun.

Run before hardcoding any model id in a lab -- preview ids churn and
differ per credential path/project.
"""
import os
import sys

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _vertex_client import get_genai_client

client, genai_types = get_genai_client(location="us-central1")
if client is None:
    print("No working Gemini credentials (checked GCP_CREDS_BASE64, then GEMINI_API_KEY/GOOGLE_API_KEY).")
    raise SystemExit(1)

backend = "Vertex AI" if os.environ.get("GCP_CREDS_BASE64") else "AI Studio"
print(f"Using {backend} credentials, location=us-central1.\n")

found = False
for m in client.models.list():
    actions = getattr(m, "supported_actions", None) or []
    if "bidiGenerateContent" in actions:
        found = True
        print(m.name, "->", actions)

if not found:
    print("No Live-API-capable (bidiGenerateContent) models found for this credential path.")
