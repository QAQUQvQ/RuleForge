"""Explicit isolated setup; never selected by RULEFORGE_DATABASE or a mode env var."""
from pathlib import Path
from ruleforge.encounters.evidence import import_candidates as import_m3
from ruleforge.encounters.runtime import EncounterRuntime
from ruleforge.combat.runtime import Runtime, templates
from ruleforge.ingestion.m2 import import_candidates as import_m2
from ruleforge.ingestion.evidence import evidence_snapshot
from ruleforge.persistence.db import connect


def prepare_isolated_demo(root, database):
    root, database = Path(root).resolve(), Path(database).resolve()
    primary = root/'data/ruleforge.sqlite3'
    if database == primary or not database.name.startswith('m3-demo') or database.exists():
        raise ValueError('Requires a new separate m3-demo*.sqlite3 database; never overwrite an existing database')
    with evidence_snapshot(cache_files=True):
        import_m2(root, database)
        catalog = import_m3(root, database)
        with connect(database) as conn:
            conn.execute("UPDATE encounter_environment SET mode='isolated_demo' WHERE id=1")
        for runtime, records in [(Runtime(catalog), templates()), (EncounterRuntime(catalog), EncounterRuntime(catalog).template_entries())]:
            for record_id in records:
                catalog.review_candidate(record_id, 'approved', 'SIMULATED-TEST-REVIEW',
                    'Isolated M3 fixture only; not human semantic review or production permission.')
                catalog.publish_record(record_id)
                runtime.register(record_id)
    return catalog


def create_demo_app(root, database):
    from ruleforge.api import create_app
    return create_app(Path(root), Path(database), isolated_demo=True)
