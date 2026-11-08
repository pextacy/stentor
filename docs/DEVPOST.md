# Devpost submission draft

## Project name
STENTOR

## Short description (one line)
Every emergency warning, in every language, verified by machine before it is sent.

## Inspiration
In January 2025, as fire moved through Los Angeles, alerts went out only in English and
Spanish. County officials said the system they use supports only those two languages
([Planetizen](https://www.planetizen.com/news/2025/02/134255-language-matters-addressing-communication-gaps-disaster-response)).
The FCC approved multilingual Wireless Emergency Alerts in 2023, then delayed them in 2025.
The National Weather Service paused its AI translation of alerts, and in 2026 a GAO review
raised concerns about AI translating disaster warnings.

Translation is not the hard part. Trust is. A wrong alert is worse than no alert: drop one
"not" from "Do not use elevators" and you have told people to do the dangerous thing. An
operator who speaks one language cannot proofread ten. So agencies send English only, and
the people last to understand are the people last to leave.

## What it does
The operator writes one alert in English. STENTOR:

1. Reads its meaning into an Alert Intent: hazard, required action, places, times, expiry,
   and every instruction with a "negated" flag.
2. Locks every literal (place names, streets, times, numbers, phone numbers, links) as a
   placeholder such as ⟦P1⟧, so no model can translate or change them.
3. Renders each language: approved templates first, then a fine tuned model, then a
   general model.
4. Verifies each rendering: every placeholder exactly once, the approved action phrase
   present and not softened, enough negation markers, and a back parse by a different model
   that never sees the English. The back parsed intent is compared slot by slot.
5. Marks each language Verified, Review or Blocked. A blocked language gets the
   pre-approved generic warning for that hazard ("Wildfire warning. Evacuate now. Info: 211.")
   instead of silence or a wrong message.
6. Exports CAP 1.2 XML with one `<info>` block per sendable language, shows SMS segment
   counts, plays audio, draws a language independent pictogram card and publishes a public
   alert page with right to left support for Arabic.

Live in the demo: chaos mode drops the "not" from the Arabic rendering. STENTOR turns
Arabic to safe fallback, the slot ledger shows Negations ✕, and the struck through blocked
text sits next to what will actually be sent.

## How we built it
- Backend: Python 3.11, FastAPI, Pydantic v2, SQLModel and SQLite for alerts and the audit
  log. The Alert Intent schema is the source of truth; TypeScript types are generated from
  the OpenAPI schema.
- Claude API: Claude Opus 5.5 extracts the intent (strict JSON schema output) and renders
  text the templates cannot express. Claude Sonnet 5.5, a different model, back parses, so
  the renderer and the checker do not share blind spots.
- Deterministic core: per language lexicons of action phrases and negation markers, a
  template renderer, a lexicon back parser and seven corruption types for chaos mode and
  the eval. Everything works without an API key.
- Frontend: Next.js 14, TypeScript, Tailwind. Status is never shown by colour alone, every
  rendered block carries `lang` and `dir`, and it works by keyboard.
- Adaption: an Invent-a-Dataset spec and a 4,224 pair template seed set for a Haitian
  Creole alert renderer, plus scripts for cost estimate, generation and an AutoScientist
  run, scored by STENTOR's own verifier.

## Challenges
- Getting negation detection right per language: folding diacritics in Vietnamese turns
  "dùng" (use) into a false "đừng" (do not), so negation matching is diacritic sensitive.
- Our own eval caught a real bug: an alert with no explicit action sentence ("Drop, cover
  and hold on") was blocked in every language. The implied action is now made explicit on
  the intent card. That case is now a regression test.
- Right to left text: "211." jumped to the wrong side in Arabic until each restored literal
  was wrapped in a Unicode directional isolate.

## Accomplishments
- In our eval (60 alerts × 5 languages, deterministic path), all 1,640 injected critical
  errors were blocked, with no clean rendering blocked. We publish the limits next to the
  numbers: without a key, renderer and checker share a lexicon, so this shows the checks
  fire, not that translations are good.
- A standards compliant CAP 1.2 file with one info block per language.

## What we learned
Make the dangerous failure its own slot. Negation and action strength get dedicated checks
because they are the failures that hurt people.

## What's next
- Native speaker review of every lexicon, starting with Haitian Creole and Tagalog.
- Run the model renderer eval (baseline vs Adaption fine tuned) and publish it.
- More languages: the method needs only a lexicon and templates per language.

## Built with
python, fastapi, pydantic, sqlmodel, sqlite, claude-api, anthropic, next.js, typescript,
tailwindcss, cap-1.2, adaption, web-speech-api

## Screenshots (docs/screenshots)
03-results.png (console), 04-arabic-blocked.png (blocked diff), 06-public-ar.png (Arabic
public page), 05-citizen.png (phone preview), 08-eval.png (eval), docs/samples/demo.cap.xml
