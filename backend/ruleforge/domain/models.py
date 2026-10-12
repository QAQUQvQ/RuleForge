from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

Score = Annotated[int, Field(ge=1, le=30)]
Nonnegative = Annotated[int, Field(ge=0, le=10000)]

class Abilities(StrictModel):
    strength: Score = 10
    dexterity: Score = 10
    constitution: Score = 10
    intelligence: Score = 10
    wisdom: Score = 10
    charisma: Score = 10

class Equipment(StrictModel):
    armor: Literal["none", "leather", "light", "medium", "heavy"] = "none"
    shield: bool = False
    alternative_ac: bool = False

class HitPoints(StrictModel):
    maximum: Annotated[int, Field(ge=1, le=10000)] = 1
    current: Nonnegative = 1
    temporary: Nonnegative = 0

    @model_validator(mode="after")
    def valid_current(self):
        if self.current > self.maximum:
            raise ValueError("HP exceeds maximum")
        return self

class Character(StrictModel):
    id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=100)
    ruleset: Literal["srd-5.1"] = "srd-5.1"
    version: Annotated[int, Field(ge=0)] = 0
    level: Annotated[int, Field(ge=1, le=20)] = 1
    abilities: Abilities = Field(default_factory=Abilities)
    equipment: Equipment = Field(default_factory=Equipment)
    hp: HitPoints = Field(default_factory=HitPoints)
    speed_ft: Nonnegative = 30
    conditions: list[str] = Field(default_factory=list, max_length=50)
    resources: dict[str, Nonnegative] = Field(default_factory=dict, max_length=100)

class Creature(Character):
    kind: Literal["pc", "npc", "monster"] = "pc"

class Position(StrictModel):
    x: Annotated[int, Field(ge=-10000, le=10000)] = 0
    y: Annotated[int, Field(ge=-10000, le=10000)] = 0

class ActionBudget(StrictModel):
    action: bool = True
    bonus_action: bool = True
    reaction: bool = True
    movement_ft: Nonnegative = 30

class Combatant(StrictModel):
    creature: Creature
    initiative: Annotated[int, Field(ge=-100, le=100)] = 0
    position: Position = Field(default_factory=Position)
    budget: ActionBudget = Field(default_factory=ActionBudget)

class Effect(StrictModel):
    id: str
    rule_id: str
    target_id: str
    expires: Literal["turn_start", "turn_end", "encounter_end", "dm"]
    remaining_rounds: Nonnegative | None = None

class ReactionWindow(StrictModel):
    trigger_event_id: str
    eligible_ids: list[str]
    resume_phase: Literal["turn_start", "action", "turn_end"]

class CombatState(StrictModel):
    id: str
    ruleset: Literal["srd-5.1"] = "srd-5.1"
    version: Nonnegative = 0
    round: Annotated[int, Field(ge=1)] = 1
    phase: Literal["setup", "turn_start", "action", "reaction", "turn_end", "ended"] = "setup"
    combatants: list[Combatant] = Field(default_factory=list, max_length=100)
    initiative_order: list[str] = Field(default_factory=list, max_length=100)
    active_id: str | None = None
    reaction_window: ReactionWindow | None = None
    effects: list[Effect] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def references(self):
        ids = [c.creature.id for c in self.combatants]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate combatant")
        if len(self.initiative_order) != len(set(self.initiative_order)) or not set(self.initiative_order) <= set(ids):
            raise ValueError("invalid initiative order")
        if self.active_id is not None and self.active_id not in ids:
            raise ValueError("unknown active combatant")
        if self.phase not in ("setup", "ended"):
            if set(self.initiative_order) != set(ids) or self.active_id is None:
                raise ValueError("active combat needs complete initiative and active actor")
        if (self.phase == "reaction") != (self.reaction_window is not None):
            raise ValueError("reaction phase/window mismatch")
        if self.reaction_window and not set(self.reaction_window.eligible_ids) <= set(ids):
            raise ValueError("unknown reaction actor")
        if any(e.target_id not in ids for e in self.effects):
            raise ValueError("unknown effect target")
        return self

class Item(StrictModel):
    id: str
    name: str
    ruleset: str
    category: Literal["armor", "shield", "weapon", "other"]
    source_ids: list[str] = Field(min_length=1)
    review_status: Literal["draft", "verified", "rejected"] = "draft"

class CommandBase(StrictModel):
    command_id: str = Field(min_length=1, max_length=100)
    encounter_id: str
    actor_id: str
    expected_version: Nonnegative

class AttackCommand(CommandBase):
    type: Literal["attack"] = "attack"
    target_id: str
    weapon_id: str

class MoveCommand(CommandBase):
    type: Literal["move"] = "move"
    destination: Position

class EndTurnCommand(CommandBase):
    type: Literal["end_turn"] = "end_turn"

class DMAdjustmentCommand(CommandBase):
    type: Literal["dm_adjustment"] = "dm_adjustment"
    target_id: str
    hp_delta: Annotated[int, Field(ge=-10000, le=10000)]
    reason: str = Field(min_length=1, max_length=1000)

Command = Annotated[AttackCommand | MoveCommand | EndTurnCommand | DMAdjustmentCommand, Field(discriminator="type")]

class DieRoll(StrictModel):
    sides: Literal[4, 6, 8, 10, 12, 20, 100]
    value: Annotated[int, Field(ge=1, le=100)]

    @model_validator(mode="after")
    def in_range(self):
        if self.value > self.sides:
            raise ValueError("die result outside range")
        return self

class RuleReference(StrictModel):
    id: str
    version: Annotated[int, Field(ge=1)]

class DomainEvent(StrictModel):
    id: str
    command_id: str
    encounter_id: str
    sequence: Annotated[int, Field(ge=1)]
    type: Literal["attack_resolved", "moved", "turn_ended", "dm_adjusted"]
    before_hash: str = Field(pattern="^[a-f0-9]{64}$")
    after_hash: str = Field(pattern="^[a-f0-9]{64}$")
    rule_refs: list[RuleReference]
    source_ids: list[str]
    dice: list[DieRoll] = Field(default_factory=list)
    trace: list[str] = Field(default_factory=list, max_length=100)
