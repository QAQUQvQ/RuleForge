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

from ruleforge.rules.sources import SourceReference
from ruleforge.catalog.equipment import EquipmentUnion
from ruleforge.catalog.models import (NormalizedRecord, EquipmentRecord, SpellRecord, ClassRecord,
    ConditionRecord, GeneralRuleRecord)
models = {"source-reference": SourceReference, "equipment-definition": EquipmentUnion,
          "normalized-record": NormalizedRecord, "equipment-record": EquipmentRecord,
          "spell-record": SpellRecord, "class-record": ClassRecord,
          "condition-record": ConditionRecord, "general-rule-record": GeneralRuleRecord}
for name, model in models.items():
    (target / (name+".schema.json")).write_text(json.dumps(TypeAdapter(model).json_schema(),ensure_ascii=False,indent=2),encoding="utf-8")

# M2 public contracts; CombatState/Command/Event retain their separate M3 meaning.
from ruleforge.domain.models import EquipmentInstance
from ruleforge.combat.characters import CreateCharacter, PatchCharacter
from ruleforge.combat.attacks import AttackContext, AttackResult
from ruleforge.combat.service import PreviewRequest, ResolutionPreview
from ruleforge.combat.ac import EquipmentACRequest
from ruleforge.combat.damage import DamageComponent, Defenses
models = {"equipment-instance":EquipmentInstance,"create-character":CreateCharacter,"patch-character":PatchCharacter,
          "attack-context":AttackContext,"attack-result":AttackResult,"preview-request":PreviewRequest,
          "resolution-preview":ResolutionPreview,"equipment-ac-request":EquipmentACRequest,
          "damage-component":DamageComponent,"damage-defenses":Defenses}
for name, model in models.items():
    (target / (name+".schema.json")).write_text(json.dumps(TypeAdapter(model).json_schema(),ensure_ascii=False,indent=2),encoding="utf-8")

# M3 payloads are separately validated by the service. Publish their precise shapes
# alongside the backwards-compatible domain command envelope.
from ruleforge.encounters.contracts import CreateEncounter, PAYLOAD_TYPES
(target/'create-encounter.schema.json').write_text(json.dumps(CreateEncounter.model_json_schema(),ensure_ascii=False,indent=2),encoding='utf-8')
schema=TypeAdapter(Command).json_schema()
for definition in list(schema['$defs'].values()):
    properties=definition.get('properties',{})
    kind=properties.get('type',{}).get('const')
    if kind in PAYLOAD_TYPES:
        payload=PAYLOAD_TYPES[kind].model_json_schema()
        schema['$defs'].update(payload.pop('$defs',{}))
        properties['payload']=payload
        if payload.get('required') and 'payload' not in definition.get('required',[]):
            definition.setdefault('required',[]).append('payload')
(target/'command.schema.json').write_text(json.dumps(schema,ensure_ascii=False,indent=2),encoding='utf-8')
