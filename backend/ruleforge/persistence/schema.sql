PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS documents (
 id TEXT PRIMARY KEY, ruleset TEXT NOT NULL CHECK(ruleset='srd-5.1'),
 source_url TEXT NOT NULL, sha256 TEXT NOT NULL UNIQUE, local_path TEXT NOT NULL,
 license TEXT NOT NULL, downloaded_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS parse_runs (
 id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id),
 parser_version TEXT NOT NULL, api_mode TEXT NOT NULL CHECK(api_mode='free'),
 status TEXT NOT NULL CHECK(status IN ('running','succeeded','failed')),
 artifact_manifest TEXT NOT NULL CHECK(json_valid(artifact_manifest)),
 error TEXT, started_at TEXT NOT NULL, finished_at TEXT
);
CREATE TABLE IF NOT EXISTS source_spans (
 id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES parse_runs(id),
 json_pointer TEXT NOT NULL, physical_page INTEGER CHECK(physical_page>0),
 printed_page TEXT, section TEXT, quote TEXT NOT NULL, quote_sha256 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS rules (
 id TEXT NOT NULL, version INTEGER NOT NULL CHECK(version>0), ruleset TEXT NOT NULL,
 category TEXT NOT NULL, dsl_json TEXT NOT NULL CHECK(json_valid(dsl_json)),
 review_status TEXT NOT NULL CHECK(review_status IN ('draft','verified','rejected')),
 PRIMARY KEY(id,version)
);
CREATE TABLE IF NOT EXISTS rule_sources (
 rule_id TEXT NOT NULL, rule_version INTEGER NOT NULL, source_id TEXT NOT NULL REFERENCES source_spans(id),
 PRIMARY KEY(rule_id,rule_version,source_id),
 FOREIGN KEY(rule_id,rule_version) REFERENCES rules(id,version)
);
CREATE TABLE IF NOT EXISTS verifications (
 id TEXT PRIMARY KEY, rule_id TEXT NOT NULL, rule_version INTEGER NOT NULL,
 dsl_sha256 TEXT NOT NULL, report_json TEXT NOT NULL CHECK(json_valid(report_json)), verified_at TEXT NOT NULL,
 FOREIGN KEY(rule_id,rule_version) REFERENCES rules(id,version)
);
CREATE TABLE IF NOT EXISTS characters (
 id TEXT PRIMARY KEY, version INTEGER NOT NULL CHECK(version>=0), state_json TEXT NOT NULL CHECK(json_valid(state_json))
);
CREATE TABLE IF NOT EXISTS encounters (
 id TEXT PRIMARY KEY, version INTEGER NOT NULL CHECK(version>=0), state_json TEXT NOT NULL CHECK(json_valid(state_json))
);
CREATE TABLE IF NOT EXISTS commands (
 id TEXT PRIMARY KEY, encounter_id TEXT NOT NULL REFERENCES encounters(id),
 expected_version INTEGER NOT NULL CHECK(expected_version>=0), payload_json TEXT NOT NULL CHECK(json_valid(payload_json)),
 created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
 id TEXT PRIMARY KEY, command_id TEXT NOT NULL REFERENCES commands(id),
 encounter_id TEXT NOT NULL REFERENCES encounters(id), sequence INTEGER NOT NULL CHECK(sequence>0),
 before_hash TEXT NOT NULL, after_hash TEXT NOT NULL,
 payload_json TEXT NOT NULL CHECK(json_valid(payload_json)), UNIQUE(encounter_id,sequence)
);
PRAGMA user_version = 1;
