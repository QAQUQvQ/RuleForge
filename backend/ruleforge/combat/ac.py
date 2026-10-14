from typing import Literal
from pydantic import Field
from ruleforge.domain.models import StrictModel, Abilities, VersionedRecordRef
from ruleforge.catalog.equipment import ArmorDefinition, ShieldDefinition
from ruleforge.combat.characters import Characters, ABILITY, ARMOR
from ruleforge.combat.modifiers import armor_class
from ruleforge.combat.errors import RuleError


class EquipmentACRequest(StrictModel):
    abilities: Abilities
    armor: VersionedRecordRef | None = None
    shield: VersionedRecordRef | None = None
    alternative_ac: Literal[False] = False
    armor_proficiencies: list[Literal['light','medium','heavy','shield']] = Field(default_factory=list,max_length=4)


def equipment_ac(characters: Characters, request: EquipmentACRequest):
    with characters.transaction() as (_conn,scope):
        scope.require(ABILITY);scope.require(ARMOR)
        if request.armor is None:
            raise RuleError('rule_unverified','Ordinary unarmored AC lacks direct source evidence',409)
        armor=scope.require(request.armor.id,request.armor.version).normalized_payload
        shield=scope.require(request.shield.id,request.shield.version).normalized_payload if request.shield else None
        if not isinstance(armor,ArmorDefinition) or (shield is not None and not isinstance(shield,ShieldDefinition)):
            raise RuleError('invalid_equipment','Armor/shield references must have the matching definition type')
        result=armor_class(request.abilities.dexterity,armor,shield)
        result.update(equipment_refs=[r.model_dump() for r in (request.armor,request.shield) if r],
            equipment_consequences={'armor_nonproficiency':armor.armor_category not in request.armor_proficiencies
                                     or bool(shield and 'shield' not in request.armor_proficiencies),
                'stealth_disadvantage':armor.stealth_disadvantage,
                'speed_reduction_ft':10 if armor.strength_requirement and request.abilities.strength<armor.strength_requirement else 0},
            **scope.evidence())
        return result
