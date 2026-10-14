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
