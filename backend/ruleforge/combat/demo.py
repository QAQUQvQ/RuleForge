"""Explicit simulated review only for a separate demonstration/test database."""
from pathlib import Path
from ruleforge.catalog.service import CatalogService
from ruleforge.combat.runtime import Runtime, templates
from ruleforge.combat.characters import Characters, CreateCharacter
from ruleforge.combat.service import PreviewRequest, preview
from ruleforge.ingestion.m2 import import_candidates
from ruleforge.ingestion.evidence import evidence_snapshot


def prepare_isolated_demo(root, database):
    root,database=Path(root).resolve(),Path(database).resolve()
    if database == root/'data/ruleforge.sqlite3' or not database.name.startswith('m2-demo'):
        raise ValueError('Simulated approvals require a separate m2-demo*.sqlite3 database')
    with evidence_snapshot():
        import_candidates(root,database)
        catalog=CatalogService(root,database)
        runtime=Runtime(catalog)
        for record_id in templates():
            catalog.review_candidate(record_id,'approved','SIMULATED-TEST-REVIEW',
                'Isolated M2 fixture only. Not human semantic review and not a production publication.')
            catalog.publish_record(record_id)
            runtime.register(record_id)
    return catalog


def run_demo(catalog):
    characters=Characters(catalog)
    create=CreateCharacter(name='M2 isolated Fighter',abilities={'strength':16,'dexterity':14,'constitution':14,
        'intelligence':10,'wisdom':12,'charisma':8},skills=['Athletics','Perception'],speed_ft=30,origin_confirmed=True)
    card=characters.create(create)
    char=card['character']
    request=PreviewRequest(attacker_id=char['id'],expected_version=char['version'],weapon_id='srd51.equipment.longsword',
        target_id='isolated-training-target',target_ac=14,target_hp={'maximum':20,'current':20,'temporary':2},
        target_defenses={'resistance':['slashing']},target_scope='isolated_dm_input',fixed_dice=[15,6],
        context={'mode':'melee','distance_ft':5,'scene_confirmed':True,'target_visible':True,'cover':'none','hostile_within_5ft':False})
    first=preview(characters,request).model_dump()
    second=preview(characters,request).model_dump()
    if first!=second:
        raise AssertionError('fixed stream preview differs')
    return {'environment':'isolated demo; simulated review only','creation_input':create.model_dump(),
            'character':card,'preview_input':request.model_dump(),'result':first,'repeated_identical':True}
