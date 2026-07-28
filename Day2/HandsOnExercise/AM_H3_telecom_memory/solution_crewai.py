"""
AM · H3 — Telecom Cross-Session Memory (CrewAI VARIANT)

Same cross-session memory task as solution.py — reimplemented on CrewAI to
show a framework with memory as a first-class, built-in feature instead of
the hand-rolled JSON store in solution.py. One Agent, memory=True on the
Crew; CrewAI persists long-term memory to a local on-disk store between
kickoff() calls, so a second "session" (a second kickoff in the same
process, or even a fresh process run) recalls facts from the first.

Setup:
    pip install crewai sentence-transformers
    Uses ANTHROPIC_API_KEY (already in .env) for the chat model, via
    LiteLLM's "anthropic/<model>" string.
    CrewAI's long-term memory layer embeds facts for recall. Anthropic has
    no embeddings API, so this uses a local sentence-transformers embedder
    (all-MiniLM-L6-v2, CPU, no API key) instead of CrewAI's OpenAI default —
    keeps the whole exercise on just the Anthropic key.

Note: CrewAI's memory store lives in a local directory (~/.crewai or
CREWAI_STORAGE_DIR) — delete it if you want a clean-slate re-run, the same
role solution.py's os.remove(STORE_PATH) plays.
"""

import sys
from crewai import Agent, Crew, Task
from dotenv import load_dotenv

load_dotenv()  # LiteLLM reads ANTHROPIC_API_KEY from the environment

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

MODEL = "anthropic/claude-sonnet-5"

# Long-term memory recalls facts by SEMANTIC similarity, not exact key lookup
# the way solution.py's dict does — so it needs an embedding model. Anthropic
# ships no embeddings API, hence a local sentence-transformers model. First
# run downloads ~90MB; after that it's CPU-only and offline.
EMBEDDER = {
    "provider": "sentence-transformer",
    "config": {"model_name": "all-MiniLM-L6-v2"},
}

# role/goal/backstory are CrewAI's structured stand-in for a system prompt.
# Same content solution.py writes as one prose string — just decomposed into
# named slots the framework assembles for you.
support_agent = Agent(
    role="Telecom Support Agent",
    goal="Resolve the customer's request while remembering durable facts "
         "about them (device, plan, preferences) across conversations, "
         "never re-asking for something already known.",
    backstory="You've supported this customer base for years and pride "
              "yourself on never making a returning customer repeat "
              "themselves.",
    llm=MODEL,
    memory=True,
    verbose=False,
)

# memory=True on the Crew is the whole lab. This single flag replaces
# solution.py's extract_facts() + save_fact() + load_profile() + the JSON
# store — CrewAI does extraction, persistence, and retrieval internally.
#
# The trade-off worth discussing: you no longer control WHAT gets stored.
# solution.py's extract_facts() prompt is where you draw the line between
# durable ("Pixel 9a") and session-specific ("data is slow today"). Here that
# judgment is the framework's, and the store is opaque until you go read it.
crew = Crew(
    agents=[support_agent],
    tasks=[],
    memory=True,
    embedder=EMBEDDER,
    verbose=False,
)


def chat(customer_id: str, message: str) -> str:
    task = Task(
        description=(
            f"Customer (id={customer_id}) says: \"{message}\"\n\n"
            "Reply helpfully. If you recall durable facts about this "
            "customer from earlier conversations (device model, plan name, "
            "preferred contact method, etc.), use them naturally instead of "
            "asking again. Only recall facts that are actually durable — "
            "ignore one-off details like 'my data was slow today.'"
        ),
        expected_output="A short, natural support reply to the customer.",
        agent=support_agent,
    )
    # A fresh Task per message, swapped onto the existing crew. The crew (and
    # its memory) is long-lived; the task is the single turn. Rebuilding the
    # Crew here instead would work, but re-reads the store every call.
    crew.tasks = [task]
    result = crew.kickoff()
    return str(result)  # kickoff returns a CrewOutput, not a str


if __name__ == "__main__":
    cid = "cust_8842"

    print("=== SESSION 1 ===")
    msg1 = "Hi, my data has been really slow today. I'm on an iPhone 15, Unlimited Plus plan."
    print("CUSTOMER:", msg1)
    print("AGENT:", chat(cid, msg1))

    print("\n=== SESSION 2 (next day, new conversation) ===")
    msg2 = "Hey, I have a question about my bill."
    print("CUSTOMER:", msg2)
    print("AGENT:", chat(cid, msg2))
    print("\n(Check: CrewAI's long-term memory recalled the iPhone 15 / "
          "Unlimited Plus plan from session 1 without solution.py's manual "
          "extract_facts()+JSON-store bookkeeping.)")

# Expected: same behavior as solution.py's SESSION 2 — the agent already
# knows device + plan going in. The difference is *where* memory lives:
# solution.py's explicit extract_facts()/save_fact()/load_profile() vs.
# CrewAI's memory=True doing extraction, storage, and retrieval for you.
