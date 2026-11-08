"""AlertIntent: the structured meaning of an alert. Source of truth for diffing."""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Hazard(str, Enum):
    WILDFIRE = "wildfire"
    FLOOD = "flood"
    EARTHQUAKE = "earthquake"
    TSUNAMI = "tsunami"
    HURRICANE = "hurricane"
    TORNADO = "tornado"
    EXTREME_HEAT = "extreme_heat"
    HAZMAT = "hazmat"
    SHOOTER = "active_threat"
    BOIL_WATER = "boil_water"
    OTHER = "other"


class Action(str, Enum):  # ordered by strength within a family
    EVACUATE_NOW = "evacuate_now"
    PREPARE_TO_EVACUATE = "prepare_to_evacuate"
    SHELTER_IN_PLACE = "shelter_in_place"
    MOVE_TO_HIGHER_GROUND = "move_to_higher_ground"
    STAY_INDOORS = "stay_indoors"
    AVOID_AREA = "avoid_area"
    BOIL_WATER = "boil_water"
    MONITOR = "monitor"
    ALL_CLEAR = "all_clear"


# Canonical English verb for the instruction that carries the main action.
ACTION_VERB: dict[Action, str] = {
    Action.EVACUATE_NOW: "evacuate",
    Action.PREPARE_TO_EVACUATE: "prepare",
    Action.SHELTER_IN_PLACE: "shelter",
    Action.MOVE_TO_HIGHER_GROUND: "move",
    Action.STAY_INDOORS: "stay",
    Action.AVOID_AREA: "avoid",
    Action.BOIL_WATER: "boil",
    Action.MONITOR: "monitor",
    Action.ALL_CLEAR: "all_clear",
}

VERB_ACTION: dict[str, Action] = {v: a for a, v in ACTION_VERB.items()}
# Actions whose place placeholder is a route ("via") or a destination ("to").
ROUTE_ACTIONS = {Action.EVACUATE_NOW, Action.PREPARE_TO_EVACUATE}

# Actions that are a dangerous softening of the key action.
WEAKER_THAN: dict[Action, list[Action]] = {
    Action.EVACUATE_NOW: [Action.PREPARE_TO_EVACUATE, Action.MONITOR],
    Action.SHELTER_IN_PLACE: [Action.MONITOR],
    Action.MOVE_TO_HIGHER_GROUND: [Action.PREPARE_TO_EVACUATE, Action.MONITOR],
    Action.STAY_INDOORS: [Action.MONITOR],
    Action.AVOID_AREA: [Action.MONITOR],
    Action.BOIL_WATER: [Action.MONITOR],
    Action.PREPARE_TO_EVACUATE: [Action.MONITOR],
}

DEFAULT_URGENCY: dict[Action, str] = {
    Action.EVACUATE_NOW: "immediate",
    Action.PREPARE_TO_EVACUATE: "expected",
    Action.SHELTER_IN_PLACE: "immediate",
    Action.MOVE_TO_HIGHER_GROUND: "immediate",
    Action.STAY_INDOORS: "immediate",
    Action.AVOID_AREA: "immediate",
    Action.BOIL_WATER: "expected",
    Action.MONITOR: "future",
    Action.ALL_CLEAR: "future",
}


class Instruction(BaseModel):
    verb: str  # normalized English verb, e.g. "use", "return"
    object: str | None = None  # "elevators", "the area"
    negated: bool  # True for "do NOT ..."
    placeholders: list[str] = []  # e.g. ["⟦T1⟧"]


class AlertIntent(BaseModel):
    hazard: Hazard
    action: Action
    urgency: str = Field(default="immediate", pattern="^(immediate|expected|future)$")
    area_refs: list[str] = []  # placeholder ids only
    time_refs: list[str] = []  # placeholder ids only
    expires: str | None = None  # placeholder id
    instructions: list[Instruction] = []
    info_refs: list[str] = []  # phone / URL placeholders
    number_refs: list[str] = []  # quantities, e.g. the distance in "⟦N1⟧ from ⟦P1⟧"
    event_refs: list[str] = []  # named events, e.g. the storm name in "Hurricane ⟦E1⟧"
    source: str | None = None  # non critical
    extra_info: str | None = None  # non critical


CRITICAL_SLOTS = (
    "hazard",
    "action",
    "area_refs",
    "time_refs",
    "expires",
    "instructions",
    "info_refs",
    "number_refs",
    "event_refs",
)
NONCRITICAL_SLOTS = ("urgency", "source", "extra_info")
