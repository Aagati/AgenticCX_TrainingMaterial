# Lab-2: Banking: Online QA with Sentiment + Escalation

**Track:** Banking | **Ships:** an online-QA summary report
**Pattern practiced:** three independent monitoring signals (resolution, sentiment, escalation) — deliberately not blended into one score

## Objective
Add an online QA layer to a simulated stream of 13 banking-support conversations: score resolution, track customer sentiment turn-by-turn to catch conversations that sour, and classify why conversations escalate.

## Steps
1. Open `conversations.json` and skim a few transcripts — notice how customer tone shifts across turns in some of them (e.g. **B13**).
2. In `qa_pipeline_starter.py`, implement `turn_sentiment()` using the provided `NEGATIVE_WORDS` / `POSITIVE_WORDS` lexicon.
3. Implement `sentiment_trend()` to produce a per-turn score list for each conversation's customer turns.
4. Implement `has_sharp_negative_shift()` — define what counts as "sharp" and justify it.
5. Implement `resolution_score()` using the `resolved` field.
6. Run `python qa_pipeline_starter.py`. Confirm conversation **B13** gets flagged for a sharp negative shift — if it doesn't, your threshold is too strict.
7. Look at the "Escalated but NOT sentiment-flagged" list the report produces. Discuss: why is it important to review these even though sentiment didn't flag them?

## Run
```bash
cd 02_Prelunch_H2_Banking_Online_QA
python qa_pipeline_starter.py      # participant version — raises NotImplementedError until the 4 
```
No API keys or external packages required — everything runs on the Python standard library.

## What "ships" means
A working `qa_pipeline_starter.py` producing an online-QA summary: resolution rate, sentiment-flagged conversation IDs, and an escalation-reason breakdown.

## Files
- `conversations.json` — 13 simulated banking-support conversations, each with per-turn `speaker`/`text`, a `resolved` flag, and (if applicable) `escalated`/`escalation_reason`.
- `qa_pipeline_starter.py` — 4 TODOs (`turn_sentiment`, `sentiment_trend`, `has_sharp_negative_shift`, `resolution_score`).
- `qa_pipeline_solution.py` — facilitator reference.

## Facilitator tips
- A lexicon this small will both over-flag (sarcasm, mixed signals) and under-flag (calm but firm dissatisfaction). That's a feature of this exercise, not a bug — use it to discuss why production systems use a model-based sentiment scorer, not a word list.
- Remind participants: resolution, sentiment and escalation are three independent signals. A conversation can be resolved **and** still deserve review (e.g. **B03**). Don't let trainees "fix" this by merging all three into one score — contrast directly against lab 01's `combined_score` design choice, where blending two lenses *was* the point.

## Stretch goal (optional)
Right now the lexicon only looks at customer turns. Extend it to also score AGENT turns — does agent tone ever make things worse (e.g. a flat, unempathetic reply following an angry customer message)?
