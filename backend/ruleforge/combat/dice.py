"""Bounded dice parser. Fixed streams are explicitly demonstration inputs."""
import random
import re
from ruleforge.combat.errors import RuleError


def parse(expression: str):
    match = re.fullmatch(r'([1-9][0-9]?)d(4|6|8|10|12|20|100)([+-][0-9]{1,3})?', expression)
    if not match:
        raise RuleError('invalid_dice', 'Expected 1..99 dice, supported sides, optional +/-0..999')
    return int(match[1]), int(match[2]), int(match[3] or 0)


class Dice:
    def __init__(self, *, rng=None, fixed=None):
        if fixed is not None and (len(fixed) > 1000 or any(type(v) is not int or not 1 <= v <= 100 for v in fixed)):
            raise RuleError('invalid_dice', 'Invalid fixed dice stream')
        self.rng = rng if rng is not None else random.SystemRandom()
        self.fixed = iter(fixed) if fixed is not None else None
        self.mode = 'fixed_demo' if fixed is not None else ('injected_rng' if rng is not None else 'random')
        self.log = []

    def roll(self, expression: str, *, critical=False):
        count, sides, modifier = parse(expression)
        count *= 2 if critical else 1
        if len(self.log) + count > 1000:
            raise RuleError('invalid_dice', 'Calculation dice budget exceeded')
        values = []
        for _ in range(count):
            try:
                value = next(self.fixed) if self.fixed is not None else self.rng.randint(1, sides)
            except StopIteration as exc:
                raise RuleError('invalid_dice', 'Fixed dice stream exhausted') from exc
            if type(value) is not int or not 1 <= value <= sides:
                raise RuleError('invalid_dice', f'Die result outside d{sides}')
            self.log.append({'sides': sides, 'value': value})
            values.append(value)
        return {'expression': expression, 'rolls': values, 'sides': sides,
                'modifier': modifier, 'total': sum(values) + modifier, 'critical': critical}

    def finish(self):
        if self.fixed is not None and next(self.fixed, None) is not None:
            raise RuleError('invalid_dice', 'Unused fixed dice; supply exactly the required stream')
