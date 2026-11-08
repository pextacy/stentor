# DOCS: STENTOR technical reference

This describes the system as built. Code paths are relative to `services/api/stentor/`.

## 1. Core schema (`intent/schema.py`)

```python
class Hazard(str, Enum):  wildfire flood earthquake tsunami hurricane tornado extreme_heat
                          hazmat active_threat boil_water other
class Action(str, Enum):  evacuate_now prepare_to_evacuate shelter_in_place move_to_higher_ground
                          stay_indoors avoid_area boil_water monitor all_clear

class Instruction(BaseModel):
    verb: str               # normalized English verb: "return", "use", or an action verb
    object: str | None      # "elevators", "until_cleared"; for evacuate/prepare: "via" | "to"
    negated: bool           # True for "do NOT ..." and for implied prohibitions
    placeholders: list[str] # ids bound to this instruction, in text order

class AlertIntent(BaseModel):
    hazard: Hazard
    action: Action                # the main protective action
    urgency: str                  # immediate | expected | future   (non critical)
    area_refs: list[str]          # every ⟦P⟧
    time_refs: list[str]          # every ⟦T⟧
    expires: str | None           # the ⟦T⟧ for when the alert itself ends
    instructions: list[Instruction]
    info_refs: list[str]          # every ⟦U⟧
    number_refs: list[str]        # every ⟦N⟧
    event_refs: list[str]         # every ⟦E⟧ (storm names)
    source: str | None            # non critical
    extra_info: str | None        # non critical
```

Action verbs: evacuate, prepare, shelter, move, stay, avoid, boil, monitor, all_clear.
`WEAKER_THAN` lists dangerous softenings (evacuate_now -> prepare_to_evacuate, monitor; ...).

**Critical slots:** hazard, action, area_refs, time_refs, info_refs, number_refs, event_refs,
expires, negations (the negated instructions), instructions.

**Every alert states its action.** If the source has no action sentence ("Drop, cover and
hold on."), `ensure_action_instruction` adds the implied action to the intent card so the
operator sees it, and the alert goes to Review because the action was assumed.

## 2. Placeholder locking (`lock/locker.py`)

| Kind | Token | Detects |
|---|---|---|
| Time / day | `⟦T1⟧` | `6:00 PM`, `18:00`, `3 p.m.`, `3 pm tomorrow`, `tomorrow 8am`, `7 PM tonight`, `5 PM Friday`, `Friday`, `noon` |
| Place | `⟦P1⟧` | operator markers `⟦Altadena⟧`; names after near/in/at/for/from/via/to...; streets (`Lake Ave`, `5th Street`, `St. Mary School`, `Mt. Wilson`); routes (`I-5`, `Highway 101`, `Exit 132`) |
| Quantity | `⟦N1⟧` | `2 miles`, `one minute`, `3 minutes`, bare numbers |
| Phone / link | `⟦U1⟧` | `211`, `911`, `112` and other short codes, `(602) 555-0134`, `1-800-555-1234`, URLs and domains |
| Event name | `⟦E1⟧` | `Milton` in `Hurricane Milton` |

Priority on overlap: U > T > E > P > N, then the longer span. Each occurrence gets its own
token. Abbreviation dots (`St.`, `Mt.`) are kept inside places, and `p.m.` at the end of a
sentence leaves the sentence period in place.

`restore(text, mapping, lang)` puts values back and localizes only the format:

| | vi | tl | ko | ar | ht | es | tr |
|---|---|---|---|---|---|---|---|
| `6:00 PM` | 18:00 | 6:00 PM | 오후 6:00 | 6:00 م | 6:00 PM | las 18:00 | 18:00 |
| `3 pm tomorrow` | 15:00 ngày mai | 3:00 PM bukas | 내일 오후 3:00 | غدًا 3:00 م | 3:00 PM demen | las 15:00 de mañana | yarın 15:00 |
| `Friday` | thứ Sáu | Biyernes | 금요일 | الجمعة | vandredi | el viernes | Cuma |
| `2 miles` | 2 dặm | 2 milya | 2마일 | 2 ميلان | 2 mil | 2 millas | 2 mil |

In right-to-left languages each literal is wrapped in Unicode isolates (U+2068 ... U+2069) so
`211.` cannot be reordered. `finalize()` capitalizes sentence starts after restoring
(Turkish `i` -> `İ`); it runs after verification and only changes letter case.

Verification rule: `Counter(placeholders_in(rendered)) == Counter(placeholders_in(source))`,
and after restore every localized literal must appear as often as its token did.

## 3. Rendering (`render/router.py`, `render/template.py`)

Router order:
1. **Templates** when they express the whole alert (`coverage()` below).
2. **Adaption model** when `STENTOR_RENDERER=adaption` and a trained model supports the language.
3. **Claude** (`claude-opus-5-5`) with a strict prompt: short imperative sentences, keep every
   token once, never soften the action, use the lexicon's action phrase and negation words.
4. No model available: templates anyway, but the language goes to **Review** with the words
   the templates drop listed.

The template renderer composes, in order: headline, expiry, the action sentence (if no
instruction carries it), each instruction, then an info line for each phone/link not used by
an instruction. Headline variants: plain, with places (several are joined with the language's
list separator), with a distance (`Wildfire ⟦N1⟧ from ⟦P1⟧`), with an event name
(`Hurricane ⟦E1⟧`), and a cancelled form for all-clear messages. Action variants are keyed by
placeholder kinds and role: `""`, `P` (route), `P:to` (destination), `T`, `TT`, `N`.
Instruction variants: `neg`, `pos`, `neg|T`, `pos|P`, `pos|U`.

**Coverage.** The English rendering of the intent must say everything the source says. A
source word counts as covered if the English rendering contains it or it belongs to a
phrase the lexicon recognized ("take shelter", "flash flood", "turn around, don't drown").
Anything else ("if safe", "without windows", a lower case place name) is listed and the
alert goes to Review.

**Safe fallback.** `render_generic()` = hazard headline + action sentence + info lines. It
drops places, times and names on purpose so it is always expressible, and it is verified
against the reduced intent it expresses.

## 4. Lexicon format (`lexicon/{lang}.json`)

```jsonc
{
  "lang": "vi", "name": "Tiếng Việt", "english_name": "Vietnamese", "dir": "ltr", "tts": "vi-VN",
  "reviewed_by": "unreviewed",            // a native speaker's name once checked
  "fold_diacritics": false,               // Vietnamese: diacritics change meaning
  "word_boundary": true,                  // false for Korean and Turkish (suffixes)
  "negation_markers": ["không", "đừng", "chớ", "cấm"],
  "negation_drop": [["지 마십시오", "십시오"]],   // optional: how chaos removes a suffix negation
  "split_clauses": false, "split_colon": false,   // English only
  "list_sep": ", ",
  "role_markers": {"via": ["theo đường"], "to": ["đến"]},
  "headline": "Cảnh báo {name}.", "headline_place": "Cảnh báo {name} tại {P}.",
  "headline_distance": "...", "headline_all_clear": "...", "headline_all_clear_place": "...",
  "event_name": "{name} {E}",
  "time": {"style": "24h", "day_position": "after", "day_words": {...}, "weekdays": [...]},
  "units": {"minute": "phút", ...}, "unit_format": "{n} {u}",
  "hazards": {"wildfire": {"name": "cháy rừng", "terms": ["đám cháy"]}, ...},
  "actions": {"evacuate_now": {"match": ["sơ tán ngay"],
                               "text": {"": "Sơ tán ngay.", "P": "Sơ tán ngay theo đường {P}.", "P:to": "...", "T": "..."}}, ...},
  "instructions": {"use:elevators": {"match": ["thang máy"], "text": {"neg": "KHÔNG đi thang máy."}},
                   "go:beach": {"match": [...], "implied_neg": ["stay away from the beach"], "text": {...}},
                   "use:route": {"match": [...], "needs": "P", "text": {"pos|P": "..."}}, ...},
  "info": {"match": ["thông tin"], "text": "Thông tin: {U}."},
  "expires": {"match": ["có hiệu lực đến"], "text": "Cảnh báo này có hiệu lực đến {T}."}
}
```

Eight lexicons ship: en (source), vi, tl, ko, ar, ht (the PRD set), es, tr. Each has 11
hazards, 9 actions and 30 instruction types. File order of `instructions` is priority.
Where the script has case and the negation is a separate word, it is written in capitals
(NOT, KHÔNG, HUWAG, PA, NO).

`tests/test_lexicon.py` enforces, for every language: all keys and variants present; every
template reads back to exactly the intent it was rendered from (over 1,000 combinations per
language); negation markers only in negated templates; and the role word next to a place
tells route from destination.

## 5. Parsing and back parsing (`verify/backparse.py`)

The same deterministic parser reads the English source (no key) and the translations (lexicon
back parser). It is never shown the English when reading a translation.

1. **Sentences.** Split on `. ! ? ؟`, protecting abbreviation dots. English also splits
   `Heat wave in ⟦P1⟧: stay indoors` at the colon, but keeps `Info: ⟦U1⟧` together.
2. **Clauses.** An English sentence with more than one instruction is split on commas, `;`
   and `and`, so in "Evacuate now and do not use elevators" the "not" belongs to the second
   clause only.
3. **Matches.** All action and instruction phrases are found. On overlap the longer phrase
   wins ("stay away from the beach" beats the action "stay away from"). Hazard terms are
   blanked before action matching, so "boil water notice" is not the boil action. In one
   clause a specific key beats the generic key of the same verb (`return:until_cleared` over
   `return`); different objects are both kept ("medications and pets").
4. **Negation** is per clause: a marker in the clause, or an `implied_neg` phrase.
5. **Binding.** Instructions take the placeholders of their clause that their templates can
   hold. For evacuate/prepare a place is a route only next to a via-word, a destination only
   next to a to-word; otherwise it is the affected area ("Evacuate now from Altadena",
   "residents of ⟦P1⟧ must evacuate").
6. **Main action** = the earliest action phrase, including headline forms ("EVACUATION
   ORDER"). Other action phrases become instructions with their own verbs. Exact duplicate
   instructions are dropped ("Evacuation order. Leave now.").

With a Claude key, back parsing uses `claude-sonnet-5-5` (a different model from the
renderer) with the same JSON schema, told the language and the valid tokens only. If that
call fails, the language is blocked.

## 6. Checks, slot diff and status (`verify/checks.py`, `verify/diff.py`)

Checks on the rendered (locked) text, all critical except length and coverage:

| Check | Fails when |
|---|---|
| placeholders | any token missing, extra or duplicated |
| action_present | no approved phrase for the main action |
| no_weaker_action | a weaker action's phrase appears without the right one |
| negation_count | fewer negation markers than negated instructions |
| literals_restored | a localized literal is missing after restore |
| length (non critical) | over 360 characters; with a key, a compressed version is requested and verified again |
| template_coverage (non critical) | templates were used although they drop source words |

Slot diff: enums exact; placeholder lists as multisets; instructions as multisets of
`(verb, object, negated, placeholders)` where placeholders keep their order within a kind
("between ⟦T1⟧ and ⟦T2⟧" is not "between ⟦T2⟧ and ⟦T1⟧").

```python
if any critical check fails or any critical slot differs: BLOCKED -> try safe fallback -> FALLBACK
elif any non critical check fails or slot differs:        REVIEW (not sent automatically)
else:                                                       VERIFIED
```

Reasons are written in plain language, shown on the card and stored in the audit log.

## 7. API (`main.py`)

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/health` | | status, version, which keys are configured (never values) |
| GET | `/meta` | | languages with lexicon summary, examples, corruption types, English phrasebook |
| POST | `/intent` | `{text}` | `{intent, locked_text, mapping, method, warnings, template_coverage, uncovered}` |
| POST | `/compile?chaos=drop_negation:ar` | `{intent, locked_text, mapping, langs[]}` | `{alert_id, source_text, intent, results[]}` |
| GET | `/alerts?limit=` | | recent alerts with per language status |
| GET | `/alerts/{id}` | | full alert + audit log |
| POST | `/export/cap` | `{alert_id}` | CAP 1.2 XML |
| GET | `/public/{id}?lang=` | | citizen page data, sendable languages only |
| POST | `/eval/run` | `{langs[], suites[]}` | eval summary (only without an API key) |
| GET | `/eval/latest`, `/eval/renderers` | | latest eval file; model renderer comparison |

`/compile` de-duplicates languages, rejects an empty list, rejects chaos aimed at a language
that is not compiled, and rebuilds the English source text from the locked text, so the
stored, exported and public English is always the text that was verified.

## 8. Channels (`channels/`)

**CAP 1.2:** one `<alert>` (status `Exercise`), one `<info>` for English plus one per
VERIFIED or FALLBACK language, with language, category, event, responseType, urgency,
severity, certainty, expires (clock time today, tomorrow if already past, weekday = end of that
day; left out if unparseable), senderName, headline, description, instruction, web (the
public page in that language), parameters `stentorStatus` and `stentorRenderer`, and area.
Datetimes use an explicit offset (`-00:00` for UTC).

**SMS:** GSM-7 vs UCS-2, 160/70 characters for one segment, 153/67 per segment after that.

**Audio:** Web Speech API with the language's voice; the UI says so when a device has none.

**Pictogram:** SVG from hazard icon + action icon + one tile per prohibition with an icon
(elevators, flood water, return, outside, tap water, fires, power lines, door, beach, damaged
buildings, windows, waiting) + place and time chips.

## 9. Eval (`evaluation.py`, `eval/run_eval.py`)

Suites:
- `eval/suites/clean.jsonl`: 60 alerts in template wording, 8+ hazards, 29 with negations.
- `eval/suites/realistic.jsonl`: 32 alerts with messy wording and every bug found in review,
  each with a note. These are also unit tests (`tests/test_realistic.py`).

Each alert has an expected hazard, action, negation count and status. Every rendering is then
corrupted in each applicable way: `drop_negation`, `downgrade_action`, `shift_time` (swap two
times or invent one), `swap_place` (swap places with different roles or invent one),
`swap_hazard`, `drop_placeholder`, `duplicate_placeholder`.

Metrics: catch rate, wrongly blocked rate on clean renderings, status as expected, review
rate, literal survival, intent read accuracy, per language, per suite, per corruption.
`--force-model llm|adaption` switches templates off to measure a model renderer
(`eval/results/renderer-*.json`). Only these numbers appear in the pitch.

## 10. Chaos mode

`POST /compile?chaos=drop_negation:ar` applies one corruption to one language after rendering
and before verification. Clearly labelled in the UI; the chaos language always follows the
selected languages.

## 11. Accessibility

- All controls keyboard reachable, visible focus ring (3px ink + tape yellow halo)
- `lang` and `dir` on every rendered alert block; literals isolated in RTL text
- Status never by colour alone: icon + word everywhere, slot ledger cells carry ✓/✕ + label
- 16px base text, AA contrast palette, reduced motion respected, no horizontal scroll at 390px
