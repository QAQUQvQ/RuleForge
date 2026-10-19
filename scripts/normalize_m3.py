"""Offline candidate import only. Never reviews, publishes or grants execution."""
import argparse
from pathlib import Path
from ruleforge.encounters.evidence import import_candidates, TURN, READY

if __name__=='__main__':
    root=Path(__file__).resolve().parents[1]
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',type=Path,default=root/'data/ruleforge.sqlite3')
    args=parser.parse_args()
    import_candidates(root,args.database)
    print({'records':[TURN,READY],'policy':'candidates only; explicit review/publication/grants still required'})
