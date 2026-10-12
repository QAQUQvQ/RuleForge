import json
import shutil
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from ruleforge.api import create_app
from ruleforge.domain.models import Abilities, Equipment
from ruleforge.ingestion.evidence import EvidenceError
from ruleforge.persistence.db import connect
from ruleforge.rules.service import calculate_ac, load_verified, publish

ROOT = Path(__file__).resolve().parents[2]

@pytest.fixture(scope="module")
def real_root():
    if not (ROOT / "data/ruleforge.sqlite3").is_file():
        pytest.skip("REAL xParse evidence missing: M1 acceptance NOT satisfied")
    return ROOT

@pytest.fixture
def copied_evidence(real_root,tmp_path):
    shutil.copytree(real_root/"data",tmp_path/"data")
    return tmp_path

@pytest.mark.evidence
def test_real_document_and_source_chain(real_root):
    rule, sources = load_verified(real_root)
    assert rule.id == "srd51.ac.leather"
    assert {s["physical_page"] for s in sources} == {63,64,76}
    result = calculate_ac(real_root,Abilities(dexterity=14),Equipment(armor="leather"))
    assert result["ac"] == 13
    assert len(result["sources"]) == 3

@pytest.mark.evidence
def test_real_api(real_root):
    client = TestClient(create_app(real_root))
    assert client.get("/api/health").json()["ac_ready"] is True
    result = client.post("/api/evaluate/ac",json={"abilities":{"dexterity":9},"equipment":{"armor":"leather"}})
    assert result.status_code == 200
    assert result.json()["ac"] == 10
    assert client.get("/api/sources").status_code == 200
    bad = client.post("/api/evaluate/ac",json={"abilities":{"dexterity":14},"equipment":{"armor":"leather","shield":True}})
    assert bad.status_code == 422
    bad = client.post("/api/evaluate/ac",json={"abilities":{"dexterity":"14"},"equipment":{"armor":"leather"}})
    assert bad.status_code == 422

def test_empty_database_fails_closed(tmp_path):
    client = TestClient(create_app(tmp_path))
    assert client.get("/api/health").json()["ac_ready"] is False
    assert client.post("/api/evaluate/ac",json={"abilities":{"dexterity":14},"equipment":{"armor":"leather"}}).status_code == 503

@pytest.mark.evidence
@pytest.mark.parametrize("target",["pdf","raw","manifest","source","dsl","review"])
def test_tampered_evidence_rejected(copied_evidence,target):
    root = copied_evidence
    if target in ("pdf","raw","manifest"):
        path = {"pdf":"data/sources/SRD_CC_v5.1.pdf",
                "raw":"data/runs/srd51-full-001/raw/SRD_CC_v5.1.json",
                "manifest":"data/runs/srd51-full-001/manifest.json"}[target]
        with (root/path).open("ab") as f:
            f.write(b" ")
    else:
        with connect(root/"data/ruleforge.sqlite3") as conn:
            if target == "source":
                conn.execute("UPDATE source_spans SET physical_page=99")
            elif target == "dsl":
                row = conn.execute("SELECT dsl_json FROM rules").fetchone()
                dsl = json.loads(row[0])
                dsl["expression"]["args"][0]["value"] = 99
                conn.execute("UPDATE rules SET dsl_json=?",(json.dumps(dsl),))
            else:
                conn.execute("UPDATE rules SET review_status='draft'")
    with pytest.raises(EvidenceError):
        calculate_ac(root,Abilities(dexterity=14),Equipment(armor="leather"))
    client = TestClient(create_app(root))
    assert client.get("/api/health").json()["ac_ready"] is False

@pytest.mark.evidence
def test_publish_idempotent(copied_evidence):
    publish(copied_evidence,"srd51-full-001")
    with connect(copied_evidence/"data/ruleforge.sqlite3") as conn:
        assert conn.execute("SELECT count(*) FROM rules").fetchone()[0] == 1
