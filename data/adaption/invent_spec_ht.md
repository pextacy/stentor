# Invent-a-Dataset spec: STENTOR alert renderer, Haitian Creole

Goal: a small model that renders English emergency alerts into Haitian Creole (`ht`)
without ever changing meaning. Backup language: Tagalog (`tl`).

Success is measured by STENTOR's own verifier (`eval/run_eval.py --force-model adaption`):
slot match rate and placeholder survival on the clean (60) and realistic (32) suites, compared with the
baseline LLM (`--force-model llm`). Nothing is claimed until both runs exist.

Coverage plan (~1,000 rows): 8 hazards (wildfire, flood, earthquake, tsunami, hurricane,
tornado, extreme heat, chemical hazard) x 10 actions/instruction families x negation
variants. At least 30% of rows contain a "do not" instruction.

Hard rules the data must teach:

1. Every placeholder (`⟦P1⟧`, `⟦T1⟧`, `⟦N1⟧`, `⟦U1⟧`) appears exactly once, unchanged.
2. The action is never softened ("evacuate now" never becomes "prepare to evacuate").
3. Every negation survives ("Do not" -> "Pa").
4. Short imperative sentences, about grade 6 reading level, no emoji, no added advice.

Seed data: `seed_ht.jsonl` (built by `adaption_track.py seed`) holds template-composed
pairs. Its Haitian Creole side comes from an LLM seeded, **unreviewed** lexicon; a native
speaker should review it before it is used as ground truth.

The text below the marker is sent as `dataset_prompt`.

---PROMPT---
Instruction data for an emergency alert translator. Each row: the input is a short English
public emergency alert (wildfire, flood, earthquake, tsunami, hurricane, tornado, extreme heat
or chemical hazard) written in plain imperative sentences, in which place names, times,
numbers, phone numbers and links are replaced by locked tokens such as ⟦P1⟧, ⟦T1⟧, ⟦N1⟧ and
⟦U1⟧. The output is the same alert in Haitian Creole. The output keeps every locked token
exactly once and unchanged, never softens the protective action (evacuate now, shelter in
place, move to higher ground, stay indoors, avoid the area, boil water), keeps every negation
such as "do not use elevators" or "do not return until ⟦T1⟧", uses short plain sentences at
about a grade 6 reading level, and adds no advice that is not in the input. About a third of
rows include at least one "do not" instruction. Vary hazards, actions, sentence order and
the number of locked tokens.
