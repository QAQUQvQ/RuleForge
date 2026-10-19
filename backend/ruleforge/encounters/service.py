"""Atomic Command -> fixed DomainEvents -> encounter snapshot, using the M2 kernel."""
import json
from copy import deepcopy
from contextlib import contextmanager
from uuid import uuid4
from pydantic import TypeAdapter, ValidationError
from ruleforge.domain.models import (CombatState, Combatant, Creature, ActionBudget, DomainEvent,
    Command, HitPoints)
from ruleforge.encounters.contracts import CreateEncounter, PAYLOAD_TYPES
from ruleforge.encounters.machine import (state_hash, transition, initiative, combatant, spend,
    distance, expire, turn_start, reduce_event)
from ruleforge.encounters.runtime import EncounterScope
from ruleforge.encounters.evidence import TURN, READY
from ruleforge.combat.characters import Characters, ATTACK, DAMAGE
from ruleforge.combat.attacks import attack, AttackContext
from ruleforge.combat.damage import damage, apply_hp, DamageComponent, Defenses
from ruleforge.combat.dice import Dice
from ruleforge.combat.errors import RuleError
from ruleforge.catalog.equipment import WeaponDefinition
from ruleforge.catalog.service import canonical
from ruleforge.ingestion.evidence import digest_text, evidence_snapshot, now
from ruleforge.persistence.db import connect

COMMAND = TypeAdapter(Command)


def event_digest(event):
    data = event.model_dump()
    data.pop('event_hash')
    return digest_text(canonical(data))


class Builder:
    def __init__(self, state, command, scope, head):
        self.state, self.command, self.scope, self.head = state, command, scope, head
        self.events = []

    def emit(self, event_type, next_state=None, *, targets=(), details=None, dice=()):
        before = self.state.model_dump()
        after = (next_state or self.state).model_dump()
        after['version'] += 1
        after['event_sequence'] += 1
        bindings = { (r['id'], r['version']): r for r in after['rule_version_bindings'] }
        for key, ref in self.scope.refs.items():
            if key in bindings and bindings[key] != ref:
                raise RuleError('rule_binding_changed', 'Encounter requires its original rule/adapter version', 409)
            bindings[key] = ref
        after['rule_version_bindings'] = sorted(bindings.values(), key=lambda r: (r['id'], r['version']))
        state = CombatState.model_validate(after)
        evidence = self.scope.evidence()
        event = DomainEvent(id=uuid4().hex, command_id=self.command.command_id, encounter_id=state.id,
            sequence=state.event_sequence, type=event_type, actor_id=self.command.actor_id,
            target_ids=list(targets), before_hash=state_hash(before), after_hash=state_hash(state),
            rule_refs=[{'id': r['id'], 'version': r['version']} for r in evidence['rule_refs']],
            source_ids=[r['id'] for r in evidence['source_refs']], dice=list(dice),
            runtime_adapter_refs=evidence['rule_refs'], previous_event_hash=self.head,
            payload={'changes': {k: v for k, v in after.items() if before[k] != v},
                     'resolution': details or {}, 'source_refs': evidence['source_refs']},
            trace=['DM-authorized local command', 'fixed state patch; replay never invokes RNG or current catalog'])
        event = event.model_copy(update={'event_hash': event_digest(event)})
        self.state = reduce_event(self.state, event)
        self.events.append(event)
        self.head = event.event_hash


class Encounters:
    def __init__(self, catalog, *, isolated_demo=False, fault=None):
        self.catalog, self.characters = catalog, Characters(catalog)
        self.mode = 'isolated_demo' if isolated_demo else 'production'
        self.fault = fault  # Explicit in-process test hook. Never exposed through HTTP/config/env.
        db = catalog.database.resolve()
        primary = (catalog.root/'data/ruleforge.sqlite3').resolve()
        if isolated_demo and (db == primary or (db.exists() and primary.exists() and db.samefile(primary))
                              or not db.name.startswith('m3-demo')):
            raise ValueError('Demo requires a separate m3-demo*.sqlite3 database')

    @contextmanager
    def transaction(self, *, write=False):
        with connect(self.catalog.database) as conn, evidence_snapshot(cache_files=True):
            conn.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
            mode = conn.execute('SELECT mode FROM encounter_environment WHERE id=1').fetchone()[0]
            if mode != self.mode:
                raise RuleError('environment_mismatch', 'Use an explicit isolated demo application for this database', 409)
            yield conn, EncounterScope(self.catalog, conn, self.mode)

    def create(self, request: CreateEncounter):
        with self.transaction(write=True) as (conn, scope):
            scope.require(TURN)
            actors = []
            for participant in request.participants:
                char = self.characters.load(conn, participant.character_id)
                if char.version != participant.expected_version:
                    raise RuleError('version_conflict', 'Character changed before encounter creation', 409)
                ac = self.characters.ac_for(char, scope)
                if char.hp.current == 0:
                    raise RuleError('dm_required', 'Resolve zero HP before adding a combatant')
                speed = max(0, char.speed_ft - ac['equipment_consequences']['speed_reduction_ft'])
                actors.append(Combatant(creature=Creature(**char.model_dump(), kind=participant.kind),
                    initiative=participant.initiative, position=participant.position,
                    budget=ActionBudget(movement_ft=speed), ac=ac['ac'], ac_sources=ac,
                    defenses=participant.defenses.model_dump(), speed_ft=speed, team=participant.team,
                    character_version=char.version))
            state = CombatState(id=uuid4().hex, combatants=actors, environment=self.mode,
                map_cells=request.clear_cells, scene_notes=request.notes,
                rule_version_bindings=sorted(scope.refs.values(), key=lambda r: (r['id'], r['version'])))
            raw, digest = state.model_dump_json(), state_hash(state)
            conn.execute('''INSERT INTO encounters(id,version,state_json,initial_json,initial_hash,state_hash,event_head)
                VALUES (?,?,?,?,?,?,?)''', (state.id, 0, raw, raw, digest, digest, digest))
            return state

    def load(self, conn, encounter_id):
        row = conn.execute('SELECT * FROM encounters WHERE id=?', (encounter_id,)).fetchone()
        if not row:
            raise RuleError('not_found', 'Encounter not found', 404)
        if row['initial_json'] is None:
            raise RuleError('legacy_encounter', 'Legacy snapshot retained; no invented event history', 409)
        try:
            state = CombatState.model_validate_json(row['state_json'])
        except ValidationError as exc:
            raise RuleError('integrity_failure', 'Malformed encounter snapshot', 409) from exc
        if (state.id != encounter_id or state.version != row['version'] or state.environment != self.mode
            or state_hash(state) != row['state_hash']):
            raise RuleError('integrity_failure', 'Encounter snapshot identity/hash mismatch', 409)
        return state, row

    def get(self, encounter_id):
        with self.transaction() as (conn, _):
            return self.load(conn, encounter_id)[0]

    def _authorize_bindings(self, state, scope):
        for ref in state.rule_version_bindings:
            scope.require(ref['id'], ref['version'])
            if scope.refs[(ref['id'], ref['version'])] != ref:
                raise RuleError('rule_binding_changed', 'Current grant differs from encounter binding', 409)

    def _replay(self, conn, encounter_id):
        current, row = self.load(conn, encounter_id)
        try:
            state = CombatState.model_validate_json(row['initial_json'])
            if state.id != encounter_id or state.version != 0 or state.event_sequence != 0 or state_hash(state) != row['initial_hash']:
                raise RuleError('integrity_failure', 'Initial snapshot mismatch', 409)
            head = row['initial_hash']
            events = []
            command_events = {}
            for stored in conn.execute('SELECT * FROM events WHERE encounter_id=? ORDER BY sequence', (encounter_id,)):
                event = DomainEvent.model_validate_json(stored['payload_json'])
                if (event.id != stored['id'] or event.command_id != stored['command_id']
                    or event.sequence != stored['sequence'] or event.before_hash != stored['before_hash']
                    or event.after_hash != stored['after_hash'] or event.previous_event_hash != head
                    or event.event_hash != stored['event_hash'] or event_digest(event) != event.event_hash):
                    raise RuleError('integrity_failure', 'Event envelope/hash chain mismatch', 409)
                state = reduce_event(state, event)
                events.append(event.model_dump())
                command_events.setdefault(event.command_id, []).append(event.model_dump())
                head = event.event_hash
            for stored in conn.execute('SELECT * FROM commands WHERE encounter_id=?', (encounter_id,)):
                request = json.loads(stored['payload_json'])
                result = json.loads(stored['result_json'])
                group = command_events.pop(stored['id'], None)
                if (digest_text(canonical(request)) != stored['request_hash'] or request['command_id'] != stored['id']
                    or request['encounter_id'] != encounter_id or request['expected_version'] != stored['expected_version']
                    or not group or group != result['events']
                    or result['state']['version'] != group[-1]['sequence']
                    or state_hash(result['state']) != group[-1]['after_hash']
                    or stored['expected_version'] != group[0]['sequence']-1
                    or any(e['actor_id'] != request['actor_id'] for e in group)):
                    raise RuleError('integrity_failure', 'Command receipt/history mismatch', 409)
            if command_events or state_hash(state) != row['state_hash'] or state != current or head != row['event_head']:
                raise RuleError('integrity_failure', 'Final snapshot/event head mismatch', 409)
            return {'verified': True, 'state': state.model_dump(), 'state_hash': state_hash(state),
                    'event_head': head, 'events': events, 'authorization': 'historical_data_only'}
        except (ValueError, KeyError, TypeError) as exc:
            if isinstance(exc, RuleError):
                raise
            raise RuleError('integrity_failure', 'Malformed historical data', 409) from exc

    def replay(self, encounter_id):
        with self.transaction() as (conn, _):
            return self._replay(conn, encounter_id)

    def execute(self, command):
        try:
            command = COMMAND.validate_python(command) if isinstance(command, dict) else COMMAND.validate_python(command.model_dump())
            payload = PAYLOAD_TYPES[command.type].model_validate(command.payload)
        except (ValidationError, KeyError) as exc:
            raise RuleError('unsupported_or_invalid_command', str(exc)) from exc
        request = command.model_dump()
        request_hash = digest_text(canonical(request))
        with self.transaction(write=True) as (conn, scope):
            state, row = self.load(conn, command.encounter_id)
            prior = conn.execute('SELECT * FROM commands WHERE id=?', (command.command_id,)).fetchone()
            # A retry keeps the original expected_version. Recognize the receipt before rejecting stale versions.
            if prior:
                if prior['request_hash'] != request_hash or prior['encounter_id'] != state.id:
                    raise RuleError('command_id_conflict', 'Command ID already names different content', 409)
                self._replay(conn, state.id)
                return dict(json.loads(prior['result_json']), idempotent=True)
            if command.expected_version != state.version:
                raise RuleError('version_conflict', 'Encounter changed; reload before submitting', 409)
            self._replay(conn, state.id)
            combatant(state, command.actor_id)
            if state.phase == 'ended':
                raise RuleError('encounter_ended', 'Ended encounters are immutable', 409)
            self._preflight(state, command, payload)
            if command.type not in ('end_encounter', 'dm_adjustment'):
                self._authorize_bindings(state, scope)
                scope.require(TURN)
            builder = Builder(state, command, scope, row['event_head'])
            self._handle(builder, payload)
            result = {'idempotent': False, 'state': builder.state.model_dump(),
                      'events': [e.model_dump() for e in builder.events]}
            conn.execute('''INSERT INTO commands(id,encounter_id,expected_version,payload_json,created_at,request_hash,result_json)
                VALUES (?,?,?,?,?,?,?)''', (command.command_id, state.id, command.expected_version,
                canonical(request), now(), request_hash, canonical(result)))
            self._fail('after_command')
            for event in builder.events:
                conn.execute('''INSERT INTO events(id,command_id,encounter_id,sequence,before_hash,after_hash,payload_json,event_hash)
                    VALUES (?,?,?,?,?,?,?,?)''', (event.id, event.command_id, event.encounter_id, event.sequence,
                    event.before_hash, event.after_hash, event.model_dump_json(), event.event_hash))
                self._fail('after_event')
            if conn.execute('''UPDATE encounters SET version=?,state_json=?,state_hash=?,event_head=?
                WHERE id=? AND version=?''', (builder.state.version, builder.state.model_dump_json(),
                state_hash(builder.state), builder.head, state.id, state.version)).rowcount != 1:
                raise RuleError('version_conflict', 'Concurrent encounter update', 409)
            self._fail('after_snapshot')
            return result

    def _fail(self, stage):
        if self.fault:
            self.fault(stage)

    def _preflight(self, state, command, payload):
        """Check actor/phase/resource legality before any runtime lookup or RNG."""
        if command.type in ('attack', 'ready', 'move', 'end_turn'):
            actor = self._ordinary(state, command, require_alive=command.type != 'end_turn')
            if command.type in ('attack', 'ready'):
                spend(actor.budget, 'action')
            if command.type == 'attack':
                combatant(state, command.target_id)
        elif command.type == 'start_encounter':
            if state.phase != 'setup':
                raise RuleError('invalid_phase', 'Encounter has already started', 409)
            initiative(state, payload.initiative_order)
        elif command.type == 'dm_adjustment':
            if state.phase == 'reaction':
                raise RuleError('invalid_phase', 'Finish reaction decisions before DM adjustment')
            combatant(state, command.target_id)
        elif command.type in ('submit_reaction', 'decline_reaction'):
            window = state.reaction_window
            if (state.phase != 'reaction' or not window or window.mechanism != 'ready_attack'
                or window.trigger_event_id != payload.trigger_event_id or not window.pending_reactions
                or command.actor_id != window.pending_reactions[0]):
                raise RuleError('invalid_reaction', 'No matching pending reaction for this actor/trigger', 409)
            if command.type == 'submit_reaction':
                spend(combatant(state, command.actor_id).budget, 'reaction')

    def _ordinary(self, state, command, *, require_alive=True):
        if state.phase != 'action':
            raise RuleError('invalid_phase', 'Ordinary actions require action phase', 409)
        if state.active_id != command.actor_id:
            raise RuleError('invalid_actor', 'Only the active combatant can act', 409)
        actor = combatant(state, command.actor_id)
        if require_alive and (actor.status != 'alive' or actor.creature.hp.current == 0):
            raise RuleError('dm_required', 'Resolve incapacitation/death before acting')
        return actor

    def _weapon(self, actor, weapon_id, scope):
        ac = self.characters.ac_for(actor.creature, scope)
        if ac['ac'] != actor.ac:
            raise RuleError('integrity_failure', 'Stored AC differs from bound equipment')
        items = [i for i in actor.creature.inventory if i.equipped and i.equipment_slot == 'main_hand'
                 and i.equipment_record_id == weapon_id]
        if len(items) != 1:
            raise RuleError('invalid_equipment', 'Requires equipped main-hand weapon')
        weapon = scope.require(weapon_id, items[0].record_version).normalized_payload
        if not isinstance(weapon, WeaponDefinition) or weapon.attack_category != 'melee' or weapon.damage_dice is None:
            raise RuleError('unsupported_action', 'M3 adapter supports ordinary melee weapons only')
        return weapon, ac

    def _attack(self, builder, target_id, weapon_id, payload, *, reaction=False):
        state, command, scope = builder.state, builder.command, builder.scope
        actor, target = combatant(state, command.actor_id), combatant(state, target_id)
        if actor.creature.id == target_id or actor.status != 'alive' or target.status != 'alive':
            raise RuleError('dm_required', 'Self attacks and incapacitated/dead participants need separate adjudication')
        if any(e.active and e.kind == 'dm_marker' and e.target_id in (actor.creature.id, target_id) for e in state.effects):
            raise RuleError('unsupported_context', 'DM condition note requires adjudication/removal before automatic attack')
        resource = 'reaction' if reaction else 'action'
        budget = spend(actor.budget, resource)
        weapon, ac = self._weapon(actor, weapon_id, scope)
        target_ac = self.characters.ac_for(target.creature, scope)
        if target_ac['ac'] != target.ac:
            raise RuleError('integrity_failure', 'Target AC snapshot mismatch')
        scope.require(ATTACK); scope.require(DAMAGE)
        dice = Dice(fixed=payload.fixed_dice)
        context = AttackContext(mode='melee', distance_ft=distance(actor.position, target.position),
            scene_confirmed=payload.scene_confirmed, target_visible=payload.target_visible, cover=payload.cover,
            hostile_within_5ft=any(c.team != actor.team and c.status == 'alive' and distance(c.position, actor.position) <= 5
                                  for c in state.combatants))
        hit = attack(actor.creature.id, target_id, weapon, actor.creature.abilities,
            weapon.proficiency_category in actor.creature.proficiencies, actor.creature.proficiency_bonus,
            target.ac, context, dice, armor_disadvantage=ac['equipment_consequences']['armor_nonproficiency'])
        dealt = damage([DamageComponent(damage_type=weapon.damage_type, dice=weapon.damage_dice,
            modifier=hit.ability_modifier)], Defenses.model_validate(target.defenses), dice, critical=hit.critical) if hit.hit else {
                'components': [], 'total': 0, 'critical': False}
        hp = apply_hp(target.creature.hp, dealt['total'], critical=hit.critical)
        dice.finish()
        data = state.model_dump()
        for entry in data['combatants']:
            if entry['creature']['id'] == actor.creature.id:
                entry['budget'] = budget
            if entry['creature']['id'] == target_id:
                entry['creature']['hp'] = hp['after']
                if hp['after']['current'] == 0:
                    entry['status'] = 'dm_required'
        if reaction:
            for effect in data['effects']:
                if effect['active'] and effect['kind'] == 'ready_attack' and effect['target_id'] == command.actor_id:
                    effect['active'] = False
        builder.emit('reaction_attack_resolved' if reaction else 'attack_resolved', CombatState.model_validate(data),
            targets=[target_id], dice=dice.log, details={'attack': hit.model_dump(), 'damage': dealt, 'hp': hp,
                'budget_before': actor.budget.model_dump(), 'budget_after': budget, 'context': context.model_dump(),
                'dice_mode': dice.mode})

    def _handle(self, b, payload):
        s, c = b.state, b.command
        if c.type == 'start_encounter':
            if s.phase != 'setup':
                raise RuleError('invalid_phase', 'Encounter has already started', 409)
            order = initiative(s, payload.initiative_order)
            started = transition(s, 'turn_start', initiative_order=order, active_id=order[0], encounter_status='active')
            b.emit('encounter_started', turn_start(started), details={'initiative_confirmation': payload.model_dump()})
            b.emit('turn_opened', transition(b.state, 'action'))
        elif c.type == 'end_encounter':
            data = s.model_dump()
            data.update(phase='ended', encounter_status='ended', active_id=None, reaction_window=None,
                        effects=expire(data['effects'], None, 'encounter_end'))
            b.emit('encounter_ended', CombatState.model_validate(data), details=payload.model_dump())
        elif c.type == 'dm_adjustment':
            if s.phase == 'reaction':
                raise RuleError('invalid_phase', 'Finish reaction decisions before DM adjustment')
            target = combatant(s, c.target_id)
            data = s.model_dump()
            entry = next(x for x in data['combatants'] if x['creature']['id'] == c.target_id)
            hp = entry['creature']['hp']
            hp['current'] = max(0, min(hp['maximum'], hp['current'] + c.hp_delta))
            entry['status'] = payload.status or ('alive' if hp['current'] else 'dm_required')
            if entry['status'] == 'alive' and hp['current'] == 0:
                raise RuleError('invalid_adjustment', 'Zero HP cannot be marked alive')
            if payload.remove_effect_id:
                matches = [e for e in data['effects'] if e['id'] == payload.remove_effect_id and e['target_id'] == c.target_id and e['active']]
                if not matches:
                    raise RuleError('invalid_effect', 'No active effect with this ID/target')
                matches[0]['active'] = False
            if payload.marker:
                if any(e['active'] and e['kind'] == 'dm_marker' and e['target_id'] == c.target_id and e['label'] == payload.marker for e in data['effects']):
                    raise RuleError('duplicate_effect', 'DM note already exists')
                data['effects'].append(dict(id=uuid4().hex, rule_id='dm.declaration', target_id=c.target_id,
                    expires='dm', kind='dm_marker', label=payload.marker, applied_at={'sequence': s.event_sequence+1,
                    'round': s.round, 'active_id': s.active_id, 'phase': s.phase}, duration_type='dm'))
            b.emit('dm_adjusted', CombatState.model_validate(data), targets=[c.target_id],
                details={'reason': c.reason, 'before_hp': target.creature.hp.model_dump(), 'after_hp': hp,
                         'declaration': payload.model_dump(), 'scope': 'DM decision, not automatic rules execution'})
        elif c.type == 'end_turn':
            self._ordinary(s, c, require_alive=False)
            data = s.model_dump()
            data['effects'] = expire(data['effects'], s.active_id, 'turn_end')
            b.emit('turn_ended', transition(CombatState.model_validate(data), 'turn_end'))
            index = (s.initiative_order.index(s.active_id)+1) % len(s.initiative_order)
            next_state = transition(b.state, 'turn_start', active_id=s.initiative_order[index], round=s.round+(index == 0))
            b.emit('turn_started', turn_start(next_state))
            b.emit('turn_opened', transition(b.state, 'action'))
        elif c.type == 'attack':
            self._ordinary(s, c)
            self._attack(b, c.target_id, c.weapon_id, payload)
        elif c.type == 'ready':
            actor = self._ordinary(s, c)
            b.scope.require(READY)
            self._weapon(actor, payload.weapon_id, b.scope)
            if payload.trigger_actor == c.actor_id:
                raise RuleError('invalid_trigger', 'Ready trigger must identify another participant')
            combatant(s, payload.trigger_actor)
            data = s.model_dump()
            entry = next(x for x in data['combatants'] if x['creature']['id'] == c.actor_id)
            entry['budget'] = spend(actor.budget, 'action')
            # Same actor cannot stack multiple prepared responses; one action per turn.
            if any(e['active'] and e['target_id'] == c.actor_id and e['kind'] == 'ready_attack' for e in data['effects']):
                raise RuleError('duplicate_effect', 'Ready action already active')
            data['effects'].append(dict(id=uuid4().hex, rule_id=READY, rule_version=1, target_id=c.actor_id,
                kind='ready_attack', expires='turn_start', expires_at_phase='turn_start',
                duration_type='owner_turn_boundary', duration_owner_id=c.actor_id, remaining_rounds=1,
                applied_at={'sequence': s.event_sequence+1, 'round': s.round, 'active_id': s.active_id, 'phase': s.phase},
                source_refs=b.scope.evidence()['source_refs'], parameters=payload.model_dump()))
            b.emit('action_readied', CombatState.model_validate(data), details=payload.model_dump())
        elif c.type == 'move':
            actor = self._ordinary(s, c)
            if any(e.active and e.kind == 'dm_marker' and e.target_id == c.actor_id for e in s.effects):
                raise RuleError('unsupported_context', 'DM condition note requires movement adjudication')
            if payload.path[-1] != c.destination:
                raise RuleError('invalid_path', 'Destination must equal the final path cell')
            previous = actor.position
            for cell in payload.path:
                if cell not in s.map_cells or distance(previous, cell) != 5:
                    raise RuleError('invalid_path', 'Each step must enter an adjacent confirmed clear cell')
                if any(x.creature.id != c.actor_id and x.position == cell for x in s.combatants):
                    raise RuleError('unsupported_terrain', 'Occupied cells require separate adjudication')
                if any(x.team != actor.team and x.status == 'alive' and distance(previous, x.position) <= 5
                       and distance(cell, x.position) > 5 for x in s.combatants):
                    raise RuleError('unsupported_reaction', 'Leaving hostile reach requires opportunity-attack adjudication')
                previous = cell
            data = s.model_dump()
            entry = next(x for x in data['combatants'] if x['creature']['id'] == c.actor_id)
            entry.update(position=c.destination.model_dump(), budget=spend(actor.budget, 'movement_ft', len(payload.path)*5))
            b.emit('moved', CombatState.model_validate(data), details={'path': [p.model_dump() for p in payload.path],
                'cost_ft': len(payload.path)*5, 'scene': payload.model_dump(exclude={'path'})})
            eligible = []
            for actor_id in b.state.initiative_order:
                candidate = combatant(b.state, actor_id)
                if candidate.status != 'alive' or not candidate.budget.reaction:
                    continue
                if any(e.active and e.kind == 'ready_attack' and e.target_id == actor_id
                       and e.parameters['trigger_actor'] == c.actor_id and distance(candidate.position, c.destination) == 5
                       for e in b.state.effects):
                    eligible.append(actor_id)
            if eligible:
                b.scope.require(READY)
                window = dict(trigger_event_id=b.events[-1].id, eligible_ids=eligible, resume_phase='action',
                    triggering_actor=c.actor_id, response_status={a: 'pending' for a in eligible},
                    pending_reactions=eligible, resolved_reactions=[], mechanism='ready_attack')
                b.emit('reaction_opened', transition(b.state, 'reaction', reaction_window=window), targets=eligible,
                    details={'ordering': 'initiative order; DM confirmed when encounter started'})
        elif c.type in ('submit_reaction', 'decline_reaction'):
            window = s.reaction_window
            if (s.phase != 'reaction' or not window or window.mechanism != 'ready_attack'
                or window.trigger_event_id != payload.trigger_event_id
                or not window.pending_reactions or c.actor_id != window.pending_reactions[0]):
                raise RuleError('invalid_reaction', 'No matching pending reaction for this actor/trigger', 409)
            b.scope.require(READY)
            if c.type == 'submit_reaction':
                effect = next((e for e in s.effects if e.active and e.kind == 'ready_attack'
                               and e.target_id == c.actor_id and e.parameters['trigger_actor'] == window.triggering_actor), None)
                if effect is None:
                    raise RuleError('invalid_reaction', 'Ready effect is no longer active')
                self._attack(b, window.triggering_actor, effect.parameters['weapon_id'], payload, reaction=True)
            data = b.state.model_dump()
            w = data['reaction_window']
            w['pending_reactions'].remove(c.actor_id)
            w['resolved_reactions'].append(c.actor_id)
            w['response_status'][c.actor_id] = 'submitted' if c.type == 'submit_reaction' else 'declined'
            b.emit('reaction_responded', CombatState.model_validate(data), details={'response': w['response_status'][c.actor_id],
                'trigger_event_id': w['trigger_event_id']})
            if not w['pending_reactions']:
                b.emit('reaction_closed', transition(b.state, window.resume_phase, reaction_window=None), details={'window': w})
        else:
            raise RuleError('unsupported_action', 'No verified command adapter')
