"""Run A/B/C using a NEW isolated DB. Only explicit invocation simulates reviews."""
import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4
from ruleforge.combat.characters import Characters, CreateCharacter
from ruleforge.combat.errors import RuleError
from ruleforge.domain.models import CombatState
from ruleforge.encounters.contracts import CreateEncounter
from ruleforge.encounters.demo import prepare_isolated_demo
from ruleforge.encounters.service import Encounters
from ruleforge.encounters.machine import state_hash
from ruleforge.persistence.db import connect

WEAPON = 'srd51.equipment.longsword'
SCENE = dict(scene_confirmed=True, target_visible=True, cover='none')


def summary(state):
    return dict(id=state.id, version=state.version, round=state.round, phase=state.phase,
        active_id=state.active_id, event_sequence=state.event_sequence, hash=state_hash(state),
        combatants=[dict(id=c.creature.id, name=c.creature.name, hp=c.creature.hp.model_dump(),
            budget=c.budget.model_dump(), position=c.position.model_dump(), status=c.status) for c in state.combatants],
        effects=[e.model_dump(exclude={'source_refs'}) for e in state.effects],
        reaction_window=state.reaction_window.model_dump() if state.reaction_window else None)


def run(root, database):
    catalog = prepare_isolated_demo(root, database)
    service = Encounters(catalog, isolated_demo=True)
    chars = [Characters(catalog).create(CreateCharacter(name=name,
        abilities={'strength':16,'dexterity':14,'constitution':14}, skills=['Athletics','Perception'],
        speed_ft=30, origin_confirmed=True))['character'] for name in ('Alpha','Beta','Gamma')]
    report = {'environment':'isolated_demo', 'review':'SIMULATED-TEST-REVIEW; not production approval',
              'database':str(database.resolve()), 'scenarios':{}}

    def create(label, count=2, far=False):
        request = CreateEncounter(participants=[dict(character_id=c['id'],expected_version=c['version'],team=str(i),
            initiative=20-i,position={'x':i*(2 if far else 1),'y':0}) for i,c in enumerate(chars[:count])],
            clear_cells=[{'x':x,'y':y} for x in range(-1,10) for y in range(-1,3)],
            scene_confirmed=True,initiative_confirmed=True,distance_convention='five_ft_chebyshev',
            notes='Explicit DM confirmation: clear ground, ordinary combatants, no extra defenses or mechanics.')
        state=service.create(request)
        report['scenarios'][label]={'create_input':request.model_dump(),'initial':summary(state),'commands':[]}
        return state

    def command(state, kind, actor=None, payload=None, **fields):
        return dict(command_id=uuid4().hex, encounter_id=state.id, actor_id=actor or state.active_id or chars[0]['id'],
            expected_version=state.version, type=kind, payload=payload or {}, **fields)

    def apply(label, request):
        result=service.execute(request)
        state=CombatState.model_validate(result['state'])
        report['scenarios'][label]['commands'].append({'input':request,'output':summary(state),
            'idempotent':result['idempotent'],'events':[{k:e[k] for k in ('id','sequence','type','dice','rule_refs',
                'source_ids','runtime_adapter_refs','before_hash','after_hash','event_hash')} |
                {'resolution':e['payload']['resolution']} for e in result['events']]})
        return state

    def finish(label, state):
        replay=service.replay(state.id)
        assert replay['state']==state.model_dump()
        report['scenarios'][label]['replay']={k:replay[k] for k in ('verified','state_hash','event_head','authorization')}
        report['scenarios'][label]['final']=summary(state)

    state=create('A')
    state=apply('A',command(state,'start_encounter',payload={'ties_confirmed':True}))
    for _ in range(2):
        state=apply('A',command(state,'attack',target_id=chars[1]['id'],weapon_id=WEAPON,payload={**SCENE,'fixed_dice':[15,1]}))
        state=apply('A',command(state,'end_turn'))
        state=apply('A',command(state,'end_turn'))
    finish('A',state)

    state=create('B',far=True)
    state=apply('B',command(state,'start_encounter',payload={'ties_confirmed':True}))
    ready=dict(trigger_actor=chars[1]['id'],weapon_id=WEAPON,trigger='actor_finishes_move_adjacent',perceivable_confirmed=True)
    state=apply('B',command(state,'ready',payload=ready))
    state=apply('B',command(state,'end_turn'))
    state=apply('B',command(state,'move',destination={'x':1,'y':0},payload={
        'path':[{'x':1,'y':0}],'scene_confirmed':True,'no_unmodeled_triggers':True}))
    state=apply('B',command(state,'submit_reaction',actor=chars[0]['id'],payload={**SCENE,'fixed_dice':[15,2],
        'trigger_event_id':state.reaction_window.trigger_event_id}))
    state=apply('B',command(state,'end_turn'))
    state=apply('B',command(state,'ready',payload=ready))
    state=apply('B',command(state,'end_turn'));state=apply('B',command(state,'end_turn'))
    assert not any(e.active for e in state.effects)
    finish('B',state)

    state=create('C',count=3)
    state=apply('C',command(state,'start_encounter',payload={'ties_confirmed':True}))
    attack=command(state,'attack',target_id=chars[1]['id'],weapon_id=WEAPON,payload={**SCENE,'fixed_dice':[15,2]})
    faults=[]
    for stage in ('after_command','after_event','after_snapshot'):
        def fail(at):
            if at==stage:raise RuntimeError('injected '+stage)
        service.fault=fail
        try:service.execute(attack)
        except RuntimeError as exc:faults.append({'stage':stage,'error':str(exc),'rolled_back':service.get(state.id)==state})
        else:raise AssertionError('Failure hook was not called')
    service.fault=None
    report['scenarios']['C']['faults']=faults
    state=apply('C',attack)
    repeated=service.execute(attack)
    assert repeated['idempotent'] and repeated['state']==state.model_dump()
    report['scenarios']['C']['duplicate']={'input':attack,'idempotent':True,'unchanged':True}
    try:service.execute({**attack,'command_id':uuid4().hex})
    except RuleError as exc:report['scenarios']['C']['stale_version']=exc.code
    else:raise AssertionError('Stale version accepted')
    retry=command(state,'end_turn')
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(service.execute,[retry,retry]))
    assert sorted(r['idempotent'] for r in results)==[False,True]
    state=service.get(state.id)
    report['scenarios']['C']['concurrent_duplicate']={'input':retry,'idempotent_flags':[r['idempotent'] for r in results]}
    attempts=[command(state,'end_turn'),command(state,'end_turn')]
    def competing(request):
        try:return service.execute(request)
        except RuleError as exc:return exc.code
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(competing,attempts))
    assert results.count('version_conflict')==1
    report['scenarios']['C']['version_race']={'inputs':attempts,'outcomes':['committed' if isinstance(r,dict) else r for r in results]}
    state=service.get(state.id)
    finish('C',state)
    with connect(database) as conn:
        saved=conn.execute('SELECT id,payload_json FROM events WHERE encounter_id=? AND sequence=3',(state.id,)).fetchone()
        event=json.loads(saved['payload_json']);event['dice'][0]['value']=1
        conn.execute('UPDATE events SET payload_json=? WHERE id=?',(json.dumps(event),saved['id']))
    try:service.replay(state.id)
    except RuleError as exc:report['scenarios']['C']['tampered_history']=exc.code
    else:raise AssertionError('Tampered event accepted')
    with connect(database) as conn:conn.execute('UPDATE events SET payload_json=? WHERE id=?',(saved['payload_json'],saved['id']))
    assert service.replay(state.id)['verified']
    with connect(database) as conn:
        report['sqlite_version']=conn.execute('PRAGMA user_version').fetchone()[0]
        report['foreign_key_errors']=[tuple(r) for r in conn.execute('PRAGMA foreign_key_check')]
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--database',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result=run(args.root,args.database)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({label:data['replay'] for label,data in result['scenarios'].items()},indent=2))
