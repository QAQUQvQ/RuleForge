import json
from pathlib import Path
from ruleforge.combat.demo import prepare_isolated_demo, run_demo

if __name__=='__main__':
    root=Path(__file__).resolve().parents[1]
    target=root/'data/local-checks'
    target.mkdir(parents=True,exist_ok=True)
    result=run_demo(prepare_isolated_demo(root,target/'m2-demo.sqlite3'))
    (target/'m2-demo-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    out=result['result']
    print(json.dumps({'environment':result['environment'],'character_id':result['character']['character']['id'],
        'ac':out['ac']['ac'],'attack_total':out['attack']['attack_total'],'damage':out['damage']['total'],
        'hp_after':out['hp']['after'],'repeated_identical':result['repeated_identical']},indent=2))
