import argparse
import json
from pathlib import Path
from ruleforge.ingestion.xparse import finalize, run_parse
from ruleforge.rules.service import publish
from ruleforge.persistence.db import initialize

def main():
    parser = argparse.ArgumentParser(description="RuleForge M1 evidence pipeline")
    parser.add_argument("--root", type=Path, default=Path("."))
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("init")
    ingest = sub.add_parser("parse", help="Official CLI, free route only; no retries")
    ingest.add_argument("--executable", type=Path, required=True)
    finish = sub.add_parser("finalize", help="Record the observed exit code from a standalone CLI run")
    finish.add_argument("run_id")
    finish.add_argument("--exit-code", type=int, required=True)
    finish.add_argument("--parser-version", required=True)
    review = sub.add_parser("publish")
    review.add_argument("run_id")
    args = parser.parse_args()
    root = args.root.resolve()
    if args.action == "init":
        initialize(root / "data/ruleforge.sqlite3")
    elif args.action == "parse":
        print(json.dumps(run_parse(root,args.executable),indent=2))
    elif args.action == "finalize":
        print(json.dumps(finalize(root,args.run_id,args.exit_code,args.parser_version),indent=2))
    elif args.action == "publish":
        print(json.dumps(publish(root,args.run_id),indent=2))

if __name__ == "__main__":
    main()
