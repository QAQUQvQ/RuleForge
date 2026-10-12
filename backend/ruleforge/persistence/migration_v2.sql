CREATE TABLE IF NOT EXISTS source_references (
 id TEXT PRIMARY KEY,
 run_id TEXT NOT NULL REFERENCES parse_runs(id),
 reference_json TEXT NOT NULL CHECK(json_valid(reference_json)),
 manifest_ref_json TEXT NOT NULL CHECK(json_valid(manifest_ref_json))
);
CREATE TABLE IF NOT EXISTS normalized_records (
 id TEXT NOT NULL, record_version INTEGER NOT NULL CHECK(record_version>0),
 ruleset TEXT NOT NULL CHECK(ruleset='srd-5.1'),
 record_type TEXT NOT NULL CHECK(record_type IN ('equipment','spell','class','condition','general_rule')),
 record_json TEXT NOT NULL CHECK(json_valid(record_json)),
 content_sha256 TEXT NOT NULL,
 validation_json TEXT CHECK(validation_json IS NULL OR json_valid(validation_json)),
 published_at TEXT,
 PRIMARY KEY(id,record_version)
);
CREATE INDEX IF NOT EXISTS normalized_record_type ON normalized_records(ruleset,record_type);
CREATE TABLE IF NOT EXISTS record_sources (
 record_id TEXT NOT NULL, record_version INTEGER NOT NULL,
 source_id TEXT NOT NULL REFERENCES source_references(id),
 PRIMARY KEY(record_id,record_version,source_id),
 FOREIGN KEY(record_id,record_version) REFERENCES normalized_records(id,record_version)
);
CREATE TABLE IF NOT EXISTS review_decisions (
 id INTEGER PRIMARY KEY,
 record_id TEXT NOT NULL, record_version INTEGER NOT NULL,
 decision TEXT NOT NULL CHECK(decision IN ('approved','rejected')),
 reviewer TEXT NOT NULL CHECK(length(reviewer)>0), reason TEXT NOT NULL CHECK(length(reason)>0),
 evidence_sha256 TEXT NOT NULL, reviewed_at TEXT NOT NULL,
 FOREIGN KEY(record_id,record_version) REFERENCES normalized_records(id,record_version)
);
PRAGMA user_version = 2;
