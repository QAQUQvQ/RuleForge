"""M2 goldens and isolated lifecycle tests; never simulate approval in the real DB."""
import json
import copy
import random
import sqlite3
from pathlib import Path
import pytest
from pydantic import ValidationError
from fastapi.testclient import TestClient
from ruleforge.catalog.models import parse_record
from ruleforge.catalog.service import CatalogService, canonical
from ruleforge.combat.runtime import Runtime, templates, ResolutionScope
from ruleforge.combat.demo import prepare_isolated_demo, run_demo
from ruleforge.combat.characters import Characters, CreateCharacter, PatchCharacter, FIGHTER, ARMOR
from ruleforge.combat.service import PreviewRequest, preview
from ruleforge.combat.attacks import AttackContext, attack
from ruleforge.combat.dice import Dice
from ruleforge.combat.damage import DamageComponent, Defenses, damage, apply_hp
from ruleforge.combat.modifiers import armor_class, ability_modifier, proficiency
from ruleforge.combat.errors import RuleError
from ruleforge.combat.verification import fixed_tests
from ruleforge.combat.ac import EquipmentACRequest, equipment_ac
from ruleforge.domain.models import Abilities, HitPoints
from ruleforge.ingestion.evidence import EvidenceError, evidence_snapshot
from ruleforge.persistence.db import connect, initialize, rollback_v3
from ruleforge.api import create_app

ROOT=Path(__file__).resolve().parents[2]


@pytest.fixture(scope='module')
def prepared(tmp_path_factory):
    database=tmp_path_factory.mktemp('m2')/'m2-demo-fixture.sqlite3'
    return prepare_isolated_demo(ROOT,database)


@pytest.fixture
def catalog(prepared,tmp_path):
    database=tmp_path/'m2-demo-copy.sqlite3'
    with sqlite3.connect(prepared.database) as src, sqlite3.connect(database) as dest:
        src.backup(dest)
    return CatalogService(ROOT,database)


def equipment(name):
    return parse_record(templates()['srd51.equipment.'+name]['record']).normalized_payload


def context(**changes):
    return AttackContext(**dict(dict(mode='melee',distance_ft=5,scene_confirmed=True,target_visible=True,
        cover='none',hostile_within_5ft=False),**changes))


def creation(**changes):
    return CreateCharacter(**dict(dict(name='Test Fighter',abilities={'strength':16,'dexterity':14,'constitution':14},
        speed_ft=30,origin_confirmed=True,skills=['Athletics','Perception']),**changes))


@pytest.mark.parametrize('score,expected',[(1,-5),(2,-4),(9,-1),(10,0),(11,0),(14,2),(29,9),(30,10)])
def test_modifiers(score,expected):
    assert ability_modifier(score)==expected


@pytest.mark.parametrize('bad',[0,31,True,'14',14.5])
def test_creation_invalid_abilities(bad):
    with pytest.raises(ValidationError):creation(abilities={'strength':bad})


@pytest.mark.parametrize('level,pb',[(1,2),(4,2),(5,3),(8,3),(9,4),(13,5),(17,6),(20,6)])
def test_proficiency(level,pb):
    assert proficiency(level)==pb


@pytest.mark.parametrize('armor,dex,shield,expected',[
    (None,14,False,12),('leather',14,False,13),('chain-shirt',18,False,15),('chain-shirt',9,False,12),
    ('chain-mail',18,False,16),('chain-mail',9,False,16),('chain-mail',9,True,18)])
def test_ac_arithmetic(armor,dex,shield,expected):
    # Unarmored arithmetic vector does not confer runtime source authorization.
    assert armor_class(dex,equipment(armor) if armor else None,equipment('shield') if shield else None)['ac']==expected


@pytest.mark.parametrize('expression',['1d4','2d6+2','1d8','1d10','1d12','1d20','1d100','1d6-2'])
def test_dice_seed_reproducible(expression):
    assert Dice(rng=random.Random(123)).roll(expression)==Dice(rng=random.Random(123)).roll(expression)


@pytest.mark.parametrize('expression',['d6','0d6','100d6','999999d6','1d3','1d6+1000','1d6;print(1)','1d6+1d4','1d6 + 2'])
def test_dice_rejects(expression):
    with pytest.raises(RuleError,match='Expected'):Dice().roll(expression)


def test_dice_stream_validation_and_log():
    d=Dice(fixed=[1,4]);assert d.roll('2d4-1')['total']==4
    assert d.log==[{'sides':4,'value':1},{'sides':4,'value':4}];d.finish()
    for fixed in [[True],[0],[101]]:
        with pytest.raises(RuleError):Dice(fixed=fixed)
    with pytest.raises(RuleError):Dice(fixed=[]).roll('1d20')
    with pytest.raises(RuleError):Dice(fixed=[8]).roll('1d4')
    with pytest.raises(RuleError):Dice(fixed=[1]).finish()
    d=Dice(fixed=[1]*1000)
    for _ in range(10):d.roll('99d4')
    with pytest.raises(RuleError):d.roll('11d4')


@pytest.mark.parametrize('rolls,flags,hit,selected',[
    ([10],{},True,10),([9],{},False,9),([1],{},False,1),([20],{},True,20),
    ([3,18],{'advantage':True},True,18),([3,18],{'disadvantage':True},False,3),
    ([10],{'advantage':True,'disadvantage':True},True,10)])
def test_attacks(rolls,flags,hit,selected):
    r=attack('a','b',equipment('dagger'),Abilities(dexterity=14),True,2,14,context(**flags),Dice(fixed=rolls))
    assert (r.hit,r.selected_d20,r.critical)==(hit,selected,selected==20)
    assert r.ability=='dexterity' and r.attack_modifier==4
    assert attack('a','b',equipment('dagger'),Abilities(dexterity=14),True,2,14,context(**flags),Dice(fixed=rolls))==r


def test_finesse_proficiency_and_thrown_ranges():
    r=attack('a','b',equipment('dagger'),Abilities(strength=16,dexterity=14),False,2,15,
             context(ability='dexterity'),Dice(fixed=[12]))
    assert r.attack_modifier==2 and not r.hit
    r=attack('a','b',equipment('handaxe'),Abilities(strength=16,dexterity=18),True,2,15,
             context(mode='ranged',distance_ft=30),Dice(fixed=[18,11]))
    assert r.ability=='strength' and r.selected_d20==11 and 'long_range' in r.applied_conditions
    with pytest.raises(RuleError):attack('a','b',equipment('handaxe'),Abilities(),True,2,15,
             context(mode='ranged',distance_ft=61),Dice(fixed=[20]))
    with pytest.raises(RuleError):attack('a','b',equipment('longsword'),Abilities(),True,2,15,
             context(mode='ranged'),Dice(fixed=[20]))
    with pytest.raises(RuleError):attack('a','b',equipment('handaxe'),Abilities(),True,2,15,
             context(ability='dexterity'),Dice(fixed=[20]))
    r=attack('a','b',equipment('dagger'),Abilities(),True,2,15,
             context(mode='ranged',hostile_within_5ft=True,advantage=True),Dice(fixed=[20]))
    assert r.selected_d20==20 and 'cancelled' in r.applied_conditions


@pytest.mark.parametrize('changes',[{'distance_ft':6},{'special_mechanics':['spell attack']}, {'special_mechanics':['extra attack']}])
def test_unsupported_attack(changes):
    with pytest.raises(RuleError):attack('a','b',equipment('dagger'),Abilities(),True,2,10,context(**changes),Dice(fixed=[20]))


@pytest.mark.parametrize('changes',[{'scene_confirmed':False},{'cover':'half'},{'target_visible':False}])
def test_scene_not_assumed(changes):
    with pytest.raises(ValidationError):context(**changes)


@pytest.mark.parametrize('defenses,expected',[
    ({},7),({'resistance':['piercing']},3),({'vulnerability':['piercing']},14),
    ({'resistance':['piercing'],'vulnerability':['piercing']},6),
    ({'immunity':['piercing'],'vulnerability':['piercing']},0),
    ({'resistance':['piercing','piercing']},3)])
def test_damage_defenses(defenses,expected):
    r=damage([DamageComponent(damage_type='piercing',dice={'expression':'1d4'},modifier=3)],Defenses(**defenses),Dice(fixed=[4]))
    assert r['total']==expected


def test_critical_and_independent_damage():
    r=damage([DamageComponent(damage_type='piercing',dice={'expression':'1d4+1'},modifier=3),
              DamageComponent(damage_type='fire',dice={'expression':'1d6'})],Defenses(resistance=['piercing']),
              Dice(fixed=[3,4,5,6]),critical=True)
    assert r['components'][0]['raw_damage']==11 # 3+4+1+3; fixed bonuses once
    assert r['total']==5+11
    assert damage([DamageComponent(damage_type='cold',dice={'expression':'1d4'},modifier=-5)],Defenses(),Dice(fixed=[1]))['total']==0
    with pytest.raises(ValidationError):DamageComponent(damage_type='magic',dice={'expression':'1d4'})
    with pytest.raises(ValidationError):Defenses(immunity=['typo'])


def test_hp_boundaries():
    hp=HitPoints(maximum=10,current=5,temporary=3)
    r=apply_hp(hp,6);assert r['after']=={'maximum':10,'current':2,'temporary':0}
    r=apply_hp(hp,18);assert r['overflow']==10 and r['instant_death_threshold_met'] and r['status']=='dm_or_m3_required'
    r=apply_hp(HitPoints(maximum=10,current=0,temporary=1),2,critical=True)
    assert r['damage_at_zero'] and r['death_save_failures_pending']==2
    assert apply_hp(hp,3)['after']['current']==5
    with pytest.raises(ValidationError):HitPoints(maximum=5,current=6)
    with pytest.raises(RuleError):apply_hp(hp,-1)


def test_runtime_goldens():
    assert fixed_tests()['status']=='passed'


@pytest.mark.evidence
def test_search_and_api_permissions(catalog,monkeypatch):
    with connect(catalog.database) as conn:conn.execute("UPDATE normalized_records SET published_at=NULL WHERE id=?",(FIGHTER,))
    monkeypatch.setenv('RULEFORGE_ADMIN_TOKEN','isolated-test-token')
    client=TestClient(create_app(ROOT,catalog.database))
    assert client.get('/api/catalog/'+FIGHTER).status_code==404
    assert client.get('/api/admin/catalog').status_code==403
    found=client.get('/api/admin/catalog',headers={'X-RuleForge-Admin':'isolated-test-token'},params={'q':FIGHTER}).json()
    assert found['total']==1 and found['items'][0]['record']['id']==FIGHTER
    assert client.get('/api/search',params={'q':'dagger','record_type':'equipment'}).json()['total']==1
    assert client.get('/api/catalog/no-such-record').status_code==404
    assert client.get('/api/catalog',params={'record_type':'bad'}).status_code==422
    sources=client.get('/api/catalog/srd51.equipment.dagger/sources').json()
    assert {s['physical_page'] for s in sources}=={65,66}
    assert all(s['json_pointer'].startswith('/data/elements/') and s['quote'] for s in sources)
    assert catalog.search('匕首')['total']==0 # no invented aliases


@pytest.mark.evidence
def test_character_crud_and_equipment_atomicity(catalog):
    chars=Characters(catalog)
    card=chars.create(creation());char=card['character'];cid=char['id']
    assert char['hp']=={'maximum':12,'current':12,'temporary':0}
    assert char['proficiency_bonus']==2 and len(char['inventory'])==5
    assert Characters(CatalogService(ROOT,catalog.database)).get(cid)==card
    changed=chars.patch(cid,PatchCharacter(expected_version=1,name='Changed',abilities={'constitution':16,'dexterity':9}))
    assert changed['character']['version']==2 and changed['character']['hp']['maximum']==13
    with pytest.raises(RuleError,match='reload'):chars.patch(cid,PatchCharacter(expected_version=1,name='Stale'))
    inventory=copy.deepcopy(changed['character']['inventory']);inventory[0]['equipment_record_id']='unknown'
    with pytest.raises(RuleError):chars.patch(cid,PatchCharacter(expected_version=2,inventory=inventory))
    assert chars.get(cid)==changed
    inventory=copy.deepcopy(changed['character']['inventory']);inventory.append(dict(inventory[0]))
    with pytest.raises(RuleError):chars.patch(cid,PatchCharacter(expected_version=2,inventory=inventory))
    assert chars.get(cid)==changed


@pytest.mark.evidence
def test_ac_runtime_and_unarmored_fail_closed(catalog):
    chars=Characters(catalog);card=chars.create(creation());char=card['character']
    result=chars.ac(char['id']);assert result['ac']==19 and result['source_refs'] and result['rule_refs']
    for i in char['inventory']:
        if i['equipment_slot']=='body':i.update(equipped=False,equipment_slot='inventory')
    chars.patch(char['id'],PatchCharacter(expected_version=1,inventory=char['inventory']))
    with pytest.raises(RuleError,match='unarmored'):chars.ac(char['id'])


@pytest.mark.evidence
@pytest.mark.parametrize('tamper',['grant','code','source','review','publication','validation','relation','execution','record'])
def test_runtime_revokes_on_any_binding_change(catalog,tamper):
    with connect(catalog.database) as conn:
        if tamper=='grant':conn.execute('DELETE FROM runtime_grants WHERE record_id=?',(FIGHTER,))
        elif tamper=='code':conn.execute("UPDATE runtime_grants SET adapter_sha256='changed' WHERE record_id=?",(FIGHTER,))
        elif tamper=='source':
            ref=json.loads(conn.execute('SELECT reference_json FROM source_references WHERE id=?',('srd51-full-001:element:552',)).fetchone()[0])
            ref['quote_sha256']='0'*64
            conn.execute('UPDATE source_references SET reference_json=? WHERE id=?',(json.dumps(ref),ref['id']))
        elif tamper=='review':conn.execute('DELETE FROM review_decisions WHERE record_id=?',(FIGHTER,))
        elif tamper=='publication':conn.execute('UPDATE normalized_records SET published_at=NULL WHERE id=?',(FIGHTER,))
        elif tamper=='validation':conn.execute("UPDATE normalized_records SET validation_json='{}' WHERE id=?",(FIGHTER,))
        elif tamper=='relation':conn.execute('DELETE FROM record_sources WHERE record_id=?',(FIGHTER,))
        else:
            row=conn.execute('SELECT record_json FROM normalized_records WHERE id=?',(FIGHTER,)).fetchone()
            value=json.loads(row[0]);value['execution_status' if tamper=='execution' else 'canonical_name']='executable' if tamper=='execution' else 'forged'
            conn.execute('UPDATE normalized_records SET record_json=? WHERE id=?',(json.dumps(value),FIGHTER))
    with pytest.raises((RuleError,EvidenceError)):
        Characters(catalog).create(creation())
    with connect(catalog.database) as conn:assert conn.execute('SELECT count(*) FROM characters').fetchone()[0]==0


@pytest.mark.evidence
def test_e2e_api_and_repeated_preview(catalog):
    demo=run_demo(catalog)
    assert demo['repeated_identical'] and demo['result']['hp']['after']['current']==18
    client=TestClient(create_app(ROOT,catalog.database))
    request=demo['preview_input']
    first=client.post('/api/combat/preview',json=request)
    assert first.status_code==200 and first.json()==demo['result']
    assert client.post('/api/combat/preview',json=request).json()==first.json()
    request['fixed_dice']=[1]
    missed=client.post('/api/combat/preview',json=request).json()
    assert not missed['attack']['hit'] and missed['damage']['total']==0 and missed['hp']['after']['current']==20
    request['fixed_dice']=[20,8,8]
    assert client.post('/api/combat/preview',json=request).json()['damage']['total']==9
    request['fixed_dice']=[2,99]
    assert client.post('/api/combat/preview',json=request).json()['error']['code']=='invalid_dice'
    request['expected_version']=999
    assert client.post('/api/combat/preview',json=request).status_code==409
    assert client.get('/api/characters/'+demo['character']['character']['id']).json()['character']['hp']['current']==12


def test_v2_v3_lossless_and_rollback(tmp_path):
    db=tmp_path/'v2.sqlite3'
    with connect(db) as conn:
        conn.executescript((ROOT/'backend/ruleforge/persistence/schema.sql').read_text())
        conn.executescript((ROOT/'backend/ruleforge/persistence/migration_v2.sql').read_text())
        conn.execute("INSERT INTO characters VALUES ('sentinel',7,'{}')")
        tables=[r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        before={t:[tuple(r) for r in conn.execute('SELECT * FROM '+t)] for t in tables}
    initialize(db,target_version=3);initialize(db,target_version=3)
    with connect(db) as conn:
        assert conn.execute('PRAGMA user_version').fetchone()[0]==3
        assert before=={t:[tuple(r) for r in conn.execute('SELECT * FROM '+t)] for t in tables}
        assert conn.execute('PRAGMA foreign_key_check').fetchall()==[]
    rollback_v3(db)
    with connect(db) as conn:assert conn.execute('PRAGMA user_version').fetchone()[0]==2
    initialize(db,target_version=3)


def test_v3_migration_failure_atomic(tmp_path,monkeypatch):
    db=tmp_path/'db.sqlite3'
    with connect(db) as conn:
        conn.executescript((ROOT/'backend/ruleforge/persistence/schema.sql').read_text())
        conn.executescript((ROOT/'backend/ruleforge/persistence/migration_v2.sql').read_text())
    original=Path.read_text
    def broken(path,*args,**kwargs):
        value=original(path,*args,**kwargs)
        return value+'\nINSERT INTO nonexistent VALUES (1);' if path.name=='migration_v3.sql' else value
    monkeypatch.setattr(Path,'read_text',broken)
    with pytest.raises(sqlite3.OperationalError):initialize(db)
    with connect(db) as conn:
        assert conn.execute('PRAGMA user_version').fetchone()[0]==2
        assert not conn.execute("SELECT name FROM sqlite_master WHERE name='runtime_grants'").fetchall()


def test_demo_cannot_approve_real_database():
    with pytest.raises(ValueError):prepare_isolated_demo(ROOT,ROOT/'data/ruleforge.sqlite3')


@pytest.mark.evidence
def test_rollback_refuses_data_loss(catalog):
    with pytest.raises(ValueError,match='rollback requires v3'):rollback_v3(catalog.database)
    # Retain the historical v3 data-loss guard as well as the new v4 refusal.
    with connect(catalog.database) as conn:conn.execute('PRAGMA user_version=3')
    with pytest.raises(ValueError,match='M2 data'):rollback_v3(catalog.database)
    with connect(catalog.database) as conn:conn.execute('PRAGMA user_version=4')


@pytest.mark.evidence
def test_authorized_ac_vectors(catalog):
    chars=Characters(catalog)
    for name,dex,shield,expected in [('leather',14,False,13),('chain-shirt',18,False,15),
            ('chain-shirt',9,False,12),('chain-mail',9,False,16),('chain-mail',18,True,18)]:
        request=EquipmentACRequest(abilities={'dexterity':dex},armor={'id':'srd51.equipment.'+name},
                                   shield={'id':'srd51.equipment.shield'} if shield else None)
        result=equipment_ac(chars,request)
        assert result['ac']==expected and result['equipment_consequences']['armor_nonproficiency']
        assert result['equipment_refs'] and result['source_refs']
    with pytest.raises(RuleError):equipment_ac(chars,EquipmentACRequest(abilities={},armor={'id':'srd51.equipment.dagger'}))


@pytest.mark.evidence
def test_explicit_alias_and_no_implicit_execution(catalog):
    candidate=parse_record(templates()['srd51.equipment.dagger']['record'])
    value=candidate.model_dump();value.update(record_version=2,aliases=['测试登记的匕首别名'])
    catalog.create_candidate(value,templates()[candidate.id]['sources'])
    assert catalog.search('测试登记的匕首别名')['total']==0
    assert catalog.search('测试登记的匕首别名',published_only=False)['total']==1
    with pytest.raises(RuleError):Runtime(catalog).register(candidate.id,2)


@pytest.mark.evidence
def test_review_revocation_blocks_existing_character(catalog):
    chars=Characters(catalog);cid=chars.create(creation())['character']['id']
    catalog.review_candidate(ARMOR,'rejected','SIMULATED-TEST-REVIEW','Test revocation')
    with pytest.raises(RuleError):chars.ac(cid)
