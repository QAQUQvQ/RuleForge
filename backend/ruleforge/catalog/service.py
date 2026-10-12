"""Versioned reference catalog. Approval never grants runtime capability."""
import json
from pathlib import Path
from ruleforge.catalog.models import parse_record
from ruleforge.rules.sources import SourceReference
from ruleforge.ingestion.evidence import (EvidenceError, artifact, checked_file, contained,
    digest_text, now, verify_reference, SOURCE_URL)
from ruleforge.persistence.db import connect, initialize


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'))


def content(record):
    data = record.model_dump()
    for key in ('validation_status', 'review_status'):
        data.pop(key)
    if data['record_type'] == 'equipment':
        data['normalized_payload'].pop('review_status')
    return data


def transition(record, **updates):
    data = record.model_dump()
    data.update(updates)
    if record.record_type == 'equipment':
        data['normalized_payload']['review_status'] = data['review_status']
    return parse_record(data)


class CatalogService:
    def __init__(self, root: Path, database: Path | None = None):
        self.root = Path(root)
        self.database = database or self.root / 'data/ruleforge.sqlite3'
        initialize(self.database)

    def _load(self, conn, record_id, version):
        row = conn.execute('SELECT * FROM normalized_records WHERE id=? AND record_version=?',
                           (record_id, version)).fetchone()
        if row is None:
            raise KeyError((record_id, version))
        record = parse_record(row['record_json'])
        if (record.id != record_id or record.record_version != version
            or row['ruleset'] != record.ruleset or row['record_type'] != record.record_type
            or digest_text(canonical(content(record))) != row['content_sha256']):
            raise EvidenceError('record content integrity failure')
        return record, row

    def _evidence(self, conn, record):
        if not record.source_ids:
            raise EvidenceError('record has no verifiable sources')
        rows = conn.execute('''SELECT s.* FROM source_references s JOIN record_sources rs
            ON s.id=rs.source_id WHERE rs.record_id=? AND rs.record_version=? ORDER BY s.id''',
            (record.id, record.record_version)).fetchall()
        if {s['id'] for s in rows} != set(record.source_ids):
            raise EvidenceError('required sources missing')
        evidence = []
        sources = {}
        for row in rows:
            ref = SourceReference.model_validate_json(row['reference_json'])
            if ref.id != row['id'] or ref.run_id != row['run_id'] or ref.run_id != record.extraction_run_id:
                raise EvidenceError('source/run identity mismatch')
            if ref.review_status == 'rejected':
                raise EvidenceError('rejected source')
            manifest_ref = json.loads(row['manifest_ref_json'])
            manifest = json.loads(checked_file(self.root, manifest_ref).read_text(encoding='utf-8'))
            verify_reference(self.root, manifest, ref.model_dump())
            sources[ref.id] = ref
            evidence.append({'reference': ref.model_dump(), 'manifest': manifest_ref})
        if record.record_type == 'class':
            from ruleforge.ingestion.tables import table_grid
            for progress in record.normalized_payload.progression:
                for cell in progress.cells:
                    grid = table_grid(sources[cell.source_id].quote)
                    matches = [c for row in grid for c in row if c['row']==cell.row and c['column']==cell.column]
                    actual = cell.model_dump(exclude={'source_id'})
                    if matches != [actual]:
                        raise EvidenceError('class cell differs from source grid')
        # Hash covers payload, the complete required-source set and pinned manifest hashes.
        return digest_text(canonical({'record': content(record), 'evidence': evidence}))

    def create_candidate(self, record, sources):
        record = parse_record(record.model_dump() if hasattr(record, 'model_dump') else record)
        if (record.review_status != 'review_required' or record.validation_status != 'extracted'
            or record.execution_status not in ('reference_only', 'unsupported')):
            raise EvidenceError('new candidates must be unreviewed and non-executable')
        sources = [SourceReference.model_validate(s.model_dump() if hasattr(s, 'model_dump') else s) for s in sources]
        if len({s.id for s in sources}) != len(sources) or {s.id for s in sources} != set(record.source_ids):
            raise EvidenceError('candidate source set mismatch')
        digest = digest_text(canonical(content(record)))
        with connect(self.database) as conn:
            conn.execute('BEGIN IMMEDIATE')
            existing = conn.execute('SELECT 1 FROM normalized_records WHERE id=? AND record_version=?',
                                    (record.id, record.record_version)).fetchone()
            if existing:
                saved, row = self._load(conn, record.id, record.record_version)
                if row['content_sha256'] != digest:
                    raise EvidenceError('record version conflict; create a new version')
                stored = {r['id']: json.loads(r['reference_json']) for r in conn.execute(
                    '''SELECT s.* FROM source_references s JOIN record_sources rs ON s.id=rs.source_id
                    WHERE rs.record_id=? AND rs.record_version=?''', (record.id, record.record_version))}
                if stored != {s.id: s.model_dump() for s in sources}:
                    raise EvidenceError('source version conflict')
                if saved.source_ids:
                    self._evidence(conn, saved)
                return saved
            for source in sources:
                if source.run_id != record.extraction_run_id or source.ruleset != record.ruleset:
                    raise EvidenceError('candidate source ruleset/run mismatch')
                manifest_path = contained(self.root, f'data/runs/{source.run_id}/manifest.json')
                manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
                manifest_ref = artifact(self.root, manifest_path)
                verify_reference(self.root, manifest, source.model_dump())
                doc = manifest['document']
                conn.execute('INSERT OR IGNORE INTO documents VALUES (?,?,?,?,?,?,?)',
                    (doc['sha256'], record.ruleset, SOURCE_URL, doc['sha256'], doc['path'], 'CC-BY-4.0', manifest['started_at']))
                conn.execute('INSERT OR IGNORE INTO parse_runs VALUES (?,?,?,?,?,?,?,?,?)',
                    (source.run_id,doc['sha256'],manifest['parser_version'],manifest['api_mode'],manifest['status'],
                     canonical(manifest),None,manifest['started_at'],manifest['finished_at']))
                run = conn.execute('SELECT document_id FROM parse_runs WHERE id=?',(source.run_id,)).fetchone()
                if run['document_id'] != source.document_id:
                    raise EvidenceError('parse run document conflict')
                previous = conn.execute('SELECT * FROM source_references WHERE id=?',(source.id,)).fetchone()
                values = (source.id,source.run_id,canonical(source.model_dump()),canonical(manifest_ref))
                if previous and tuple(previous) != values:
                    raise EvidenceError('source id collision')
                conn.execute('INSERT OR IGNORE INTO source_references VALUES (?,?,?,?)',values)
            conn.execute('INSERT INTO normalized_records VALUES (?,?,?,?,?,?,NULL,NULL)',
                (record.id,record.record_version,record.ruleset,record.record_type,record.model_dump_json(),digest))
            conn.executemany('INSERT INTO record_sources VALUES (?,?,?)',
                [(record.id,record.record_version,s.id) for s in sources])
        return record

    def validate_candidate(self, record_id, version=1):
        failure = None
        with connect(self.database) as conn:
            conn.execute('BEGIN IMMEDIATE')
            record, row = self._load(conn, record_id, version)
            try:
                fingerprint = self._evidence(conn, record)
                report = {'status':'passed','evidence_sha256':fingerprint,'validated_at':now(),
                          'scope':'schema + provenance; semantic review still required'}
            except (ValueError, OSError, KeyError) as exc:
                failure = str(exc)
                report = {'status':'failed','error':failure,'validated_at':now()}
            if failure:
                updated = transition(record,validation_status='review_required',review_status='review_required')
            else:
                updated = transition(record,validation_status='validated')
            conn.execute('UPDATE normalized_records SET record_json=?,validation_json=?,published_at=? WHERE id=? AND record_version=?',
                (updated.model_dump_json(),canonical(report),None if failure else row['published_at'],record_id,version))
        if failure:
            raise EvidenceError(failure)
        return report

    def review_candidate(self, record_id, decision, reviewer, reason, version=1):
        if decision not in ('approved','rejected') or not reviewer.strip() or not reason.strip():
            raise ValueError('explicit reviewer, reason and approved/rejected decision required')
        with connect(self.database) as conn:
            conn.execute('BEGIN IMMEDIATE')
            record, row = self._load(conn,record_id,version)
            report = json.loads(row['validation_json'] or '{}')
            fingerprint = self._evidence(conn,record) if decision == 'approved' else row['content_sha256']
            if decision == 'approved' and (record.validation_status != 'validated' or report.get('status') != 'passed'
                                          or report.get('evidence_sha256') != fingerprint):
                raise EvidenceError('approval requires current successful validation')
            updated = transition(record,review_status=decision)
            conn.execute('INSERT INTO review_decisions VALUES (NULL,?,?,?,?,?,?,?)',
                (record_id,version,decision,reviewer,reason,fingerprint,now()))
            conn.execute('UPDATE normalized_records SET record_json=?,published_at=NULL WHERE id=? AND record_version=?',
                (updated.model_dump_json(),record_id,version))
        return updated

    def _publication_gate(self, conn, record, row):
        # Catalog has no runtime compiler. The existing leather service is the only executor.
        if record.execution_status not in ('reference_only','unsupported'):
            raise EvidenceError('no registered and verified runtime adapter')
        if record.validation_status != 'validated' or record.review_status != 'approved':
            raise EvidenceError('publication requires validated, approved record')
        fingerprint = self._evidence(conn,record)
        report = json.loads(row['validation_json'] or '{}')
        review = conn.execute('SELECT * FROM review_decisions WHERE record_id=? AND record_version=? ORDER BY id DESC LIMIT 1',
                              (record.id,record.record_version)).fetchone()
        if (report.get('status') != 'passed' or report.get('evidence_sha256') != fingerprint or not review
            or review['decision'] != 'approved' or review['evidence_sha256'] != fingerprint):
            raise EvidenceError('validation/review not bound to current evidence')

    def publish_record(self, record_id, version=1):
        with connect(self.database) as conn:
            conn.execute('BEGIN IMMEDIATE')
            record,row = self._load(conn,record_id,version)
            self._publication_gate(conn,record,row)
            conn.execute('UPDATE normalized_records SET published_at=COALESCE(published_at,?) WHERE id=? AND record_version=?',
                         (now(),record_id,version))
        return record

    def get_record(self, record_id, version=1, *, published_only=False):
        with connect(self.database) as conn:
            record,row = self._load(conn,record_id,version)
            if published_only:
                if not row['published_at']:
                    raise EvidenceError('record is not published')
                self._publication_gate(conn,record,row)
            return record

    def list_records(self, record_type=None, *, published_only=False):
        with connect(self.database) as conn:
            rows = conn.execute('''SELECT id,record_version FROM normalized_records
                WHERE (? IS NULL OR record_type=?) AND (?=0 OR published_at IS NOT NULL) ORDER BY id,record_version''',
                (record_type,record_type,int(published_only))).fetchall()
        return [self.get_record(r['id'],r['record_version'],published_only=published_only) for r in rows]
