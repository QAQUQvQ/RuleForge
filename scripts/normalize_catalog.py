"""Offline M1+ import. No network or xParse invocation."""
import argparse
import json
from pathlib import Path
from ruleforge.ingestion.pipeline import run_pipeline

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path.cwd())
    parser.add_argument('--run-id',default='srd51-full-001')
    parser.add_argument('--category',action='append')
    args=parser.parse_args()
    report=run_pipeline(args.root,args.run_id,args.category)
    print(json.dumps(report,ensure_ascii=False,indent=2))
    raise SystemExit(0 if report['status']=='passed' else 1)
