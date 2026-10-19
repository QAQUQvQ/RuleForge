ALTER TABLE encounters ADD COLUMN initial_json TEXT CHECK(initial_json IS NULL OR json_valid(initial_json));
ALTER TABLE encounters ADD COLUMN initial_hash TEXT;
ALTER TABLE encounters ADD COLUMN state_hash TEXT;
ALTER TABLE encounters ADD COLUMN event_head TEXT;
ALTER TABLE commands ADD COLUMN request_hash TEXT;
ALTER TABLE commands ADD COLUMN result_json TEXT CHECK(result_json IS NULL OR json_valid(result_json));
ALTER TABLE events ADD COLUMN event_hash TEXT;
CREATE INDEX commands_encounter ON commands(encounter_id);
CREATE TABLE encounter_environment (
 id INTEGER PRIMARY KEY CHECK(id=1), mode TEXT NOT NULL CHECK(mode IN ('production','isolated_demo'))
);
INSERT INTO encounter_environment VALUES (1,'production');
PRAGMA user_version = 4;
