"""
AM · H3 — Telecom Cross-Session Memory (CrewAI VARIANT)

Same cross-session memory task as solution.py — reimplemented on CrewAI to
show a framework with memory as a first-class, built-in feature instead of
the hand-rolled JSON store in solution.py. One Agent, memory=True on the
Crew; CrewAI persists long-term memory to a local on-disk store between
kickoff() calls, so a second "session" (a second kickoff in the same
process, or even a fresh process run) recalls facts from the first.

Setup:
    pip install crewai
    Uses ANTHROPIC_API_KEY (already in .env) for the chat model, via
    LiteLLM's "anthropic/<model>" string.
    CrewAI's long-term memory layer embeds facts for recall and defaults to
    OpenAI embeddings — set OPENAI_API_KEY in .env (same placeholder added
    for the Day1 GPT variant) or this will raise on first kickoff.

Note: CrewAI's memory store lives in a local directory (~/.crewai or
CREWAI_STORAGE_DIR) — delete it if you want a clean-slate re-run, the same
role solution.py's os.remove(STORE_PATH) plays.
"""

import os
import sys
from crewai import Agent, Crew, Task

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

if not os.environ.get("OPENAI_API_KEY"):
    raise RuntimeError(
        "OPENAI_API_KEY not set. CrewAI's long-term memory layer embeds "
        "facts with OpenAI embeddings by default - add a key to .env "
        "(same placeholder used for the Day1 GPT variant)."
    )

MODEL = "anthropic/claude-sonnet-5"

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

crew = Crew(agents=[support_agent], tasks=[], memory=True, verbose=False)


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
    crew.tasks = [task]
    result = crew.kickoff()
    return str(result)


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
