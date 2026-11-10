# Devpost submission

As submitted to the CTRL-V hackathon (10 Nov 2026).

- **Project:** STENTOR
- **Elevator pitch:** Every emergency warning, in every language, verified by machine before it is sent.
- **Try it out:** https://stentor-taupe.vercel.app · https://github.com/pextacy/stentor
- **Video:** https://youtu.be/AwZFp-BBr54
- **Built with:** python, fastapi, pydantic, sqlmodel, sqlite, typescript, next.js, react, tailwindcss, vercel, gemini, claude, adaption, cap-1.2

# About the project

### Inspiration
In January 2025, as fire moved through Los Angeles, emergency alerts went out only in English and Spanish. County officials said the system they use supports only those two languages ([Planetizen](https://www.planetizen.com/news/2025/02/134255-language-matters-addressing-communication-gaps-disaster-response)). The FCC approved multilingual Wireless Emergency Alerts in 2023, then delayed them. The National Weather Service paused its AI alert translation program, and in early 2026 a GAO review raised concerns about AI translating disaster warnings.

Translation is not the hard part. **Trust is.** A wrong alert is worse than no alert: drop one "not" from "Do not use elevators" and you have told people to do the dangerous thing. An operator who reads one language cannot proofread ten. So agencies send English only, and the people last to understand are the people last to leave.

### What it does
The operator writes one alert in plain English. STENTOR:

1. **Reads** its meaning into an Alert Intent: hazard, required action, places, times, expiry, and every instruction with a `negated` flag.
2. **Locks** every literal (places, streets, zones, times, numbers, phone numbers, links, plates) as a placeholder like `⟦P1⟧`, so nothing can translate or change them.
3. **Translates** with approved phrase templates first, and a model only for what the templates cannot say.
4. **Reads every translation back**, without seeing the English, and **compares it slot by slot**: every placeholder exactly once, the approved action phrase present and not softened, the right number of negations, same hazard, places, times and instructions.
5. Marks each language **Verified**, **Review** or **Blocked**. A blocked language gets the pre-approved generic warning for that hazard instead of silence or a wrong message.
6. Exports **CAP 1.2** XML with one `<info>` block per language, SMS segment counts, audio, a language independent pictogram card, and a public alert page with right to left support for Arabic.

In the demo, chaos mode deletes the "not" from the Arabic translation after it is written and before it is checked. STENTOR blocks it, strikes the broken text through, and sends the safe warning instead.

### How we built it
- **Backend:** Python 3.11, FastAPI, Pydantic v2, SQLModel + SQLite for alerts and a full audit log (every decision stores its reason).
- **Deterministic core:** per language lexicons of action phrases and negation markers, a template renderer, a role-aware back parser (route vs destination vs affected area, clause-level negation), and seven corruption types for chaos mode and the eval. It runs with no API key.
- **Model layer:** one strict JSON-schema interface that works with Claude or Gemini. The renderer and the back parser are deliberately *different* models so they don't share blind spots.
- **Frontend:** Next.js 14, TypeScript, Tailwind. Status is never shown by color alone, every rendered block carries `lang` and `dir`, and everything works by keyboard.
- **Adaption:** we used Invent-a-Dataset to generate a 1,994-row Haitian Creole alert dataset, plus a 6,732-pair template seed set, for training a small alert renderer scored by STENTOR's own verifier.
- **Deploy:** web and API both on Vercel.

### Challenges we ran into
- **Our own review found dangerous bugs.** "Evacuate now *from* Altadena" was rendered as a route, "St. Mary School" was split in two, and in "Evacuate now and do not use elevators" the "not" landed on the evacuation. Each one is fixed and is now a regression test. The fix that mattered most: places bind by role, and negation belongs to a clause, not a sentence.
- **A silent negation drop.** Probing with alerts beyond our demo, we found a sentence like "Do not go to the hospital unless it is an emergency" could be dropped by the templates and still reach Review. Now any "not", "unless" or "except" the templates would drop **blocks** the language.
- **The first real model run failed, safely.** With Gemini on the free tier, the back parser mapped meaning into the wrong slots, so even the demo alert was blocked in most languages. Nothing wrong was sent, which is the point of the design, but the model path is not demo ready yet. The demo runs the deterministic path, and we say so.
- **Diacritics and direction.** Folding Vietnamese diacritics turned "dùng" (use) into a false "đừng" (do not), so negation matching is diacritic sensitive. In Arabic, "211." jumped to the wrong side until each restored literal was wrapped in a Unicode directional isolate.

### Accomplishments that we're proud of
- In our eval (99 alerts × 7 languages, 693 translations, deterministic path), **all 3,682 injected critical errors were blocked**, **0 of 420 clean translations of plain alerts were wrongly blocked**, and every alert landed on exactly the status we expected.
- We publish the limits next to the numbers: without a model, the renderer and the checker share one lexicon, so this shows the checks fire on every known failure type, not that translation is good. Lexicons are not yet reviewed by native speakers.
- A standards compliant CAP 1.2 file with one info block per language.

### What we learned
Make the dangerous failure its own slot. Negation and action strength get dedicated checks, because they are the failures that hurt people. And when the checker is unsure, blocking is the feature, not the bug.

### What's next
- Native speaker review of every lexicon, starting with Haitian Creole and Tagalog.
- Fix the model back parser (canonical slot keys per placeholder) and publish the baseline vs Adaption fine-tuned renderer eval.
- More languages: the method needs only a lexicon and templates per language.

# Additional info (judges only)

## What role did AI play in your project?

AI plays three roles, and we kept each one honest about its limits.

1. Inside the product, AI is never trusted on its own. STENTOR's whole idea is that machine translation must be checked before it is sent. Approved phrase templates render what they can; a language model (Claude or Gemini, behind one strict JSON-schema interface) only renders what the templates cannot express. Every output is then read back into a structured intent by a different model, plus deterministic lexicon checks, and compared slot by slot. Anything that does not match is blocked. In our first real Gemini run the model back parser over-blocked; nothing wrong was sent, and the live demo runs the deterministic path until we fix it. We say this openly in the README.

2. For data, we used Adaption's Invent-a-Dataset to generate a 1,994-row Haitian Creole alert dataset for a small, specialized alert renderer, scored by STENTOR's own verifier.

3. For building, we used an AI coding assistant (Claude Code) heavily: writing and reviewing code, probing the pipeline with realistic alerts, finding bugs (for example a dropped "not" that could reach Review), and producing the demo video narration with text-to-speech. The lexicons were drafted with an LLM and are marked "unreviewed" everywhere until a native speaker checks them.

## Who is your target audience?

Emergency managers and alert originators who must warn people in many languages but read only one or two: city and county emergency offices, universities, schools, hospitals, campgrounds and NGOs. They get one alert in, every language checked, and a standard CAP 1.2 file out.

The people they serve: residents with limited English, refugees and migrants, tourists, and minority language speakers, who are usually the last to understand a warning and the last to leave. The public alert page, audio, large text and pictogram card also serve low literacy, Deaf and hard of hearing readers.

Language access coordinators are the third group: STENTOR makes their approved wording reusable in every alert and shows them exactly which language needs a person.
