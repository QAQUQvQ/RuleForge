import json
from pathlib import Path
from ruleforge.domain.models import Abilities, Equipment
from ruleforge.ingestion.evidence import EvidenceError, now, digest_text, verify_span, SOURCE_URL, checked_file
from ruleforge.ingestion.normalize import normalize
from ruleforge.persistence.db import initialize, connect
from ruleforge.rules.dsl import RuleDSL, base_ac_rule, canonical, evaluate

def publish(root: Path, run_id: str) -> dict:
    database = root / "data/ruleforge.sqlite3"
    initialize(database)
    with connect(database) as conn:
        existing = conn.execute("SELECT report_json FROM verifications WHERE rule_id=? AND rule_version=1", ("srd51.ac.leather",)).fetchone()
        if existing:
            _, sources = load_verified(root)
            if any(s["run_id"] != run_id for s in sources):
                raise EvidenceError("Rule version already published from a different run")
            return json.loads(existing["report_json"])
    manifest_path = root / "data/runs" / run_id / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    normalized = normalize(root, manifest)
    rule = base_ac_rule()
    # Fixed goldens, including negative odd scores; not produced by the evaluator.
    goldens = {1:6, 9:10, 10:11, 15:13, 20:16, 30:21}
    cases = []
    for dex, expected in goldens.items():
        actual = evaluate(rule, Abilities(dexterity=dex), Equipment(armor="leather"))["ac"]
        if actual != expected:
            raise EvidenceError("rule verification failed")
        cases.append({"dexterity": dex, "expected_ac": expected, "actual_ac": actual})
    manifest["coverage"] = normalized["coverage"]
    manifest["page_count"] = normalized["page_count"]
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    report = {"status": "passed", "method": "reviewed exact source patterns + deterministic golden cases",
              "human_review": False, "cases": cases, "source_ids": [s["id"] for s in normalized["spans"]],
              "dsl_sha256": digest_text(canonical(rule)), "verified_at": now()}
    from ruleforge.ingestion.evidence import artifact
    report["manifest"] = artifact(root, manifest_path)
    target = root / "data/normalized"
    target.mkdir(parents=True, exist_ok=True)
    (target / "srd51.ac.leather.json").write_text(json.dumps({
        "rule": rule.model_dump(), "sources": normalized["spans"], "verification": report
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    database = root / "data/ruleforge.sqlite3"
    initialize(database)
    with connect(database) as conn:
        # Exact duplicate is idempotent; a changed source requires a new reviewed rule version.
        existing = conn.execute("SELECT * FROM rules WHERE id=? AND version=?", (rule.id, rule.version)).fetchone()
        if existing:
            load_verified(root)
            return report
        doc = manifest["document"]
        conn.execute("INSERT OR IGNORE INTO documents VALUES (?,?,?,?,?,?,?)",
            (doc["sha256"], "srd-5.1", SOURCE_URL, doc["sha256"], doc["path"], "CC-BY-4.0", manifest["started_at"]))
        conn.execute("INSERT INTO parse_runs VALUES (?,?,?,?,?,?,?,?,?)",
            (run_id, doc["sha256"], manifest["parser_version"], "free", "succeeded",
             json.dumps(manifest), None, manifest["started_at"], manifest["finished_at"]))
        for s in normalized["spans"]:
            conn.execute("INSERT INTO source_spans VALUES (?,?,?,?,?,?,?,?)",
                (s["id"],run_id,s["json_pointer"],s["physical_page"],s["printed_page"],s["section"],s["quote"],s["quote_sha256"]))
        conn.execute("INSERT INTO rules VALUES (?,?,?,?,?,?)",
            (rule.id,rule.version,rule.ruleset,rule.category,canonical(rule),"verified"))
        conn.executemany("INSERT INTO rule_sources VALUES (?,?,?)",
            [(rule.id,rule.version,s["id"]) for s in normalized["spans"]])
        conn.execute("INSERT INTO verifications VALUES (?,?,?,?,?,?)",
            (rule.id+":v1",rule.id,rule.version,report["dsl_sha256"],json.dumps(report),report["verified_at"]))
    return report

def load_verified(root: Path):
    db = root / "data/ruleforge.sqlite3"
    if not db.exists():
        raise EvidenceError("No verified rule database; real xParse ingestion required")
    with connect(db) as conn:
        row = conn.execute("SELECT * FROM rules WHERE id='srd51.ac.leather' AND version=1").fetchone()
        if not row or row["review_status"] != "verified":
            raise EvidenceError("AC rule is not verified")
        rule = RuleDSL.model_validate_json(row["dsl_json"])
        if canonical(rule) != canonical(base_ac_rule()):
            raise EvidenceError("rule differs from reviewed implementation")
        verification = conn.execute("SELECT * FROM verifications WHERE rule_id=? AND rule_version=?",(rule.id,rule.version)).fetchone()
        if not verification or verification["dsl_sha256"] != digest_text(canonical(rule)):
            raise EvidenceError("verification does not match DSL")
        report = json.loads(verification["report_json"])
        if report.get("status") != "passed":
            raise EvidenceError("verification did not pass")
        manifest_path = checked_file(root, report["manifest"])
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        sources = [dict(s) for s in conn.execute(
            "SELECT s.* FROM source_spans s JOIN rule_sources rs ON s.id=rs.source_id WHERE rs.rule_id=? AND rs.rule_version=?",
            (rule.id,rule.version))]
        normalized = normalize(root, manifest)
        expected = {s["id"]:s for s in normalized["spans"]}
        if set(expected) != {s["id"] for s in sources} or set(report["source_ids"]) != set(expected):
            raise EvidenceError("required sources missing")
        for source in sources:
            evidence = expected[source["id"]]
            for key in ("run_id","json_pointer","physical_page","printed_page","section","quote","quote_sha256"):
                if source[key] != evidence[key]:
                    raise EvidenceError("database source differs from raw evidence")
            verify_span(root,manifest,evidence)
            source["source_url"] = SOURCE_URL
            source["document_sha256"] = manifest["document"]["sha256"]
        return rule, sources

def calculate_ac(root: Path, abilities: Abilities, equipment: Equipment):
    rule, sources = load_verified(root)
    result = evaluate(rule, abilities, equipment)
    result["sources"] = sources
    return result
