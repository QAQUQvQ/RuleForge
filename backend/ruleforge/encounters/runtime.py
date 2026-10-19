import json
from pathlib import Path
from ruleforge.combat.runtime import Runtime, ResolutionScope, adapter_hash
from ruleforge.catalog.service import canonical
from ruleforge.ingestion.evidence import digest_text
from ruleforge.combat.errors import RuleError


class EncounterRuntime(Runtime):
    adapter_id = 'srd51.m3.encounters.v1'

    def template_entries(self):
        return json.loads(Path(__file__).with_name('templates.json').read_text(encoding='utf-8'))

    def adapter_digest(self):
        base = Path(__file__).parent
        files = sorted(base.glob('*.py')) + [base/'templates.json',
            base.parent/'ingestion/evidence.py', base.parent/'m3_api.py',
            base.parent/'persistence/db.py', base.parent/'persistence/migration_v4.sql']
        return digest_text(canonical({'m2': adapter_hash(),
            'm3': {p.relative_to(base.parent).as_posix(): p.read_text(encoding='utf-8') for p in files}}))

    def verification_report(self):
        from ruleforge.encounters.machine import fixed_tests
        return fixed_tests()


class EncounterScope(ResolutionScope):
    """Both runtimes share the same SQLite read/write transaction and evidence cache."""
    def __init__(self, catalog, conn, mode):
        super().__init__(Runtime(catalog), conn)
        self.m3 = EncounterRuntime(catalog)
        self.mode = mode

    def require(self, record_id, version=1):
        if self.mode == 'production':
            # Do not let an environment-selected demo DB enable simulated execution.
            row = self.conn.execute('''SELECT reviewer FROM review_decisions
                WHERE record_id=? AND record_version=? ORDER BY id DESC LIMIT 1''',
                (record_id, version)).fetchone()
            if row and 'SIMULATED' in row[0].upper():
                raise RuleError('simulated_review_forbidden', 'Production rejects simulated review', 409)
        key = (record_id, version)
        if key not in self.records:
            runtime = self.m3 if record_id.startswith('srd51.general_rule.m3-') else self.runtime
            record, ref, sources = runtime.require(self.conn, record_id, version)
            self.records[key], self.refs[key] = record, ref
            self.sources.update({s['id']: s for s in sources})
        return self.records[key]
