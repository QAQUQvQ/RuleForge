from ruleforge.combat.errors import RuleError


def ability_modifier(score: int) -> int:
    if type(score) is not int or not 1 <= score <= 30:
        raise RuleError('invalid_ability', 'Ability score must be an integer from 1 to 30')
    return (score - 10) // 2


def proficiency(level: int) -> int:
    if type(level) is not int or not 1 <= level <= 20:
        raise RuleError('unsupported_context', 'Level must be 1..20')
    return 2 + (level - 1) // 4


def armor_class(dexterity: int, armor=None, shield=None, *, defense=False):
    dex = ability_modifier(dexterity)
    # Arithmetic only. Runtime service must separately authorize every path.
    base = armor.base_ac if armor else 10
    used = dex
    if armor and armor.dexterity_modifier_policy == 'capped':
        used = min(dex, armor.dexterity_modifier_cap)
    elif armor and armor.dexterity_modifier_policy == 'none':
        used = 0
    bonus = shield.ac_bonus if shield else 0
    style = int(defense and armor is not None)
    return {'ac': base + used + bonus + style, 'base_ac': base, 'dexterity_modifier': dex,
            'dexterity_used': used, 'shield_bonus': bonus, 'other_modifiers': {'defense': style},
            'trace': [f'base {base}', f'DEX {dex}; applied {used}', f'shield {bonus}',
                      f'Defense {style}', f'AC = {base + used + bonus + style}']}
