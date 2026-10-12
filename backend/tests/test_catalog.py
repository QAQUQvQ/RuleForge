"""Synthetic schema unit tests; real evidence tests are explicitly marked below."""
import copy
import json
import shutil
import sqlite3
from pathlib import Path
import pytest
from pydantic import TypeAdapter, ValidationError
from ruleforge.catalog.equipment import DiceExpression, EquipmentUnion
from ruleforge.catalog.models import RECORD_ADAPTER, parse_record
from ruleforge.catalog.service import CatalogService, transition
from ruleforge.rules.sources import SourceReference
from ruleforge.ingestion.evidence import EvidenceError, json_pointer, verify_reference
from ruleforge.ingestion.pipeline import ExtractionContext, EXTRACTORS, run_pipeline
from ruleforge.ingestion.tables import table_grid
from ruleforge.persistence.db import initialize, connect

ROOT=Path(__file__).resolve().parents[2]
RUN='srd51-full-001'

@pytest.fixture(scope='module')
def samples():
    # Never fabricate successful xParse evidence.
    ctx=ExtractionContext(ROOT,RUN)
    return {record.id:(record,sources) for fn in EXTRACTORS.values() for record,sources in fn(ctx)}

@pytest.fixture
def catalog(tmp_path,samples):
    service=CatalogService(ROOT,tmp_path/'catalog.sqlite3')
    record,sources=samples['srd51.general_rule.ability-modifier']
    service.create_candidate(record,sources)
    return service,record,sources

@pytest.mark.parametrize('value',['1d4','2d6','1d8+2','1d10-1','1d12','1d20','1d100'])
def test_dice_valid(value):
    assert DiceExpression(expression=value).expression==value

@pytest.mark.parametrize('value',['0d6','100d6','1d3','1d14','d6','-1d6','1d6+1d4','1d6*2','1d6;eval(1)','1d6 + 1','1d6+1000'])
def test_dice_invalid(value):
    with pytest.raises(ValidationError):
        DiceExpression(expression=value)

@pytest.mark.evidence
@pytest.mark.parametrize('record_id',[
    'srd51.equipment.dagger','srd51.equipment.leather','srd51.equipment.chain-shirt',
    'srd51.equipment.chain-mail','srd51.equipment.shield','srd51.equipment.torch',
    'srd51.spell.magic-missile','srd51.class.barbarian','srd51.condition.blinded','srd51.general_rule.ability-modifier'])
def test_record_roundtrip_and_schema(samples,record_id):
    record,sources=samples[record_id]
    assert parse_record(record.model_dump_json())==record
    assert parse_record(record.model_dump())==record
    schema=RECORD_ADAPTER.json_schema()
    assert len(schema['discriminator']['mapping'])==5
    assert record.validation_status=='extracted'
    assert record.review_status=='review_required'
    assert record.execution_status=='reference_only'
    assert all(SourceReference.model_validate_json(s.model_dump_json())==s for s in sources)

@pytest.mark.evidence
@pytest.mark.parametrize('ruleset',['srd-5.2','dnd-3.5','homebrew'])
def test_ruleset_rejected(samples,ruleset):
    record,sources=samples['srd51.equipment.dagger']
    for where in ['record','payload','source']:
        data=record.model_dump() if where!='source' else sources[0].model_dump()
        if where=='payload':
            data['normalized_payload']['ruleset']=ruleset
        else:
            data['ruleset']=ruleset
        with pytest.raises(ValidationError):
            SourceReference.model_validate(data) if where=='source' else parse_record(data)

@pytest.mark.evidence
@pytest.mark.parametrize('change',[
    {'equipment_type':'shield'}, {'damage_dice':{'expression':'1d14'}},
    {'normal_range':100}, {'weapon_properties':['finesse','finesse']},
    {'versatile_damage_dice':{'expression':'1d8'}}, {'weapon_properties':['thrown'],'normal_range':None,'long_range':None}])
def test_weapon_discrimination_and_invariants(samples,change):
    data=samples['srd51.equipment.dagger'][0].normalized_payload.model_dump()
    data.update(change)
    with pytest.raises(ValidationError):
        TypeAdapter(EquipmentUnion).validate_python(data)

@pytest.mark.evidence
@pytest.mark.parametrize('name,change',[
    ('leather',{'dexterity_modifier_policy':'none'}),
    ('chain-shirt',{'dexterity_modifier_cap':3}),
    ('chain-mail',{'dexterity_modifier_cap':2}),
    ('shield',{'armor_category':'heavy'}),
    ('torch',{'base_ac':12})])
def test_equipment_type_constraints(samples,name,change):
    data=samples['srd51.equipment.'+name][0].normalized_payload.model_dump();data.update(change)
    with pytest.raises(ValidationError):
        TypeAdapter(EquipmentUnion).validate_python(data)

@pytest.mark.evidence
def test_multisource_and_nested_reference_contract(samples):
    record=samples['srd51.spell.magic-missile'][0]
    assert len(record.source_ids)>3
    data=record.model_dump();data['normalized_payload']['damage'][0]['source_ids']=['missing']
    with pytest.raises(ValidationError):
        parse_record(data)
    data=record.model_dump();data['field_sources']['range']=['missing']
    with pytest.raises(ValidationError):
        parse_record(data)

@pytest.mark.evidence
def test_real_payload_values_and_class_grid(samples):
    get=lambda key:samples[key][0].normalized_payload
    dagger=get('srd51.equipment.dagger')
    assert dagger.damage_dice.expression=='1d4' and dagger.normal_range==20 and dagger.long_range==60
    assert set(dagger.weapon_properties)=={'finesse','light','thrown'}
    assert get('srd51.equipment.leather').base_ac==11
    assert get('srd51.equipment.chain-shirt').dexterity_modifier_cap==2
    assert get('srd51.equipment.chain-mail').strength_requirement==13
    assert get('srd51.equipment.shield').ac_bonus==2
    spell=get('srd51.spell.magic-missile')
    assert spell.level==1 and spell.school=='evocation' and spell.range=='120 feet'
    assert spell.damage[0].dice.expression=='1d4+1' and spell.damage[0].per=='dart'
    cls=get('srd51.class.barbarian')
    assert cls.hit_die.expression=='1d12'
    assert [r.level for r in cls.progression]==list(range(1,21))
    assert cls.progression[10].feature_names==['Relentless Rage']
    assert len({c.source_id for c in cls.progression[10].cells})==2
    assert cls.progression[-1].cells[3].text=='Unlimited'
    assert len(get('srd51.condition.blinded').effects)==2

@pytest.mark.parametrize('pointer',['/x/-1','/x/01','/x/+1','/x/1.0','/x/99','/bad~2'])
def test_strict_json_pointer(pointer):
    with pytest.raises(EvidenceError):
        json_pointer({'x':['first','second']},pointer)

def test_json_pointer_escaping():
    assert json_pointer({'a/b':{'~':[5]}},'/a~1b/~0/0')==5

def test_merged_grid_unit_fixture():
    grid=table_grid('<table><tr><td rowspan="2">A</td><td>B<br>C</td></tr><tr><td>D</td></tr></table>')
    assert grid[1][0]['origin_row']==0 and grid[1][0]['row']==1
    assert grid[0][1]['text']=='B C'

@pytest.mark.evidence
def test_unknown_page_is_explicit(samples):
    s=samples['srd51.general_rule.ability-modifier'][1][0].model_dump()
    s.update(physical_page=None,page_pointer=None,printed_page=None,printed_page_pointer=None)
    assert SourceReference.model_validate(s).physical_page is None
    s['physical_page']=76
    with pytest.raises(ValidationError):
        SourceReference.model_validate(s)

@pytest.mark.evidence
def test_real_all_sources(samples):
    manifest=json.loads((ROOT/f'data/runs/{RUN}/manifest.json').read_text())
    for ref in {s.id:s for _,sources in samples.values() for s in sources}.values():
        assert verify_reference(ROOT,manifest,ref.model_dump())

@pytest.mark.evidence
@pytest.mark.parametrize('field,value',[
    ('quote_sha256','0'*64),('element_id','wrong'),('physical_page',99),
    ('printed_page','99'),('document_id','0'*64),('run_id','wrong-run'),
    ('section_hierarchy',['invented']),('coordinates',[1.0,2.0]),('fragment_type','invented')])
def test_reference_tampering(samples,field,value):
    ref=samples['srd51.general_rule.ability-modifier'][1][0].model_dump();ref[field]=value
    manifest=json.loads((ROOT/f'data/runs/{RUN}/manifest.json').read_text())
    with pytest.raises(EvidenceError):
        verify_reference(ROOT,manifest,ref)

@pytest.mark.evidence
def test_table_location_tampering(samples):
    ref=samples['srd51.equipment.dagger'][1][0].model_dump();ref['table_location']['text']='fake'
    manifest=json.loads((ROOT/f'data/runs/{RUN}/manifest.json').read_text())
    with pytest.raises(EvidenceError):
        verify_reference(ROOT,manifest,ref)

@pytest.mark.evidence
def test_lifecycle_and_idempotency(catalog):
    service,record,sources=catalog
    assert service.create_candidate(record,sources)==record
    with pytest.raises(EvidenceError):
        service.publish_record(record.id)
    with pytest.raises(EvidenceError):
        service.review_candidate(record.id,'approved','test-reviewer','test-only review')
    service.validate_candidate(record.id)
    with pytest.raises(EvidenceError):
        service.publish_record(record.id)
    reviewed=service.review_candidate(record.id,'approved','test-reviewer','test-only provenance review')
    assert reviewed.execution_status=='reference_only'
    assert service.publish_record(record.id)==reviewed
    assert service.publish_record(record.id)==reviewed
    assert service.get_record(record.id,published_only=True)==reviewed
    assert service.list_records('general_rule',published_only=True)==[reviewed]
    service.create_candidate(record,sources)
    assert service.get_record(record.id).review_status=='approved'
    with connect(service.database) as conn:
        assert conn.execute('SELECT count(*) FROM normalized_records').fetchone()[0]==1
    service.review_candidate(record.id,'rejected','test-reviewer','test-only revocation')
    assert service.list_records(published_only=True)==[]
    with pytest.raises(EvidenceError):
        service.get_record(record.id,published_only=True)

@pytest.mark.evidence
def test_version_conflict(catalog):
    service,record,sources=catalog
    data=record.model_dump();data['canonical_name']='Changed'
    with pytest.raises(EvidenceError,match='version conflict'):
        service.create_candidate(data,sources)
    data['record_version']=2
    assert service.create_candidate(data,sources).record_version==2

@pytest.mark.evidence
def test_missing_source_and_failure_report(tmp_path,samples):
    service=CatalogService(ROOT,tmp_path/'db.sqlite3')
    data=samples['srd51.general_rule.ability-modifier'][0].model_dump()
    data['source_ids']=[];data['field_sources']={};data['normalized_payload']['effect_specification']=[]
    record=service.create_candidate(data,[])
    with pytest.raises(EvidenceError,match='no verifiable sources'):
        service.validate_candidate(record.id)
    with connect(service.database) as conn:
        assert json.loads(conn.execute('SELECT validation_json FROM normalized_records').fetchone()[0])['status']=='failed'
    with pytest.raises(EvidenceError):
        service.publish_record(record.id)

@pytest.mark.evidence
@pytest.mark.parametrize('tamper',['source','relation','payload','validation','review','execution'])
def test_published_catalog_tampering_rejected(catalog,tamper):
    service,record,_=catalog
    service.validate_candidate(record.id)
    service.review_candidate(record.id,'approved','test-reviewer','test-only review')
    service.publish_record(record.id)
    with connect(service.database) as conn:
        if tamper=='source':
            row=conn.execute('SELECT reference_json FROM source_references').fetchone()
            ref=json.loads(row[0]);ref['quote_sha256']='0'*64
            conn.execute('UPDATE source_references SET reference_json=?',(json.dumps(ref),))
        elif tamper=='relation':
            conn.execute('DELETE FROM record_sources')
        elif tamper=='payload':
            row=conn.execute('SELECT record_json FROM normalized_records').fetchone()
            data=json.loads(row[0]);data['normalized_payload']['description']='wrong'
            conn.execute('UPDATE normalized_records SET record_json=?',(json.dumps(data),))
        elif tamper=='validation':
            conn.execute("UPDATE normalized_records SET validation_json='{}'")
        elif tamper=='review':
            conn.execute('DELETE FROM review_decisions')
        else:
            row=conn.execute('SELECT record_json FROM normalized_records').fetchone()
            data=json.loads(row[0]);data['execution_status']='executable'
            conn.execute('UPDATE normalized_records SET record_json=?',(json.dumps(data),))
    with pytest.raises(EvidenceError):
        service.get_record(record.id,published_only=True)

@pytest.mark.evidence
def test_unreviewed_executable_rejected(catalog):
    service,record,sources=catalog
    data=record.model_dump();data['execution_status']='executable'
    with pytest.raises(ValidationError):
        parse_record(data)
    data.update(validation_status='validated',review_status='approved')
    with pytest.raises(EvidenceError):
        service.create_candidate(data,sources)

@pytest.mark.evidence
def test_v1_migration_preserves_every_legacy_table(tmp_path):
    db=tmp_path/'v1.sqlite3'
    schema=ROOT/'backend/ruleforge/persistence/schema.sql'
    with connect(db) as dest, connect(ROOT/'data/ruleforge.sqlite3') as src:
        dest.executescript(schema.read_text())
        tables=[r[0] for r in dest.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        for table in tables:
            for row in src.execute('SELECT * FROM '+table):
                dest.execute('INSERT INTO '+table+' VALUES ('+','.join('?' for _ in row)+')',tuple(row))
        dest.execute("INSERT INTO characters VALUES ('migration-sentinel',7,'{}')")
        before={t:[tuple(r) for r in dest.execute('SELECT * FROM '+t)] for t in tables}
        assert dest.execute('PRAGMA user_version').fetchone()[0]==1
    initialize(db);initialize(db)
    with connect(db) as conn:
        assert conn.execute('PRAGMA user_version').fetchone()[0]==2
        assert conn.execute('PRAGMA foreign_key_check').fetchall()==[]
        assert before=={t:[tuple(r) for r in conn.execute('SELECT * FROM '+t)] for t in tables}

def test_newer_db_rejected(tmp_path):
    db=tmp_path/'future.sqlite3'
    with connect(db) as conn:
        conn.execute('PRAGMA user_version=3')
    with pytest.raises(ValueError,match='newer'):
        initialize(db)

@pytest.mark.evidence
def test_pipeline_real_samples_and_failures(tmp_path):
    root=tmp_path
    shutil.copytree(ROOT/'data/runs'/RUN,root/'data/runs'/RUN)
    shutil.copytree(ROOT/'data/sources',root/'data/sources')
    report=run_pipeline(root)
    assert report['failures']==[] and len(report['records'])==10
    assert {r['record_type'] for r in report['records']}==set(EXTRACTORS)
    second=run_pipeline(root,categories=['general_rule'])
    assert second['status']=='passed'
    service=CatalogService(root)
    assert len(service.list_records())==10 and service.list_records(published_only=True)==[]
    failed=run_pipeline(root,categories=['unknown'])
    assert failed['status']=='failed' and failed['failures'][0]['category']=='unknown'
    assert json.loads((root/'data/normalized/m1plus/extraction-report.json').read_text())==failed
    # M1 can publish after a catalog import has registered this parse run.
    shutil.copytree(ROOT/'data/setup',root/'data/setup')
    from ruleforge.rules.service import publish,calculate_ac
    from ruleforge.domain.models import Abilities,Equipment
    assert publish(root,RUN)['status']=='passed'
    assert calculate_ac(root,Abilities(dexterity=9),Equipment(armor='leather'))['ac']==10

@pytest.mark.evidence
@pytest.mark.parametrize('record_id,missing',[
    ('srd51.equipment.dagger','damage_dice'),('srd51.spell.magic-missile','casting_time'),
    ('srd51.class.barbarian','progression'),('srd51.condition.blinded','effects'),
    ('srd51.general_rule.ability-modifier','description')])
def test_five_payloads_require_fields(samples,record_id,missing):
    data=samples[record_id][0].model_dump()
    del data['normalized_payload'][missing]
    with pytest.raises(ValidationError):
        parse_record(data)

def test_migration_failure_is_atomic(tmp_path,monkeypatch):
    db=tmp_path/'atomic.sqlite3'
    with connect(db) as conn:
        conn.executescript((ROOT/'backend/ruleforge/persistence/schema.sql').read_text())
        conn.execute("INSERT INTO characters VALUES ('sentinel',1,'{}')")
    original=Path.read_text
    def broken(path,*args,**kwargs):
        text=original(path,*args,**kwargs)
        return text+'\nINSERT INTO missing_table VALUES (1);' if path.name=='migration_v2.sql' else text
    monkeypatch.setattr(Path,'read_text',broken)
    with pytest.raises(sqlite3.OperationalError):
        initialize(db)
    with connect(db) as conn:
        assert conn.execute('PRAGMA user_version').fetchone()[0]==1
        assert conn.execute('SELECT id FROM characters').fetchone()[0]=='sentinel'
        assert not conn.execute("SELECT name FROM sqlite_master WHERE name='normalized_records'").fetchall()

@pytest.mark.evidence
def test_failed_revalidation_revokes_publication(catalog):
    service,record,_=catalog
    service.validate_candidate(record.id)
    service.review_candidate(record.id,'approved','test-reviewer','test-only review')
    service.publish_record(record.id)
    with connect(service.database) as conn:
        conn.execute('DELETE FROM record_sources')
    with pytest.raises(EvidenceError):
        service.validate_candidate(record.id)
    current=service.get_record(record.id)
    assert current.validation_status=='review_required' and current.review_status=='review_required'
    assert service.list_records(published_only=True)==[]

@pytest.mark.evidence
def test_legacy_source_count_remains_strict():
    from ruleforge.rules.models import RuleRecord
    from ruleforge.rules.dsl import base_ac_rule
    legacy=json.loads((ROOT/'data/normalized/srd51.ac.leather.json').read_text())
    assert len(RuleRecord(rule=base_ac_rule(),sources=legacy['sources']).sources)==3
    with pytest.raises(ValidationError):
        RuleRecord(rule=base_ac_rule(),sources=legacy['sources'][:2])

@pytest.mark.evidence
def test_report_history_preserves_failure(tmp_path):
    shutil.copytree(ROOT/'data/runs'/RUN,tmp_path/'data/runs'/RUN)
    shutil.copytree(ROOT/'data/sources',tmp_path/'data/sources')
    failed=run_pipeline(tmp_path,categories=['not-registered'])
    passed=run_pipeline(tmp_path,categories=['general_rule'])
    history=tmp_path/'data/normalized/m1plus/reports'
    reports=[json.loads(p.read_text()) for p in history.glob('*.json')]
    assert len(reports)==2
    assert failed in reports and passed in reports
    assert failed['normalization_id'] != passed['normalization_id']
    assert failed['status']=='failed' and passed['status']=='passed'
