import json
from pathlib import Path
import pytest
from ruleforge.ingestion.evidence import structured_error, contained, EvidenceError, json_pointer
from ruleforge.ingestion.xparse import finalize, command
from ruleforge.persistence.db import initialize, connect

def test_structured_failure_overrides_zero_exit(tmp_path):
    # Deliberately synthetic ERROR only; never creates a successful parse fixture.
    root = tmp_path
    (root / "data/sources").mkdir(parents=True)
    (root / "data/sources/SRD_CC_v5.1.pdf").write_bytes(b"test-error-input-not-official-pdf")
    run = root / "data/runs/failure-only"
    (run / "raw").mkdir(parents=True)
    (run / "stdout.log").write_text("", encoding="utf-8")
    error = {"schema_version":"xparse_error.v1","error_code":"QUOTA_EXCEEDED","retryable":False,"next_action":"WAIT"}
    (run / "stderr.log").write_text("progress\n"+json.dumps(error,indent=2),encoding="utf-8")
    result = finalize(root, "failure-only", 0, "unit-test")
    assert result["status"] == "failed"
    assert result["error"] == error
    assert "raw" not in result

def test_last_error_envelope():
    text = '{"schema_version":"xparse_error.v1","retryable":true}\n{"schema_version":"xparse_error.v1","retryable":false}'
    assert structured_error(text)["retryable"] is False

def test_path_escape(tmp_path):
    with pytest.raises(EvidenceError):
        contained(tmp_path, "../outside.json")

def test_invalid_pointer():
    with pytest.raises(EvidenceError):
        json_pointer({"data":[]}, "/data/55/text")

def test_free_only_command(tmp_path):
    executable = tmp_path / "xparse-cli"
    executable.touch()
    args = command(executable,tmp_path,tmp_path/"raw")
    assert args[args.index("--api")+1] == "free"
    assert "--secret-code" not in args and "--verbose" not in args

def test_sql_foreign_keys_and_transaction_rollback(tmp_path):
    import sqlite3
    db = tmp_path/"db.sqlite3"
    initialize(db)
    with pytest.raises(sqlite3.IntegrityError):
        with connect(db) as conn:
            conn.execute("INSERT INTO characters VALUES ('c',0,'{}')")
            conn.execute("INSERT INTO source_spans VALUES ('bad','missing','/x',1,NULL,NULL,'x','hash')")
    with connect(db) as conn:
        assert conn.execute("SELECT count(*) FROM characters").fetchone()[0] == 0

def test_zero_exit_with_api_failure_is_not_success(tmp_path):
    (tmp_path/"data/sources").mkdir(parents=True)
    (tmp_path/"data/sources/SRD_CC_v5.1.pdf").write_bytes(b"failure-test-only")
    run = tmp_path/"data/runs/api-error"
    (run/"raw").mkdir(parents=True)
    (run/"raw/error.json").write_text('{"code":500,"message":"synthetic error only"}',encoding="utf-8")
    (run/"stdout.log").write_text("",encoding="utf-8")
    (run/"stderr.log").write_text("",encoding="utf-8")
    result = finalize(tmp_path,"api-error",0,"unit-test")
    assert result["status"] == "failed"
    assert result["error"]["type"] == "RESPONSE_VALIDATION_FAILED"
    assert any(ref["path"].endswith("error.json") for ref in result["artifacts"])

def test_missing_raw_is_not_success(tmp_path):
    (tmp_path/"data/sources").mkdir(parents=True)
    (tmp_path/"data/sources/SRD_CC_v5.1.pdf").write_bytes(b"failure-test-only")
    run = tmp_path/"data/runs/missing"
    (run/"raw").mkdir(parents=True)
    (run/"stdout.log").write_text("",encoding="utf-8")
    (run/"stderr.log").write_text("",encoding="utf-8")
    assert finalize(tmp_path,"missing",0,"unit-test")["status"] == "failed"

