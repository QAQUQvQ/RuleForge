from typing import Annotated, Literal
from pydantic import Field
from ruleforge.domain.models import StrictModel, Abilities
from ruleforge.catalog.equipment import WeaponDefinition
from ruleforge.combat.modifiers import ability_modifier
from ruleforge.combat.errors import RuleError


class AttackContext(StrictModel):
    mode: Literal['melee', 'ranged']
    distance_ft: Annotated[int, Field(ge=0, le=10000)]
    # Explicit caller/DM assertions, never inferred from missing scene data.
    scene_confirmed: Literal[True]
    target_visible: Literal[True]
    cover: Literal['none']
    hostile_within_5ft: bool
    advantage: bool = False
    disadvantage: bool = False
    ability: Literal['strength', 'dexterity'] | None = None
    special_mechanics: list[str] = Field(default_factory=list, max_length=20)


class AttackResult(StrictModel):
    attacker_id: str
    target_id: str
    weapon_id: str
    attack_rolls: list[int]
    selected_d20: int
    ability: str
    ability_modifier: int
    proficiency_bonus: int
    attack_modifier: int
    attack_total: int
    target_ac: int
    hit: bool
    critical: bool
    applied_conditions: list[str]
    rule_refs: list[dict] = Field(default_factory=list)
    source_refs: list[dict] = Field(default_factory=list)
    trace: list[str]


def attack(attacker_id: str, target_id: str, weapon: WeaponDefinition, abilities: Abilities,
           proficient: bool, proficiency_bonus: int, target_ac: int, context: AttackContext, dice,
           *, armor_disadvantage=False) -> AttackResult:
    if type(target_ac) is not int or not 0 <= target_ac <= 100:
        raise RuleError('unsupported_context', 'Target AC must be 0..100')
    if context.special_mechanics or set(weapon.weapon_properties) & {'heavy', 'reach', 'special', 'loading', 'ammunition', 'two-handed'}:
        raise RuleError('unsupported_context', 'Special attacks, ammunition and two-handed use are not implemented')
    conditions = []
    disadvantage = context.disadvantage or armor_disadvantage
    if armor_disadvantage:
        conditions.append('armor_nonproficiency')
    if context.mode == 'melee':
        if weapon.attack_category != 'melee' or context.distance_ft > 5:
            raise RuleError('unsupported_context', 'Requires a melee weapon and confirmed distance <= 5 ft')
    else:
        if weapon.attack_category != 'ranged' and 'thrown' not in weapon.weapon_properties:
            raise RuleError('unsupported_context', 'Weapon cannot make this ranged attack')
        if weapon.long_range is None or context.distance_ft > weapon.long_range:
            raise RuleError('unsupported_context', 'Outside verified weapon range')
        if context.distance_ft > weapon.normal_range:
            disadvantage = True
            conditions.append('long_range')
        if context.hostile_within_5ft:
            disadvantage = True
            conditions.append('hostile_within_5ft')
    allowed = ['strength', 'dexterity'] if 'finesse' in weapon.weapon_properties else [
        'strength' if weapon.attack_category == 'melee' else 'dexterity']
    scores = abilities.model_dump()
    chosen = context.ability or max(allowed, key=lambda a: scores[a])
    if chosen not in allowed:
        raise RuleError('unsupported_context', 'Ability not allowed for this weapon')
    modifier = ability_modifier(scores[chosen])
    pb = proficiency_bonus if proficient else 0
    adv = context.advantage
    rolls = dice.roll('2d20' if adv != disadvantage else '1d20')['rolls']
    selected = (max(rolls) if adv else min(rolls)) if adv != disadvantage else rolls[0]
    conditions.append('cancelled' if adv and disadvantage else 'advantage' if adv else 'disadvantage' if disadvantage else 'normal')
    total = selected + modifier + pb
    return AttackResult(attacker_id=attacker_id, target_id=target_id, weapon_id=weapon.id,
        attack_rolls=rolls, selected_d20=selected, ability=chosen, ability_modifier=modifier,
        proficiency_bonus=pb, attack_modifier=modifier+pb, attack_total=total, target_ac=target_ac,
        hit=selected == 20 or (selected != 1 and total >= target_ac), critical=selected == 20,
        applied_conditions=conditions,
        trace=[f'{chosen} modifier {modifier}; proficiency {pb}', f'd20 {rolls} -> {selected}',
               f'{selected} + {modifier} + {pb} = {total}; target AC {target_ac}',
               'natural 1 misses; natural 20 hits and is critical', 'scene constraints asserted by caller; no turn legality evaluated'])
