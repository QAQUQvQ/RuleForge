"""Pure state transitions, resource accounting and recorded-event reduction."""
from copy import deepcopy
from ruleforge.domain.models import CombatState
from ruleforge.combat.errors import RuleError
from ruleforge.catalog.service import canonical
from ruleforge.ingestion.evidence import digest_text

TRANSITIONS = {'setup': {'turn_start', 'ended'}, 'turn_start': {'action', 'ended'},
    'action': {'turn_end', 'reaction', 'ended'}, 'reaction': {'action', 'ended'},
    'turn_end': {'turn_start', 'ended'}, 'ended': set()}


def state_hash(state):
    return digest_text(canonical(state.model_dump() if isinstance(state, CombatState) else state))


def transition(state, phase, **updates):
    if phase not in TRANSITIONS[state.phase]:
        raise RuleError('invalid_phase', f'Illegal transition {state.phase} -> {phase}', 409)
    if updates.get('round', state.round) < state.round:
        raise RuleError('invalid_round', 'Round cannot move backwards', 409)
    if any(key in updates and updates[key] != getattr(state, key)
           for key in ('id', 'ruleset', 'version', 'event_sequence', 'environment')):
        raise RuleError('invalid_transition', 'Identity and event counters are owned by the event builder', 409)
    data = state.model_dump()
    data.update(updates, phase=phase)
    return CombatState.model_validate(data)


def initiative(state, requested):
    values = {c.creature.id: c.initiative for c in state.combatants}
    order = requested or sorted(values, key=lambda key: (-values[key], key))
    if len(order) != len(values) or set(order) != set(values):
        raise RuleError('invalid_initiative', 'Initiative must contain every combatant exactly once')
    if any(values[a] < values[b] for a, b in zip(order, order[1:])):
        raise RuleError('invalid_initiative', 'Only tied initiative may be reordered')
    return order


def combatant(state, actor_id):
    for actor in state.combatants:
        if actor.creature.id == actor_id:
            return actor
    raise RuleError('invalid_target', 'Unknown encounter participant')


def spend(budget, resource, amount=1):
    result = budget.model_dump()
    if resource == 'movement_ft':
        if type(amount) is not int or amount < 0 or amount > budget.movement_ft:
            raise RuleError('budget_exhausted', 'Insufficient movement')
        result[resource] -= amount
    elif resource in ('action', 'bonus_action', 'reaction'):
        if not result[resource]:
            raise RuleError('budget_exhausted', f'{resource} already spent', 409)
        result[resource] = False
    else:
        raise RuleError('unsupported_action', 'Unknown action resource')
    return result


def distance(a, b):
    # Explicit project convention: one square = 5 ft, diagonals also cost 5 ft.
    return 5 * max(abs(a.x-b.x), abs(a.y-b.y))


def expire(effects, owner_id, phase):
    updated = deepcopy(effects)
    for effect in updated:
        if not effect['active']:
            continue
        if phase == 'encounter_end':
            effect['active'] = False
        elif effect['duration_type'] == 'owner_turn_boundary' and effect['duration_owner_id'] == owner_id and effect['expires_at_phase'] == phase:
            effect['remaining_rounds'] -= 1
            if effect['remaining_rounds'] == 0:
                effect['active'] = False
    return updated


def turn_start(state):
    data = state.model_dump()
    actor = next(c for c in data['combatants'] if c['creature']['id'] == state.active_id)
    actor['budget'] = dict(action=True, bonus_action=True, reaction=True, movement_ft=actor['speed_ft'])
    data['effects'] = expire(data['effects'], state.active_id, 'turn_start')
    return CombatState.model_validate(data)


def reduce_event(state, event):
    """Replay fixed patches, never reroll or look up today's mutable catalog."""
    if event.encounter_id != state.id or event.sequence != state.event_sequence + 1 or event.before_hash != state_hash(state):
        raise RuleError('integrity_failure', 'Event order/identity/before hash mismatch', 409)
    data = state.model_dump()
    changes = event.payload['changes']
    if not set(changes) <= set(data):
        raise RuleError('integrity_failure', 'Unknown state patch key', 409)
    data.update(deepcopy(changes))
    result = CombatState.model_validate(data)
    if (result.id != state.id or result.ruleset != state.ruleset or result.version != state.version + 1
        or result.event_sequence != event.sequence or result.round < state.round
        or result.environment != state.environment or result.map_cells != state.map_cells):
        raise RuleError('integrity_failure', 'Event violates identity/version/round invariants', 409)
    if result.phase != state.phase and result.phase not in TRANSITIONS[state.phase]:
        raise RuleError('integrity_failure', 'Event contains illegal phase transition', 409)
    if event.after_hash != state_hash(result):
        raise RuleError('integrity_failure', 'Event after hash mismatch', 409)
    return result


def fixed_tests():
    from ruleforge.domain.models import ActionBudget, Position, Combatant, Creature
    assert spend(ActionBudget(), 'action')['action'] is False
    assert spend(ActionBudget(movement_ft=30), 'movement_ft', 5)['movement_ft'] == 25
    assert distance(Position(x=0, y=0), Position(x=1, y=1)) == 5
    assert TRANSITIONS['ended'] == set()
    initial = CombatState(id='golden', combatants=[
        Combatant(creature=Creature(id='a', name='A'), initiative=10, speed_ft=20,
                  budget=ActionBudget(action=False, bonus_action=False, reaction=False, movement_ft=0)),
        Combatant(creature=Creature(id='b', name='B'), initiative=12,
                  budget=ActionBudget(reaction=False))])
    assert initiative(initial, []) == ['b', 'a']
    starting = transition(initial, 'turn_start', initiative_order=['b','a'], active_id='a', encounter_status='active')
    reset = turn_start(starting)
    assert reset.combatants[0].budget == ActionBudget(movement_ft=20)
    assert not reset.combatants[1].budget.reaction
    assert not initial.combatants[0].budget.reaction
    opened = transition(reset, 'action')
    assert transition(opened, 'turn_end').phase == 'turn_end'
    effect = dict(active=True, duration_type='owner_turn_boundary', duration_owner_id='a',
                  expires_at_phase='turn_start', remaining_rounds=1)
    assert expire([effect], 'b', 'turn_start') == [effect]
    assert expire([effect], 'a', 'turn_end') == [effect]
    assert not expire([effect], 'a', 'turn_start')[0]['active']
    try:
        spend(ActionBudget(reaction=False), 'reaction')
    except RuleError:
        pass
    else:
        raise AssertionError('Reaction can be double spent')
    return {'status': 'passed', 'suite': 'm3-state-primitives-v1', 'vectors': 13}
