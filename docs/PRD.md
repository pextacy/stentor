# PRD: STENTOR

**Every warning, in every language, verified before it is sent.**

Hackathon: CTRL-V (theme: making access easier). Deadline: 11 Nov 2026, 01:00 GMT+3.

## 1. Problem

When a wildfire, flood or earthquake hits, the emergency alert is often the only thing standing between a family and the danger. In many places that alert arrives in one or two languages.

- During the January 2025 Los Angeles fires, alerts went out only in English and Spanish, and county officials said the FEMA maintained system they use supports only those two languages. ([Planetizen](https://www.planetizen.com/news/2025/02/134255-language-matters-addressing-communication-gaps-disaster-response), [LAist via Rep. Barragán](https://barragan.house.gov/2025/05/27/laist-trump-delays-multilingual-emergency-alerts-for-natural-disasters-prompting-criticism-in-la-county/))
- The FCC approved multilingual Wireless Emergency Alerts in October 2023, then delayed implementation in 2025. ([LA Times via Rep. Barragán](https://barragan.house.gov/2025/05/27/los-angeles-times-trumps-fcc-delays-multilingual-emergency-alerts-for-natural-disasters-sparking-concern-in-l-a/))
- The National Weather Service paused its AI alert translation program after a contract lapse, and in early 2026 a GAO review raised concerns about AI translation of disaster warnings. ([EHN / Washington Post](https://www.ehn.org/u-s-pauses-weather-alerts-translation-leaving-non-english-speakers-at-risk-during-disasters), [E&E News](https://www.eenews.net/articles/gao-national-weather-service-sputters-on-non-english-weather-alerts), [Smart Cities Dive](https://www.pulse.bot/govtech/news/can-ai-close-the-language-gap-in-disaster-warnings-a-federal-watchdog-raises-concerns-4acac5d3-0028-469c-a4fa-b5de93593d85))
- Research shows many alerts are incomplete, too complex, or English only. ([PreventionWeb](https://www.preventionweb.net/quick/99877))

The problem is global: refugee and migrant communities after the 2023 Türkiye earthquakes, tourists during wildfires in the Mediterranean, minority language speakers everywhere.

### The real blocker is trust, not translation

Machine translation already exists. Agencies do not use it for alerts because **a wrong alert is worse than no alert**. "Evacuate" rendered as "prepare to evacuate", a dropped "do not", a shifted time or a swapped street name can kill people. No one can read 10 languages to check. So agencies default to English only.

**STENTOR's insight:** make translation *verifiable by a machine at the level of meaning*, so an operator who speaks only English can trust what is sent in Tagalog.

## 2. Users

| User | Need |
|---|---|
| **Emergency manager / alert originator** (city, county, university, NGO, campground, school) | Send one alert fast, in all community languages, with confidence nothing was distorted |
| **Resident with limited English** | Understand what to do, where, and by when, in their own language |
| **Low literacy or Deaf/hard of hearing resident** | Pictogram card and audio / large text versions |
| **Language access coordinator** | Maintain approved templates and an action lexicon per language |

## 3. Solution overview

1. Operator types or pastes an alert in English (or picks a template).
2. STENTOR **extracts an Alert Intent**: hazard, action, negations, area, time window, expiry, source, instructions.
3. Operator confirms the intent card (one glance, all in English).
4. Literals (times, streets, numbers, phone numbers) are **locked** as placeholders.
5. Each language is **rendered**: approved template if one exists, otherwise the Adaption fine tuned alert model, otherwise a general LLM.
6. Each rendering is **back parsed** into an Alert Intent and **diffed slot by slot** against the original.
7. Languages get a status: `VERIFIED`, `REVIEW` (non critical drift), `BLOCKED` (critical slot mismatch). Blocked languages fall back to a pre approved generic safe template for that hazard ("Danger: wildfire. Evacuate now. Info: ⟦URL⟧") rather than nothing.
8. Output: CAP 1.2 XML with one `<info>` per language, SMS segments, audio, pictogram card, public web page.

## 4. Features

### Must have (demo)
- F1 Alert composer with intent card
- F2 Placeholder locking for literals
- F3 Rendering into at least 5 languages (Vietnamese, Tagalog, Korean, Arabic RTL, Haitian Creole)
- F4 Back parse + slot diff verification with color coded per slot report
- F5 Negation and action strength checks (lexicon based)
- F6 CAP 1.2 XML export with multilingual `<info>` blocks
- F7 Citizen preview: phone mockup showing the alert in the selected language + audio playback
- F8 Eval dashboard: verification results on our test set, including adversarial cases

### Should have
- F9 Pictogram card (hazard icon + action icon + arrow/time) for low literacy users
- F10 SMS segment calculator (GSM-7 vs UCS-2, 160/70 chars) and channel length budgeting
- F11 Adaption trained alert renderer for one low resource language (Haitian Creole) with before/after eval

### Won't have (this hackathon)
- Real delivery to carriers or IPAWS
- Login, multi tenant orgs
- Sign language video

## 5. Why this wins each prize category

| Criterion (weight) | How STENTOR scores |
|---|---|
| **Impact (30%)** | Life safety, measurable access gap, cited current news, global relevance. Works for any language Adaption supports (242). |
| **Innovation (25%)** | Not "a translator". Translation as a *compiled, verified* artifact: meaning lock, slot diff, negation guard, safe fallback. Directly answers the GAO concern about AI translation. |
| **Technical (25%)** | Structured extraction, placeholder locking, round trip verification, CAP standard output, Adaption fine tuning with a published eval. |
| **UX (10%)** | One screen for the operator, accessible citizen view, RTL, audio, pictograms. |
| **Presentation (10%)** | A demo with a visible "caught it" moment: a model output silently drops "do not", STENTOR blocks it. |

Sponsor fit: uses Adaption's Invent-a-Dataset, Adaptive Data translation, and AutoScientist, which also qualifies us for their credit prizes.

## 6. Success metrics (for the demo)

- On our adversarial eval set, **100% of injected critical errors are caught** (negation drop, action downgrade, time shift, place swap, hazard swap).
- False block rate on clean translations reported honestly (target under 15%).
- Operator can go from typed alert to verified 5 language CAP file in under 60 seconds.

## 7. Non goals

STENTOR does not replace human language access staff. It makes their approved work reusable and flags what needs them. It is not certified for production alerting.

## 8. Risks

| Risk | Mitigation |
|---|---|
| Back parsing model shares the same blind spots as the renderer | Use a different model for back parsing than for rendering; lexicon checks are deterministic |
| Adaption training takes too long | Model renderer is optional; LLM fallback keeps the demo working |
| Over blocking | REVIEW tier for non critical slots, safe fallback template for BLOCKED |
| Claims about accuracy | Only show numbers from our own eval |
