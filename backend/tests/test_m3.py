"""M3 scenarios and adversarial checks. Simulated grants exist only in tmp_path DBs."""
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from ruleforge.api import create_app
from ruleforge.catalog.service import CatalogService
from ruleforge.combat.characters import Characters, CreateCharacter
from ruleforge.combat.errors import RuleError
from ruleforge.domain.models import CombatState, Combatant, Creature, ActionBudget, Position, ReactionWindow
from ruleforge.encounters.contracts import CreateEncounter
from ruleforge.encounters.demo import prepare_isolated_demo
from ruleforge.encounters.evidence import TURN, READY
from ruleforge.encounters.machine import transition, initiative, spend, expire, state_hash, TRANSITIONS
from ruleforge.encounters.service import Encounters
from ruleforge.persistence.db import connect, initialize

ROOT = Path(__file__).resolve().parents[2]
WEAPON = 'srd51.equipment.longsword'
SCENE = dict(scene_confirmed=True, target_visible=True, cover='none')


@pytest.fixture(scope='module')
def prepared(tmp_path_factory):
    database = tmp_path_factory.mktemp('m3')/'m3-demo-fixture.sqlite3'
    catalog = prepare_isolated_demo(ROOT, database)
    chars = Characters(catalog)
    for name in ('Alpha', 'Beta', 'Gamma'):
        chars.create(CreateCharacter(name=name, abilities={'strength':16,'dexterity':14,'constitution':14},
            skills=['Athletics','Perception'], speed_ft=30, origin_confirmed=True))
    return catalog


@pytest.fixture
def service(prepared, tmp_path):
    database = tmp_path/'m3-demo-copy.sqlite3'
    with sqlite3.connect(prepared.database) as src, sqlite3.connect(database) as dest:
        src.backup(dest)
    return Encounters(CatalogService(ROOT, database), isolated_demo=True)


def create(service, *, count=2, far=False, positions=None):
    with connect(service.catalog.database) as conn:
        chars = [json.loads(r[0]) for r in conn.execute('SELECT state_json FROM characters ORDER BY json_extract(state_json,\'$.name\')')][:count]
    request = CreateEncounter(participants=[dict(character_id=c['id'], expected_version=c['version'],
        team=str(i), initiative=20-i, position=positions[i] if positions else {'x': i*(2 if far else 1), 'y':0}) for i,c in enumerate(chars)],
        clear_cells=[{'x': x,'y': y} for x in range(-1,10) for y in range(-1,3)],
        scene_confirmed=True, initiative_confirmed=True, distance_convention='five_ft_chebyshev',
        notes='DM confirms clear level ground, ordinary Fighter profiles and unconditional defenses.')
    return service.create(request)


def cmd(state, kind, *, actor=None, payload=None, **fields):
    return dict(type=kind, command_id=uuid4().hex, encounter_id=state.id,
        actor_id=actor or state.active_id or state.combatants[0].creature.id,
        expected_version=state.version, payload=payload or {}, **fields)


def execute(service, state, kind, **fields):
    result = service.execute(cmd(state, kind, **fields))
    return CombatState.model_validate(result['state']), result


def start(service, **kwargs):
    state = create(service, **kwargs)
    return execute(service, state, 'start_encounter', payload={'ties_confirmed': True})[0]


def counts(service):
    with connect(service.catalog.database) as conn:
        return tuple(conn.execute('SELECT count(*) FROM '+table).fetchone()[0] for table in ('commands','events'))


def test_scenario_a_multi_round_attack_persistence(service):
    state = start(service)
    actor, target = state.combatants
    state, result = execute(service, state, 'attack', target_id=target.creature.id, weapon_id=WEAPON,
        payload={**SCENE, 'fixed_dice':[15,2]})
    assert state.combatants[1].creature.hp.current == 7
    assert not state.combatants[0].budget.action
    event = result['events'][0]
    assert event['dice'] == [{'sides':20,'value':15},{'sides':8,'value':2}]
    assert event['payload']['resolution']['attack']['attack_total'] == 20
    assert event['runtime_adapter_refs'] and event['source_ids']
    for _ in range(4):
        state, _ = execute(service, state, 'end_turn')
    assert state.round == 3 and state.active_id == actor.creature.id
    assert state.combatants[0].budget.action
    reopened = Encounters(service.catalog, isolated_demo=True)
    replay = reopened.replay(state.id)
    assert replay['verified'] and replay['state'] == state.model_dump() == reopened.get(state.id).model_dump()
    with connect(service.catalog.database) as conn:
        assert Characters(service.catalog).load(conn,target.creature.id).hp.current == 12


def ready_window(service, *, count=2):
    state = start(service, far=True, count=count)
    a,b = state.combatants[:2]
    state,_ = execute(service,state,'ready',payload={'trigger_actor':b.creature.id,'weapon_id':WEAPON,
        'trigger':'actor_finishes_move_adjacent','perceivable_confirmed':True})
    state,_ = execute(service,state,'end_turn')
    state,_ = execute(service,state,'move',destination={'x':1,'y':0},payload={'path':[{'x':1,'y':0}],
        'scene_confirmed':True,'no_unmodeled_triggers':True})
    assert state.phase == 'reaction' and state.reaction_window.eligible_ids == [a.creature.id]
    return state


def test_scenario_b_ready_reaction_duration(service):
    state = ready_window(service)
    a,b = state.combatants
    trigger = state.reaction_window.trigger_event_id
    state,result = execute(service,state,'submit_reaction',actor=a.creature.id,
        payload={**SCENE,'fixed_dice':[15,2],'trigger_event_id':trigger})
    assert state.phase == 'action' and state.active_id == b.creature.id
    assert not state.combatants[0].budget.reaction and not any(e.active for e in state.effects)
    # Reaction refresh belongs to its owner's turn, not a blanket global-round reset.
    state,_ = execute(service,state,'end_turn')
    assert state.combatants[0].budget.reaction
    state,_ = execute(service,state,'ready',payload={'trigger_actor':b.creature.id,'weapon_id':WEAPON,
        'trigger':'actor_finishes_move_adjacent','perceivable_confirmed':True})
    active = [e for e in state.effects if e.active][0]
    assert active.rule_id == READY and active.source_refs and active.remaining_rounds == 1
    state,_ = execute(service,state,'end_turn')
    assert any(e.active for e in state.effects)
    state,_ = execute(service,state,'end_turn')
    expired = next(e for e in state.effects if e.id == active.id)
    assert not expired.active and expired.remaining_rounds == 0
    assert service.replay(state.id)['state'] == state.model_dump()


@pytest.mark.parametrize('stage',['after_command','after_event','after_snapshot'])
def test_scenario_c_failure_recovery_and_idempotence(service,stage):
    state=start(service,count=3)
    command=cmd(state,'attack',target_id=state.combatants[1].creature.id,weapon_id=WEAPON,payload={**SCENE,'fixed_dice':[15,2]})
    before=counts(service)
    def fail(at):
        if at == stage:raise RuntimeError('injected transaction failure')
    service.fault=fail
    with pytest.raises(RuntimeError):service.execute(command)
    assert service.get(state.id)==state and counts(service)==before
    service.fault=None
    first=service.execute(command)
    second=service.execute(command)
    assert second['idempotent'] and second['state']==first['state'] and second['events']==first['events']
    assert counts(service)==(before[0]+1,before[1]+1)
    with pytest.raises(RuleError,match='different content'):
        service.execute({**command,'payload':{**SCENE,'fixed_dice':[1]}})
    with pytest.raises(RuleError) as error:service.execute({**command,'command_id':uuid4().hex})
    assert error.value.code=='version_conflict'
    assert service.replay(state.id)['state']==first['state']
    with connect(service.catalog.database) as conn:
        conn.execute("UPDATE events SET after_hash=? WHERE encounter_id=? AND sequence=3",('0'*64,state.id))
    with pytest.raises(RuleError) as error:service.replay(state.id)
    assert error.value.code=='integrity_failure'


@pytest.mark.parametrize('same_id',[True,False])
def test_concurrent_duplicate_and_version_race(service,same_id):
    state=start(service)
    command=cmd(state,'attack',target_id=state.combatants[1].creature.id,weapon_id=WEAPON,payload={**SCENE,'fixed_dice':[15,2]})
    before=counts(service)
    other=command if same_id else {**command,'command_id':uuid4().hex}
    def run(value):
        try:return service.execute(value)
        except RuleError as exc:return exc.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(run,[command,other]))
    if same_id:assert sorted(r['idempotent'] for r in results)==[False,True]
    else:assert results.count('version_conflict')==1
    assert counts(service)==(before[0]+1,before[1]+1)
    assert service.replay(state.id)['verified']


@pytest.mark.parametrize('bad',['wrong_actor','unknown_target','wrong_weapon','range','budget','extra_hp','bad_dice','unknown_action','not_visible'])
def test_rejected_attack_no_writes(service,bad):
    state=start(service,far=bad=='range')
    target=state.combatants[1].creature.id
    command=cmd(state,'attack',target_id=target,weapon_id=WEAPON,payload={**SCENE,'fixed_dice':[15,2]})
    if bad=='wrong_actor':command['actor_id']=target
    elif bad=='unknown_target':command['target_id']='missing'
    elif bad=='wrong_weapon':command['weapon_id']='srd51.equipment.handaxe'
    elif bad=='budget':
        result=service.execute(command);state=CombatState.model_validate(result['state'])
        command.update(command_id=uuid4().hex,expected_version=state.version)
    elif bad=='extra_hp':command['payload']['target_hp']={'current':999}
    elif bad=='bad_dice':command['payload']['fixed_dice']=[15,99]
    elif bad=='unknown_action':command['type']='dash'
    elif bad=='not_visible':command['payload']['target_visible']=False
    before=counts(service)
    with pytest.raises(RuleError):service.execute(command)
    assert counts(service)==before and service.get(state.id)==state


@pytest.mark.parametrize('bad',['distance','unknown','occupied','opportunity','unconfirmed'])
def test_move_rejects_unsafe_or_unfunded(service,bad):
    state=start(service,far=True)
    path=[{'x':-1,'y':0}]
    if bad=='distance':path=[{'x':-1 if i%2==0 else 0,'y':0} for i in range(7)]
    elif bad=='unknown':path=[{'x':0,'y':-2}]
    elif bad=='occupied':path=[{'x':1,'y':0},{'x':2,'y':0}]
    elif bad=='opportunity':path=[{'x':1,'y':0},{'x':0,'y':0}]
    payload={'path':path,'scene_confirmed':True,'no_unmodeled_triggers':True}
    if bad=='unconfirmed':payload['scene_confirmed']=False
    before=counts(service)
    with pytest.raises(RuleError):service.execute(cmd(state,'move',destination=path[-1],payload=payload))
    assert counts(service)==before and service.get(state.id)==state


def test_move_and_turn_reset(service):
    state=start(service,far=True)
    state,_=execute(service,state,'move',destination={'x':0,'y':1},payload={
        'path':[{'x':0,'y':1}],'scene_confirmed':True,'no_unmodeled_triggers':True})
    assert state.combatants[0].budget.movement_ft==25
    state,_=execute(service,state,'end_turn');state,_=execute(service,state,'end_turn')
    assert state.combatants[0].budget.movement_ft==30


@pytest.mark.parametrize('bad',['actor','trigger','ordinary'])
def test_invalid_reactions_are_atomic(service,bad):
    state=ready_window(service)
    actor=state.combatants[0].creature.id
    trigger=state.reaction_window.trigger_event_id
    command=cmd(state,'decline_reaction',actor=actor,payload={'trigger_event_id':trigger})
    if bad=='actor':command['actor_id']=state.combatants[1].creature.id
    elif bad=='trigger':command['payload']['trigger_event_id']='wrong'
    else:command=cmd(state,'end_turn')
    before=counts(service)
    with pytest.raises(RuleError):service.execute(command)
    assert counts(service)==before and service.get(state.id)==state


def test_decline_retains_ready_and_reaction_then_expires(service):
    state=ready_window(service)
    command=cmd(state,'decline_reaction',actor=state.combatants[0].creature.id,
        payload={'trigger_event_id':state.reaction_window.trigger_event_id})
    result=service.execute(command);state=CombatState.model_validate(result['state'])
    assert state.phase=='action' and state.combatants[0].budget.reaction and state.effects[0].active
    assert service.execute(command)['idempotent']
    with pytest.raises(RuleError):service.execute({**command,'command_id':uuid4().hex,'expected_version':state.version})
    state,_=execute(service,state,'end_turn')
    assert not state.effects[0].active


def test_dm_marker_not_automatic_condition_and_end_cleanup(service):
    state=start(service)
    state,_=execute(service,state,'dm_adjustment',target_id=state.active_id,hp_delta=0,reason='DM records blinded pending adjudication',payload={'marker':'Blinded'})
    with pytest.raises(RuleError) as error:
        service.execute(cmd(state,'attack',target_id=state.combatants[1].creature.id,weapon_id=WEAPON,payload=SCENE))
    assert error.value.code=='unsupported_context'
    with pytest.raises(RuleError):
        service.execute(cmd(state,'dm_adjustment',target_id=state.active_id,hp_delta=0,reason='duplicate',payload={'marker':'Blinded'}))
    state,_=execute(service,state,'end_encounter',payload={'reason':'DM ends encounter'})
    assert not any(e.active for e in state.effects) and state.active_id is None
    with pytest.raises(RuleError) as error:service.execute(cmd(state,'end_turn'))
    assert error.value.code=='encounter_ended'
    assert service.replay(state.id)['state']==state.model_dump()


@pytest.mark.parametrize('tamper',['dice','metadata','delete','sequence','duplicate','snapshot','initial','receipt'])
def test_replay_detects_tampering(service,tamper):
    state=start(service)
    state,result=execute(service,state,'attack',target_id=state.combatants[1].creature.id,weapon_id=WEAPON,payload={**SCENE,'fixed_dice':[15,2]})
    with connect(service.catalog.database) as conn:
        if tamper in ('dice','metadata'):
            e=result['events'][0]
            if tamper=='dice':e['dice'][0]['value']=1
            else:e['payload']['resolution']['attack']['attack_total']=999
            conn.execute('UPDATE events SET payload_json=? WHERE id=?',(json.dumps(e),e['id']))
        elif tamper=='delete':conn.execute('DELETE FROM events WHERE encounter_id=? AND sequence=2',(state.id,))
        elif tamper=='sequence':conn.execute('UPDATE events SET sequence=99 WHERE encounter_id=? AND sequence=3',(state.id,))
        elif tamper=='duplicate':
            e=result['events'][0]
            conn.execute('''INSERT INTO events SELECT ?,command_id,encounter_id,99,before_hash,after_hash,payload_json,event_hash
                FROM events WHERE id=?''',(uuid4().hex,e['id']))
        elif tamper=='snapshot':conn.execute("UPDATE encounters SET state_hash='bad' WHERE id=?",(state.id,))
        elif tamper=='initial':conn.execute("UPDATE encounters SET initial_hash='bad' WHERE id=?",(state.id,))
        else:conn.execute("UPDATE commands SET request_hash='bad' WHERE encounter_id=?",(state.id,))
    with pytest.raises(RuleError) as error:service.replay(state.id)
    assert error.value.code=='integrity_failure'


def test_random_replay_without_rng_or_current_grants(service,monkeypatch):
    state=start(service)
    state,_=execute(service,state,'attack',target_id=state.combatants[1].creature.id,weapon_id=WEAPON,payload=SCENE)
    with connect(service.catalog.database) as conn:conn.execute('DELETE FROM runtime_grants')
    from ruleforge.combat.dice import Dice
    def forbidden(*a,**k):raise AssertionError('Replay must not roll')
    with monkeypatch.context() as replay_only:
        replay_only.setattr(Dice,'roll',forbidden)
        assert service.replay(state.id)['state']==state.model_dump()
    with pytest.raises(RuleError):service.execute(cmd(state,'end_turn'))


@pytest.mark.parametrize('tamper',['grant','adapter','review','publication'])
def test_current_runtime_revocation(service,tamper):
    state=start(service)
    with connect(service.catalog.database) as conn:
        if tamper=='grant':conn.execute('DELETE FROM runtime_grants WHERE record_id=?',(TURN,))
        elif tamper=='adapter':conn.execute("UPDATE runtime_grants SET adapter_sha256='bad' WHERE record_id=?",(TURN,))
        elif tamper=='review':conn.execute('DELETE FROM review_decisions WHERE record_id=?',(TURN,))
        else:conn.execute('UPDATE normalized_records SET published_at=NULL WHERE id=?',(TURN,))
    before=counts(service)
    with pytest.raises((RuleError,ValueError)):service.execute(cmd(state,'end_turn'))
    assert counts(service)==before and service.replay(state.id)['verified']


def test_api_auth_isolation_and_resume(service,monkeypatch):
    monkeypatch.setenv('RULEFORGE_ADMIN_TOKEN','test-local-dm')
    monkeypatch.setenv('RULEFORGE_DATABASE',str(service.catalog.database))
    prod=TestClient(create_app(ROOT))
    assert prod.get('/api/encounters').json()['error']['code']=='environment_mismatch'
    client=TestClient(create_app(ROOT,service.catalog.database,isolated_demo=True))
    state=start(service)
    command=cmd(state,'end_turn')
    assert client.post(f'/api/encounters/{state.id}/commands',json=command).status_code==403
    response=client.post(f'/api/encounters/{state.id}/commands',json=command,headers={'X-RuleForge-Admin':'test-local-dm'})
    assert response.status_code==200
    assert client.get(f'/api/encounters/{state.id}/state').json()==response.json()['state']
    assert client.get(f'/api/encounters/{state.id}/replay').json()['verified']
    assert client.get(f'/api/encounters/{state.id}/events').json()
    assert client.get('/api/encounters/participants').status_code==200
    assert client.post('/api/encounters/wrong/commands',json=command,headers={'X-RuleForge-Admin':'test-local-dm'}).status_code==422


def test_production_cannot_consume_simulated_review(service):
    with connect(service.catalog.database) as conn:
        conn.execute("UPDATE encounter_environment SET mode='production' WHERE id=1")
    production=Encounters(service.catalog)
    with pytest.raises(RuleError) as error:create(production)
    assert error.value.code=='simulated_review_forbidden'
    with pytest.raises(ValueError):prepare_isolated_demo(ROOT,ROOT/'data/ruleforge.sqlite3')
    with pytest.raises(ValueError):Encounters(CatalogService(ROOT,ROOT/'data/ruleforge.sqlite3'),isolated_demo=True)


def test_v3_v4_preserves_legacy_rows_and_is_idempotent(tmp_path):
    db=tmp_path/'migration.sqlite3'
    initialize(db,target_version=3)
    with connect(db) as conn:
        conn.execute("INSERT INTO encounters VALUES ('legacy',7,'{}')")
        conn.execute("INSERT INTO commands VALUES ('old','legacy',6,'{}','then')")
        conn.execute("INSERT INTO events VALUES ('old-event','old','legacy',1,'before','after','{}')")
        tables=[r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        columns={t:[r[1] for r in conn.execute('PRAGMA table_info('+t+')')] for t in tables}
        before={t:[tuple(r) for r in conn.execute('SELECT '+','.join(columns[t])+' FROM '+t)] for t in tables}
    initialize(db);initialize(db)
    with connect(db) as conn:
        assert conn.execute('PRAGMA user_version').fetchone()[0]==4
        assert before=={t:[tuple(r) for r in conn.execute('SELECT '+','.join(columns[t])+' FROM '+t)] for t in tables}
        assert conn.execute('PRAGMA foreign_key_check').fetchall()==[]
        conn.execute('PRAGMA user_version=5')
    with pytest.raises(ValueError):initialize(db)


def test_v4_migration_rolls_back_all_ddl(tmp_path,monkeypatch):
    db=tmp_path/'migration.sqlite3';initialize(db,target_version=3)
    read=Path.read_text
    def broken(path,*args,**kwargs):
        text=read(path,*args,**kwargs)
        return text+'; INSERT INTO missing VALUES (1);' if path.name=='migration_v4.sql' else text
    monkeypatch.setattr(Path,'read_text',broken)
    with pytest.raises(sqlite3.OperationalError):initialize(db)
    with connect(db) as conn:
        assert conn.execute('PRAGMA user_version').fetchone()[0]==3
        assert [r[1] for r in conn.execute('PRAGMA table_info(encounters)')]==['id','version','state_json']


def tiny(phase='setup'):
    active=phase not in ('setup','ended')
    return CombatState(id='pure',combatants=[Combatant(creature=Creature(id='a',name='A'),initiative=10),
        Combatant(creature=Creature(id='b',name='B'),initiative=10)],phase=phase,
        initiative_order=['a','b'] if active else [],active_id='a' if active else None,
        encounter_status='active' if active else phase,
        reaction_window=ReactionWindow(trigger_event_id='e',eligible_ids=['b'],resume_phase='action',
            triggering_actor='a',pending_reactions=['b'],response_status={'b':'pending'}) if phase=='reaction' else None)


@pytest.mark.parametrize('source',list(TRANSITIONS))
@pytest.mark.parametrize('destination',list(TRANSITIONS))
def test_pure_transition_matrix(source,destination):
    state=tiny(source)
    updates=tiny(destination).model_dump(exclude={'id','phase','combatants'})
    if destination in TRANSITIONS[source]:assert transition(state,destination,**updates).phase==destination
    else:
        with pytest.raises(RuleError):transition(state,destination,**updates)


def test_initiative_complete_ties_and_invalid():
    state=tiny()
    assert initiative(state,[])==['a','b']
    assert initiative(state,['b','a'])==['b','a']
    for order in [['a'],['a','a'],['a','unknown']]:
        with pytest.raises(RuleError):initiative(state,order)


@pytest.mark.parametrize('resource',['action','bonus_action','reaction','movement_ft'])
def test_budget_pure(resource):
    used=spend(ActionBudget(),resource,30 if resource=='movement_ft' else 1)
    with pytest.raises(RuleError):spend(ActionBudget(**used),resource)


def test_duration_is_owner_boundary_not_global_round():
    effects=[dict(active=True,duration_type='owner_turn_boundary',duration_owner_id='b',
                  expires_at_phase='turn_start',remaining_rounds=2)]
    assert expire(effects,'a','turn_start')==effects
    assert expire(effects,'b','turn_end')==effects
    once=expire(effects,'b','turn_start')
    assert once[0]['remaining_rounds']==1 and once[0]['active']
    assert not expire(once,'b','turn_start')[0]['active']
    assert effects[0]['remaining_rounds']==2


def test_cached_evidence_rechecks_before_transaction_commit(tmp_path):
    from ruleforge.ingestion.evidence import evidence_snapshot, checked_file, digest_bytes, EvidenceError
    artifact=tmp_path/'source.txt';artifact.write_bytes(b'original')
    ref={'path':'source.txt','sha256':digest_bytes(b'original')}
    db=tmp_path/'atomic.sqlite3';initialize(db)
    with pytest.raises(EvidenceError):
        with connect(db) as conn, evidence_snapshot(cache_files=True):
            conn.execute("INSERT INTO encounters(id,version,state_json) VALUES ('rollback',0,'{}')")
            checked_file(tmp_path,ref);checked_file(tmp_path,ref)
            artifact.write_bytes(b'changed')
    with connect(db) as conn:assert conn.execute('SELECT count(*) FROM encounters').fetchone()[0]==0


def test_multiple_ready_reactions_refresh_only_owner(service):
    state=start(service,count=3,positions=[{'x':0,'y':0},{'x':2,'y':1},{'x':3,'y':0}])
    a,b,c=[x.creature.id for x in state.combatants]
    ready={'trigger_actor':c,'weapon_id':WEAPON,'trigger':'actor_finishes_move_adjacent','perceivable_confirmed':True}
    state,_=execute(service,state,'ready',payload=ready)
    state,_=execute(service,state,'end_turn')
    state,_=execute(service,state,'ready',payload=ready)
    state,_=execute(service,state,'end_turn')
    state,_=execute(service,state,'move',destination={'x':1,'y':0},payload={
        'path':[{'x':2,'y':0},{'x':1,'y':0}],'scene_confirmed':True,'no_unmodeled_triggers':True})
    assert state.reaction_window.pending_reactions==[a,b]
    trigger=state.reaction_window.trigger_event_id
    with pytest.raises(RuleError):
        service.execute(cmd(state,'submit_reaction',actor=b,payload={**SCENE,'fixed_dice':[15,2],'trigger_event_id':trigger}))
    for responder in (a,b):
        state,_=execute(service,state,'submit_reaction',actor=responder,payload={**SCENE,'fixed_dice':[15,2],'trigger_event_id':trigger})
    assert state.phase=='action' and state.combatants[2].creature.hp.current==2
    assert not state.combatants[0].budget.reaction and not state.combatants[1].budget.reaction
    state,_=execute(service,state,'end_turn')
    assert state.round==2 and state.active_id==a
    assert state.combatants[0].budget.reaction and not state.combatants[1].budget.reaction
    state,_=execute(service,state,'end_turn')
    assert state.combatants[1].budget.reaction
    assert service.replay(state.id)['verified']


def test_zero_hp_and_explicit_dm_recovery(service):
    state=start(service)
    victim=state.combatants[1].creature.id
    state,_=execute(service,state,'attack',target_id=victim,weapon_id=WEAPON,payload={**SCENE,'fixed_dice':[20,8,8]})
    assert state.combatants[1].creature.hp.current==0 and state.combatants[1].status=='dm_required'
    state,_=execute(service,state,'end_turn')
    with pytest.raises(RuleError):service.execute(cmd(state,'ready',payload={'trigger_actor':state.combatants[0].creature.id,
        'weapon_id':WEAPON,'trigger':'actor_finishes_move_adjacent','perceivable_confirmed':True}))
    state,_=execute(service,state,'dm_adjustment',target_id=victim,hp_delta=3,reason='DM explicitly resolves recovery')
    assert state.combatants[1].status=='alive' and state.combatants[1].creature.hp.current==3
    assert service.replay(state.id)['verified']


def test_preflight_rejects_actor_and_phase_before_runtime(service,monkeypatch):
    from ruleforge.encounters.runtime import EncounterScope
    state=start(service)
    def forbidden(*args,**kwargs):raise AssertionError('Runtime called before actor/phase validation')
    monkeypatch.setattr(EncounterScope,'require',forbidden)
    with pytest.raises(RuleError) as error:
        service.execute(cmd(state,'attack',actor=state.combatants[1].creature.id,
            target_id=state.combatants[0].creature.id,weapon_id=WEAPON,payload=SCENE))
    assert error.value.code=='invalid_actor'
    with pytest.raises(RuleError) as error:
        service.execute(cmd(state,'start_encounter',payload={'ties_confirmed':True}))
    assert error.value.code=='invalid_phase'


def test_pure_transition_cannot_rewind_or_reidentify():
    state=tiny('action').model_copy(update={'round':3})
    for change in ({'round':2},{'id':'other'},{'version':1},{'event_sequence':1},{'environment':'isolated_demo'}):
        with pytest.raises(RuleError):transition(state,'turn_end',**change)
