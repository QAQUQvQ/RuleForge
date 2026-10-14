"""Independent, fail-closed execution grants bound to published catalog + code + fixed tests."""
import json
from pathlib import Path
from ruleforge.catalog.service import CatalogService, canonical
from ruleforge.ingestion.evidence import digest_text, now, evidence_snapshot, EvidenceError
from ruleforge.persistence.db import connect
from ruleforge.combat.errors import RuleError

ADAPTER_ID = 'srd51.m2.fixed-templates.v1'


def templates():
    return json.loads(Path(__file__).with_name('templates.json').read_text(encoding='utf-8'))


def adapter_hash():
    # Bind implementation, inputs, applicability guards and goldens, not just a version string.
    base = Path(__file__).parent
    files = sorted(base.glob('*.py')) + [base/'templates.json', base.parent/'domain/models.py']
    return digest_text(canonical({p.name: p.read_text(encoding='utf-8') for p in files}))


class Runtime:
    def __init__(self, catalog: CatalogService):
        self.catalog = catalog

    def _binding(self, conn, record_id, version):
        allowed = templates().get(record_id)
        if not allowed or version != allowed['record']['record_version']:
            raise RuleError('missing_adapter', 'No whitelisted template for this record/version', 409)
        try:
            record, row = self.catalog._load(conn, record_id, version)
        except KeyError as exc:
            raise RuleError('rule_unverified', 'Required rule record is missing: '+record_id, 409) from exc
        if not row['published_at']:
            raise RuleError('rule_unpublished', 'Record requires explicit review and publication: '+record_id, 409)
        if record.validation_status != 'validated' or record.review_status != 'approved':
            raise RuleError('rule_unverified', 'Record lacks current validation/approval', 409)
        self.catalog._publication_gate(conn, record, row)
        if row['content_sha256'] != allowed['content_sha256']:
            raise RuleError('missing_adapter', 'Published payload differs from whitelisted template', 409)
        expected_sources = {s['id']: s for s in allowed['sources']}
        actual_sources = {r['id']: json.loads(r['reference_json']) for r in conn.execute('''
            SELECT s.* FROM source_references s JOIN record_sources rs ON s.id=rs.source_id
            WHERE rs.record_id=? AND rs.record_version=?''', (record_id, version))}
        if actual_sources != expected_sources:
            raise EvidenceError('runtime template source binding mismatch')
        return record, self.catalog._evidence(conn, record), list(actual_sources.values())

    def register(self, record_id, version=1):
        from ruleforge.combat.verification import fixed_tests
        with connect(self.catalog.database) as conn, evidence_snapshot():
            conn.execute('BEGIN IMMEDIATE')
            record, fingerprint, _ = self._binding(conn, record_id, version)
            report = fixed_tests()
            report.update(method='fixed trusted adapter tests; catalog review is separate', human_review=False)
            conn.execute('''INSERT INTO runtime_grants VALUES (?,?,?,?,?,?,?)
                ON CONFLICT(record_id,record_version) DO UPDATE SET adapter_id=excluded.adapter_id,
                adapter_sha256=excluded.adapter_sha256,evidence_sha256=excluded.evidence_sha256,
                verification_json=excluded.verification_json,granted_at=excluded.granted_at''',
                (record.id, version, ADAPTER_ID, adapter_hash(), fingerprint, canonical(report), now()))
        return report

    def require(self, conn, record_id, version=1):
        record, fingerprint, sources = self._binding(conn, record_id, version)
        grant = conn.execute('SELECT * FROM runtime_grants WHERE record_id=? AND record_version=?',
                             (record_id, version)).fetchone()
        from ruleforge.combat.verification import fixed_tests
        expected = fixed_tests()
        report = json.loads(grant['verification_json']) if grant else {}
        if (not grant or grant['adapter_id'] != ADAPTER_ID or grant['adapter_sha256'] != adapter_hash()
            or grant['evidence_sha256'] != fingerprint or any(report.get(k) != v for k,v in expected.items())):
            raise RuleError('missing_adapter', 'No current independently verified execution grant: '+record_id, 409)
        return record, {'id': record_id, 'version': version, 'adapter_id': ADAPTER_ID,
                        'adapter_sha256': grant['adapter_sha256'], 'evidence_sha256': fingerprint}, sources


class ResolutionScope:
    """Lives inside the caller's SQLite transaction; never reused across calculations."""
    def __init__(self, runtime, conn):
        self.runtime, self.conn = runtime, conn
        self.records, self.refs, self.sources = {}, {}, {}

    def require(self, record_id, version=1):
        key = (record_id, version)
        if key not in self.records:
            record, ref, sources = self.runtime.require(self.conn, record_id, version)
            self.records[key], self.refs[key] = record, ref
            self.sources.update({s['id']: s for s in sources})
        return self.records[key]

    def evidence(self):
        return {'rule_refs': list(self.refs.values()), 'source_refs': list(self.sources.values())}
