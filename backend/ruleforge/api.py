from pathlib import Path
import os
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from ruleforge.domain.models import StrictModel, Abilities, Equipment
from ruleforge.ingestion.evidence import EvidenceError, PDF_PATH
from ruleforge.persistence.db import initialize, connect

class ACRequest(StrictModel):
    abilities: Abilities
    equipment: Equipment

def create_app(root: Path | None = None):
    root = (root or Path(os.environ.get("RULEFORGE_ROOT", "."))).resolve()
    database = root / "data/ruleforge.sqlite3"
    initialize(database)
    app = FastAPI(title="RuleForge", version="0.1.0")

    @app.get("/api/health")
    def health():
        from ruleforge.rules.service import load_verified
        with connect(database) as conn:
            count = conn.execute("SELECT count(*) FROM rules WHERE review_status='verified'").fetchone()[0]
        try:
            load_verified(root)
            ready, reason = True, None
        except (EvidenceError, ValueError, OSError) as exc:
            ready, reason = False, str(exc)
        return {"status": "ok", "phase": "M1", "ruleset": "srd-5.1",
                "verified_rules": count, "ac_ready": ready, "reason": reason,
                "combat_supported": False, "homebrew_supported": False}

    @app.get("/api/rules")
    def rules():
        with connect(database) as conn:
            return [dict(row) for row in conn.execute("SELECT id,version,ruleset,category,review_status FROM rules")]

    @app.get("/api/sources")
    def sources():
        with connect(database) as conn:
            return [dict(row) for row in conn.execute(
                "SELECT s.*,d.source_url,d.sha256 document_sha256 FROM source_spans s JOIN parse_runs p ON p.id=s.run_id JOIN documents d ON d.id=p.document_id")]

    @app.get("/api/source/pdf")
    def pdf():
        if not (root / PDF_PATH).is_file():
            raise HTTPException(404, "Source PDF missing")
        return FileResponse(root / PDF_PATH, media_type="application/pdf")

    @app.post("/api/evaluate/ac")
    def ac(request: ACRequest):
        from ruleforge.rules.service import calculate_ac
        try:
            return calculate_ac(root, request.abilities, request.equipment)
        except EvidenceError as exc:
            raise HTTPException(503, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        except OSError as exc:
            raise HTTPException(503, "Evidence file unavailable") from exc

    return app
