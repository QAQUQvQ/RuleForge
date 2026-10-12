import json
from pathlib import Path
from pydantic import TypeAdapter
from ruleforge.domain.models import Character, Creature, Item, CombatState, Command, DomainEvent
from ruleforge.rules.dsl import RuleDSL
from ruleforge.rules.models import SourceSpan, RuleRecord
target = Path("docs/schemas")
target.mkdir(parents=True,exist_ok=True)
models = {"character":Character,"creature":Creature,"item":Item,"combat-state":CombatState,
          "command":Command,"event":DomainEvent,"rule-dsl":RuleDSL,"source-span":SourceSpan,"rule-record":RuleRecord}
for name, model in models.items():
    (target / (name+".schema.json")).write_text(json.dumps(TypeAdapter(model).json_schema(),ensure_ascii=False,indent=2),encoding="utf-8")
