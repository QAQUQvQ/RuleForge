"""Explicit isolated demo app; does not create or approve rules on startup."""
import argparse
from pathlib import Path
import uvicorn
from ruleforge.encounters.demo import create_demo_app

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',type=Path,required=True)
    parser.add_argument('--port',type=int,default=8000)
    args=parser.parse_args()
    if not args.database.is_file():parser.error('Prepare a separate demo database first')
    uvicorn.run(create_demo_app(Path(__file__).resolve().parents[1],args.database),host='127.0.0.1',port=args.port)
