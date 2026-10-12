from typing import Annotated, Literal
from pydantic import Field, TypeAdapter, model_validator
from ruleforge.domain.models import StrictModel
from ruleforge.rules.sources import Identifier, Ruleset, ValidationStatus, ReviewStatus, ExecutionStatus
from ruleforge.catalog.equipment import EquipmentUnion, DiceExpression, DamageType

class TextEffect(StrictModel):
    kind: Literal["reference_text"] = "reference_text"
    text: str = Field(min_length=1)
    source_ids: list[Identifier] = Field(min_length=1)

class SpellComponents(StrictModel):
    verbal: bool
    somatic: bool
    material: bool
    material_description: str | None = None
    @model_validator(mode="after")
    def material_consistency(self):
        if not self.material and self.material_description is not None:
            raise ValueError("non-material spell cannot have materials")
        return self

class SpellDamage(StrictModel):
    dice: DiceExpression
    damage_type: DamageType
    per: str
    source_ids: list[Identifier] = Field(min_length=1)

class SpellPayload(StrictModel):
    level: Annotated[int,Field(ge=0,le=9)]
    school: Literal["abjuration","conjuration","divination","enchantment","evocation","illusion","necromancy","transmutation"]
    casting_time: str = Field(min_length=1)
    range: str = Field(min_length=1)
    components: SpellComponents
    duration: str = Field(min_length=1)
    concentration: bool
    ritual: bool
    description: str = Field(min_length=1)
    higher_levels: str | None = None
    effects: list[TextEffect] = Field(default_factory=list)
    damage: list[SpellDamage] = Field(default_factory=list)

class TableCell(StrictModel):
    row: Annotated[int,Field(ge=0)]
    column: Annotated[int,Field(ge=0)]
    origin_row: Annotated[int,Field(ge=0)]
    origin_column: Annotated[int,Field(ge=0)]
    rowspan: Annotated[int,Field(ge=1,le=100)]
    colspan: Annotated[int,Field(ge=1,le=100)]
    text: str
    source_id: Identifier

class ProgressionRow(StrictModel):
    level: Annotated[int,Field(ge=1,le=20)]
    proficiency_bonus: Annotated[int,Field(ge=2,le=6)]
    feature_names: list[str] = Field(min_length=1)
    cells: list[TableCell] = Field(min_length=3,max_length=100)

class FeatureReference(StrictModel):
    name: str
    source_ids: list[Identifier] = Field(min_length=1)
    rule_id: Identifier | None = None

class Proficiencies(StrictModel):
    armor: str
    weapons: str
    tools: str
    saving_throws: list[str]
    skills: str

class ClassPayload(StrictModel):
    description: str
    hit_die: DiceExpression
    proficiencies: Proficiencies
    progression_columns: list[str] = Field(min_length=3)
    progression: list[ProgressionRow] = Field(min_length=1,max_length=20)
    feature_references: list[FeatureReference]
    @model_validator(mode="after")
    def ordered_levels(self):
        levels = [r.level for r in self.progression]
        if levels != sorted(set(levels)):
            raise ValueError("class levels must be unique and ordered")
        return self

class ConditionPayload(StrictModel):
    description: str
    applicability: list[str] = Field(default_factory=list)
    effects: list[TextEffect] = Field(min_length=1)
    removal_conditions: list[str] = Field(default_factory=list)
    related_rule_ids: list[Identifier] = Field(default_factory=list)

class GeneralRulePayload(StrictModel):
    category: Literal["attack","armor_class","ability_modifier","advantage","saving_throw","action_economy","damage","hit_points","other"]
    description: str
    trigger: str | None = None
    prerequisites: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    resolution_steps: list[str] = Field(default_factory=list)
    effect_specification: list[TextEffect] = Field(default_factory=list)
    related_rule_ids: list[Identifier] = Field(default_factory=list)

class RuleRecord(StrictModel):
    id: Identifier
    ruleset: Ruleset = "srd-5.1"
    record_version: Annotated[int,Field(ge=1)] = 1
    record_type: str
    canonical_name: str = Field(min_length=1,max_length=200)
    aliases: list[str] = Field(default_factory=list,max_length=100)
    source_ids: list[Identifier] = Field(default_factory=list,max_length=128)
    extraction_run_id: Identifier
    field_sources: dict[str,list[Identifier]] = Field(default_factory=dict)
    validation_status: ValidationStatus = "extracted"
    review_status: ReviewStatus = "review_required"
    execution_status: ExecutionStatus = "reference_only"
    schema_version: Literal["1"] = "1"

    @model_validator(mode="after")
    def source_contract(self):
        if len(set(self.source_ids)) != len(self.source_ids):
            raise ValueError("duplicate source ids")
        if self.validation_status == "validated" or self.review_status == "approved" or self.execution_status in ("executable","partially_executable"):
            if not self.source_ids:
                raise ValueError("validated/approved/executable record requires sources")
        if self.review_status == "approved" and self.validation_status != "validated":
            raise ValueError("approval requires validation")
        if self.execution_status in ("executable","partially_executable") and self.review_status != "approved":
            raise ValueError("execution capability requires approval plus separate runtime verification")
        if any(not ids or not set(ids) <= set(self.source_ids) for ids in self.field_sources.values()):
            raise ValueError("invalid field source mapping")
        payload = getattr(self, "normalized_payload", None)
        def check_sources(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    if key == "source_id" and child not in self.source_ids:
                        raise ValueError("nested source is not registered")
                    if key == "source_ids" and not set(child) <= set(self.source_ids):
                        raise ValueError("nested sources are not registered")
                    check_sources(child)
            elif isinstance(value, list):
                for child in value:
                    check_sources(child)
        if payload is not None:
            check_sources(payload.model_dump())
        return self

class EquipmentRecord(RuleRecord):
    record_type: Literal["equipment"] = "equipment"
    normalized_payload: EquipmentUnion
    @model_validator(mode="after")
    def same_identity(self):
        p = self.normalized_payload
        if p.id != self.id or p.ruleset != self.ruleset or p.canonical_name != self.canonical_name:
            raise ValueError("equipment record/payload identity mismatch")
        if set(p.source_ids) != set(self.source_ids) or p.review_status != self.review_status:
            raise ValueError("equipment sources/review mismatch")
        return self

class SpellRecord(RuleRecord):
    record_type: Literal["spell"] = "spell"
    normalized_payload: SpellPayload

class ClassRecord(RuleRecord):
    record_type: Literal["class"] = "class"
    normalized_payload: ClassPayload

class ConditionRecord(RuleRecord):
    record_type: Literal["condition"] = "condition"
    normalized_payload: ConditionPayload

class GeneralRuleRecord(RuleRecord):
    record_type: Literal["general_rule"] = "general_rule"
    normalized_payload: GeneralRulePayload

NormalizedRecord = Annotated[EquipmentRecord | SpellRecord | ClassRecord | ConditionRecord | GeneralRuleRecord,Field(discriminator="record_type")]
RECORD_ADAPTER = TypeAdapter(NormalizedRecord)

def parse_record(data) -> RuleRecord:
    return RECORD_ADAPTER.validate_json(data) if isinstance(data,(str,bytes)) else RECORD_ADAPTER.validate_python(data)
