# DOCS: STENTOR technical reference

## 1. Core schema

```python
from enum import Enum
from pydantic import BaseModel, Field

class Hazard(str, Enum):
    WILDFIRE="wildfire"; FLOOD="flood"; EARTHQUAKE="earthquake"; TSUNAMI="tsunami"
    HURRICANE="hurricane"; TORNADO="tornado"; EXTREME_HEAT="extreme_heat"
    HAZMAT="hazmat"; SHOOTER="active_threat"; BOIL_WATER="boil_water"; OTHER="other"

class Action(str, Enum):           # ordered by strength within a family
    EVACUATE_NOW="evacuate_now"
    PREPARE_TO_EVACUATE="prepare_to_evacuate"
    SHELTER_IN_PLACE="shelter_in_place"
    MOVE_TO_HIGHER_GROUND="move_to_higher_ground"
    STAY_INDOORS="stay_indoors"
    AVOID_AREA="avoid_area"
    BOIL_WATER="boil_water"
    MONITOR="monitor"
    ALL_CLEAR="all_clear"

class Instruction(BaseModel):
    verb: str                     # normalized English verb, e.g. "use", "return"
    object: str | None            # "elevators", "the area"
    negated: bool                 # True for "do NOT ..."
    placeholders: list[str] = []  # e.g. ["⟦T1⟧"]

class AlertIntent(BaseModel):
    hazard: Hazard
    action: Action
    urgency: str = Field(pattern="^(immediate|expected|future)$")
    area_refs: list[str]          # placeholder ids only
    time_refs: list[str]          # placeholder ids only
    expires: str | None           # placeholder id
    instructions: list[Instruction]
    info_refs: list[str] = []     # phone / URL placeholders
    source: str | None = None     # non critical
    extra_info: str | None = None # non critical
```

Critical slots: `hazard`, `action`, `area_refs`, `time_refs`, `expires`, `instructions[*].negated`, `instructions[*].verb` (normalized), `info_refs`.

## 2. Placeholder locking

| Type | Prefix | Detects |
|---|---|---|
| Time / date | `T` | `6:00 PM`, `18:00`, `tomorrow 8am` (dateparser + regex) |
| Place / street | `P` | proper nouns from intent extraction + gazetteer list |
| Number | `N` | counts, distances, wind speed |
| Phone / URL | `U` | `211`, `911`, URLs |

Format: `⟦T1⟧`. `lock.apply(text) -> (locked_text, mapping)`, `lock.restore(text, mapping, lang) -> text` (localizes time format per language, never the value).

Verification rule: `Counter(placeholders_in(rendered)) == Counter(mapping.keys())`.

## 3. Rendering

Router order:
1. **Template**: `lexicon/templates/{hazard}.{action}.{lang}.txt` exists → fill placeholders. Status starts as VERIFIED if template is marked `approved: true`.
2. **Adaption model**: `STENTOR_RENDERER=adaption` and language is supported by the trained model.
3. **LLM**: system prompt requires short imperative sentences, keep every `⟦…⟧` exactly once, never soften the action, keep every negation, reading level about grade 6.

Rendered output is always verified, including templates (cheap sanity check).

## 4. Action lexicon

`stentor/lexicon/{lang}.json`

```json
{
  "lang": "tl",
  "actions": {
    "evacuate_now": ["lumikas na ngayon", "lumikas kaagad"],
    "prepare_to_evacuate": ["maghanda sa paglikas"],
    "shelter_in_place": ["manatili sa loob"]
  },
  "weaker_than": {
    "evacuate_now": ["prepare_to_evacuate", "monitor"]
  },
  "negation_markers": ["huwag", "hindi"],
  "reviewed_by": "native speaker name or 'unreviewed'"
}
```

Mark every lexicon file with `reviewed_by`. Unreviewed lexicons are shown as such in the UI. Seed them with an LLM, then ask native speakers from Discord / friends to review the action phrases only (short list, fast to check).

Lexicon checks:
- `action_present`: some phrase for `intent.action` appears (case and diacritic insensitive).
- `no_weaker_action`: no phrase from a weaker action appears without the correct one.
- `negation_count`: number of negation markers ≥ number of negated instructions.

## 5. Back parse prompt (model B)

Input: rendered text in language L, language code, list of valid placeholders. The model is **not** shown the English source. Output: `AlertIntent` via tool use with the same JSON schema. Temperature 0.

## 6. Slot diff and status

```python
def status(src: AlertIntent, back: AlertIntent, checks: list[Check]) -> Status:
    if any(c.critical and not c.ok for c in checks): return BLOCKED
    if critical_diff(src, back): return BLOCKED
    if noncritical_diff(src, back): return REVIEW
    return VERIFIED
```

`critical_diff` compares enums exactly, placeholder lists as multisets, and instructions matched by normalized verb with `negated` equal.

On BLOCKED: render the hazard's generic safe template for L (`{hazard}.generic.{lang}`), verify it, mark language as `FALLBACK`.

## 7. API

| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/intent` | `{text}` | `{intent, locked_text, mapping}` |
| POST | `/compile` | `{intent, locked_text, mapping, langs[]}` | `{results: [{lang, text, status, checks[], diff, renderer}]}` |
| POST | `/export/cap` | `{alert_id}` | CAP XML |
| GET | `/alerts/{id}` | | full alert + audit |
| POST | `/eval/run` | `{langs[], suite}` | eval summary |
| GET | `/public/{id}?lang=` | | citizen page data |

## 8. Channels

**CAP 1.2**: one `<alert>`, one `<info>` per language with `<language>` (e.g. `vi`), `<category>`, `<event>`, `<urgency>`, `<severity>`, `<certainty>`, `<headline>`, `<description>`, `<instruction>`, `<expires>`, `<area><areaDesc>`. Only VERIFIED and FALLBACK languages are included. Add `<parameter>` `stentorStatus` and `stentorRenderer` per info block.

**SMS**: detect GSM-7 vs UCS-2; segment size 160 / 70 (153 / 67 when concatenated). Show segment count per language.

**Short alert budget**: configurable limit (default 360 chars) for wireless alert style text; if over, ask renderer for a compressed version and re-verify.

**Audio**: Web Speech API in browser with `lang` set; fall back to "audio not available for this language".

**Pictogram card**: SVG composed from hazard icon + action icon + time/place chips. Language independent, so it is the last resort for anyone.

## 9. Eval

`eval/suites/clean.jsonl`: 60 alerts (8 hazards, varied actions, 30% with negations).
`eval/suites/adversarial.jsonl`: each clean alert + one injected corruption of the rendered text:
`drop_negation`, `downgrade_action`, `shift_time`, `swap_place`, `swap_hazard`, `drop_placeholder`, `duplicate_placeholder`.

Metrics:
- Catch rate on adversarial (target 100% for critical)
- False block rate on clean
- Placeholder survival rate
- Slot match rate per renderer (baseline LLM vs Adaption model)

`eval/run_eval.py` writes `eval/results/*.json`; the dashboard reads the latest file. Only these numbers appear in the pitch.

## 10. Chaos mode (demo)

`POST /compile?chaos=drop_negation:ar` applies a corruption to one language after rendering and before verification. Used live to show the catch. Clearly labeled in the UI.

## 11. Accessibility checklist

- All controls keyboard reachable, visible focus
- `lang` and `dir` attributes on every rendered alert block
- Status never shown by color only (icon + word)
- Minimum 16px text, AA contrast, reduced motion respected
