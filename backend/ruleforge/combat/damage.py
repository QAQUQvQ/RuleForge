from typing import Annotated
from pydantic import Field
from ruleforge.domain.models import StrictModel, HitPoints
from ruleforge.catalog.equipment import DamageType, DiceExpression


class DamageComponent(StrictModel):
    damage_type: DamageType
    dice: DiceExpression
    modifier: Annotated[int, Field(ge=-999, le=999)] = 0


class Defenses(StrictModel):
    resistance: list[DamageType] = Field(default_factory=list, max_length=13)
    vulnerability: list[DamageType] = Field(default_factory=list, max_length=13)
    immunity: list[DamageType] = Field(default_factory=list, max_length=13)


def damage(components: list[DamageComponent], defenses: Defenses, dice, *, critical=False):
    from ruleforge.combat.errors import RuleError
    if not 1 <= len(components) <= 20:
        raise RuleError('unsupported_context', 'Expected 1..20 independent damage components')
    result = []
    for component in components:
        roll = dice.roll(component.dice.expression, critical=critical)
        raw = max(0, roll['total'] + component.modifier)
        kind = component.damage_type
        immune = kind in defenses.immunity
        resistant = kind in defenses.resistance
        vulnerable = kind in defenses.vulnerability
        after_resistance = raw // 2 if resistant else raw
        final = 0 if immune else after_resistance * (2 if vulnerable else 1)
        result.append({'damage_type': kind, 'dice': roll, 'ability_modifier': component.modifier,
            'raw_damage': raw, 'immunity': immune, 'resistance': resistant, 'vulnerability': vulnerable,
            'after_resistance': after_resistance, 'damage': final,
            'trace': ['double dice only on critical', 'clamp damage to zero',
                      'immunity -> zero; otherwise resistance (floor half), then vulnerability']})
    return {'components': result, 'total': sum(c['damage'] for c in result), 'critical': critical}


def apply_hp(hp: HitPoints, amount: int, *, critical=False):
    from ruleforge.combat.errors import RuleError
    if type(amount) is not int or not 0 <= amount <= 1000000:
        raise RuleError('invalid_damage', 'Damage must be a bounded nonnegative integer')
    absorbed = min(hp.temporary, amount)
    remaining = amount - absorbed
    after = HitPoints(maximum=hp.maximum, current=max(0, hp.current-remaining), temporary=hp.temporary-absorbed)
    overflow = max(0, remaining-hp.current)
    needs_dm = after.current == 0
    return {'before': hp.model_dump(), 'after': after.model_dump(), 'damage': amount,
            'temporary_absorbed': absorbed, 'hp_lost': hp.current-after.current, 'overflow': overflow,
            'damage_at_zero': hp.current == 0 and remaining > 0,
            'death_save_failures_pending': (2 if critical else 1) if hp.current == 0 and remaining > 0 else 0,
            'instant_death_threshold_met': remaining > 0 and overflow >= hp.maximum,
            'status': 'dm_or_m3_required' if needs_dm else 'resolved',
            'trace': [f'temporary HP absorbs {absorbed}', f'HP {hp.current} -> {after.current}',
                      f'overflow {overflow}; death/stability/monster policy not committed']}
