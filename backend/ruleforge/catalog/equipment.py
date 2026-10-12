from typing import Annotated, Literal
import re
from pydantic import Field, model_validator, field_validator
from ruleforge.domain.models import StrictModel
from ruleforge.rules.sources import Identifier, Ruleset, ReviewStatus

class DiceExpression(StrictModel):
    expression: str = Field(min_length=3,max_length=30)

    @field_validator("expression")
    @classmethod
    def limited_dice(cls,value):
        match = re.fullmatch(r"([1-9][0-9]?)d(4|6|8|10|12|20|100)(?:([+-])([0-9]{1,3}))?", value)
        if not match:
            raise ValueError("Only NdS with an optional integer modifier is allowed")
        return value

class Money(StrictModel):
    amount: str = Field(pattern=r"^(0|[1-9][0-9]*)(\.[0-9]{1,2})?$",max_length=20)
    unit: Literal["cp","sp","ep","gp","pp"]

class Weight(StrictModel):
    amount: str = Field(pattern=r"^(0|[1-9][0-9]*)(\.[0-9]{1,3})?$",max_length=20)
    unit: Literal["lb"]

class Duration(StrictModel):
    amount: Annotated[int, Field(ge=0,le=100000)]
    unit: Literal["action","bonus_action","reaction","round","minute","hour","day"]

class EquipmentDefinition(StrictModel):
    id: Identifier
    ruleset: Ruleset = "srd-5.1"
    canonical_name: str = Field(min_length=1,max_length=200)
    display_name: str = Field(min_length=1,max_length=200)
    equipment_type: str
    description: str
    cost: Money | None = None
    weight: Weight | None = None
    source_ids: list[Identifier] = Field(min_length=1,max_length=128)
    review_status: ReviewStatus = "review_required"
    schema_version: Literal["1"] = "1"

WeaponProperty = Literal["ammunition","finesse","heavy","light","loading","reach","special","thrown","two-handed","versatile"]
DamageType = Literal["acid","bludgeoning","cold","fire","force","lightning","necrotic","piercing","poison","psychic","radiant","slashing","thunder"]

class WeaponDefinition(EquipmentDefinition):
    equipment_type: Literal["weapon"] = "weapon"
    proficiency_category: Literal["simple","martial"]
    attack_category: Literal["melee","ranged"]
    damage_dice: DiceExpression | None
    damage_type: DamageType | None
    weapon_properties: list[WeaponProperty] = Field(default_factory=list)
    normal_range: Annotated[int,Field(ge=1,le=10000)] | None = None
    long_range: Annotated[int,Field(ge=1,le=10000)] | None = None
    range_unit: Literal["ft"] = "ft"
    versatile_damage_dice: DiceExpression | None = None
    special_rules: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def properties_consistent(self):
        if len(set(self.weapon_properties)) != len(self.weapon_properties):
            raise ValueError("duplicate weapon property")
        if (self.normal_range is None) != (self.long_range is None):
            raise ValueError("range pair required")
        if self.normal_range and self.long_range < self.normal_range:
            raise ValueError("long range less than normal range")
        if ("versatile" in self.weapon_properties) != (self.versatile_damage_dice is not None):
            raise ValueError("versatile property/damage mismatch")
        if (self.damage_dice is None) != (self.damage_type is None):
            raise ValueError("damage dice and type required together")
        if self.damage_dice is None and ("special" not in self.weapon_properties or not self.special_rules):
            raise ValueError("no-damage weapon requires an explicit special rule")
        if {"thrown","ammunition"} & set(self.weapon_properties) and self.normal_range is None:
            raise ValueError("ranged property requires sourced range")
        return self

class ArmorDefinition(EquipmentDefinition):
    equipment_type: Literal["armor"] = "armor"
    armor_category: Literal["light","medium","heavy"]
    base_ac: Annotated[int,Field(ge=1,le=30)]
    dexterity_modifier_policy: Literal["full","capped","none"]
    dexterity_modifier_cap: Annotated[int,Field(ge=0,le=10)] | None = None
    strength_requirement: Annotated[int,Field(ge=1,le=30)] | None = None
    stealth_disadvantage: bool
    don_time: Duration | None = None
    doff_time: Duration | None = None

    @model_validator(mode="after")
    def ac_policy(self):
        expected = {"light":"full","medium":"capped","heavy":"none"}[self.armor_category]
        if self.dexterity_modifier_policy != expected:
            raise ValueError("SRD 5.1 armor category/policy mismatch")
        if self.dexterity_modifier_policy == "capped":
            if self.dexterity_modifier_cap != 2:
                raise ValueError("SRD 5.1 medium armor uses a cap of 2")
        elif self.dexterity_modifier_cap is not None:
            raise ValueError("cap only allowed for capped policy")
        return self

class ShieldDefinition(EquipmentDefinition):
    equipment_type: Literal["shield"] = "shield"
    ac_bonus: Annotated[int,Field(ge=0,le=10)]
    equipment_requirements: list[str] = Field(min_length=1)
    don_time: Duration | None = None
    doff_time: Duration | None = None

class AdventuringGearDefinition(EquipmentDefinition):
    equipment_type: Literal["adventuring_gear"] = "adventuring_gear"
    usage_description: str | None = None

EquipmentUnion = Annotated[WeaponDefinition | ArmorDefinition | ShieldDefinition | AdventuringGearDefinition, Field(discriminator="equipment_type")]
