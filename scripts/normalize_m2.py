"""Import validated candidates only. Reads existing xParse artifacts offline."""
import json
from pathlib import Path
from ruleforge.ingestion.m2 import import_candidates
from ruleforge.ingestion.evidence import evidence_snapshot

if __name__ == '__main__':
    with evidence_snapshot():
        print(json.dumps(import_candidates(Path(__file__).resolve().parents[1]),ensure_ascii=False,indent=2))
