from typing import Annotated, Literal
from pydantic import Field, model_validator
from ruleforge.domain.models import StrictModel, Position
from ruleforge.combat.damage import Defenses


class Participant(StrictModel):
    character_id: str = Field(min_length=1, max_length=100)
    expected_version: Annotated[int, Field(ge=1)]
    kind: Literal['pc', 'npc', 'monster'] = 'pc'
    team: str = Field(min_length=1, max_length=100)
    initiative: Annotated[int, Field(ge=-100, le=100)]
    position: Position
    defenses: Defenses = Field(default_factory=Defenses)


class CreateEncounter(StrictModel):
    participants: list[Participant] = Field(min_length=2, max_length=30)
    clear_cells: list[Position] = Field(min_length=2, max_length=400)
    scene_confirmed: Literal[True]
    initiative_confirmed: Literal[True]
    # Project map convention, explicitly acknowledged; not claimed as a core SRD rule.
    distance_convention: Literal['five_ft_chebyshev']
    notes: str = Field(min_length=1, max_length=2000)

    @model_validator(mode='after')
    def unique(self):
        ids = [p.character_id for p in self.participants]
        positions = [(p.position.x, p.position.y) for p in self.participants]
        cells = [(p.x, p.y) for p in self.clear_cells]
        if len(set(ids)) != len(ids) or len(set(positions)) != len(positions) or len(set(cells)) != len(cells):
            raise ValueError('Duplicate participants, occupied positions or map cells')
        if not set(positions) <= set(cells):
            raise ValueError('Every participant must occupy a confirmed map cell')
        return self


class EmptyPayload(StrictModel):
    pass


class StartPayload(StrictModel):
    initiative_order: list[str] = Field(default_factory=list, max_length=30)
    ties_confirmed: Literal[True]


class AttackPayload(StrictModel):
    scene_confirmed: Literal[True]
    target_visible: Literal[True]
    cover: Literal['none']
    fixed_dice: list[Annotated[int, Field(ge=1, le=100)]] | None = Field(default=None, max_length=100)


class MovePayload(StrictModel):
    path: list[Position] = Field(min_length=1, max_length=200)
    scene_confirmed: Literal[True]
    no_unmodeled_triggers: Literal[True]


class ReadyPayload(StrictModel):
    trigger_actor: str
    weapon_id: str
    trigger: Literal['actor_finishes_move_adjacent']
    perceivable_confirmed: Literal[True]


class ReactionPayload(AttackPayload):
    trigger_event_id: str


class DeclinePayload(StrictModel):
    trigger_event_id: str


class AdjustmentPayload(StrictModel):
    status: Literal['alive', 'dead', 'dm_required'] | None = None
    # DM notes are informational, never silently used as modifiers.
    marker: str | None = Field(default=None, min_length=1, max_length=100)
    remove_effect_id: str | None = None


class EndPayload(StrictModel):
    reason: str = Field(min_length=1, max_length=1000)


PAYLOAD_TYPES = {'start_encounter': StartPayload, 'attack': AttackPayload, 'move': MovePayload,
    'end_turn': EmptyPayload, 'dm_adjustment': AdjustmentPayload, 'ready': ReadyPayload,
    'submit_reaction': ReactionPayload, 'decline_reaction': DeclinePayload, 'end_encounter': EndPayload}
