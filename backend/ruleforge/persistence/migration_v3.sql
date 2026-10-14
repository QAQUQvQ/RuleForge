CREATE TABLE runtime_grants (
 record_id TEXT NOT NULL, record_version INTEGER NOT NULL,
 adapter_id TEXT NOT NULL, adapter_sha256 TEXT NOT NULL,
 evidence_sha256 TEXT NOT NULL, verification_json TEXT NOT NULL CHECK(json_valid(verification_json)),
 granted_at TEXT NOT NULL,
 PRIMARY KEY(record_id,record_version),
 FOREIGN KEY(record_id,record_version) REFERENCES normalized_records(id,record_version)
);
CREATE TABLE character_equipment (
 character_id TEXT NOT NULL REFERENCES characters(id),
 ordinal INTEGER NOT NULL CHECK(ordinal>=0),
 record_id TEXT NOT NULL, record_version INTEGER NOT NULL,
 instance_json TEXT NOT NULL CHECK(json_valid(instance_json)),
 PRIMARY KEY(character_id,ordinal),
 FOREIGN KEY(record_id,record_version) REFERENCES normalized_records(id,record_version)
);
PRAGMA user_version = 3;
