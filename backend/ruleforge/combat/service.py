"""Read-only M2 resolution preview with an isolated target HP snapshot."""
from typing import Annotated, Literal
from pydantic import Field
from ruleforge.domain.models import StrictModel, HitPoints
from ruleforge.combat.characters import Characters, ATTACK, DAMAGE
from ruleforge.combat.attacks import AttackContext, attack
from ruleforge.combat.damage import Defenses, DamageComponent, damage, apply_hp
from ruleforge.combat.dice import Dice
from ruleforge.combat.errors import RuleError
from ruleforge.catalog.equipment import WeaponDefinition


class PreviewRequest(StrictModel):
    attacker_id: str = Field(min_length=1,max_length=100)
    expected_version: Annotated[int,Field(ge=1)]
    weapon_id: str = Field(min_length=1,max_length=200)
    target_id: str = Field(min_length=1,max_length=100)
    target_ac: Annotated[int,Field(ge=0,le=100)]
    target_hp: HitPoints
    target_defenses: Defenses = Field(default_factory=Defenses)
    target_scope: Literal['isolated_dm_input']
    context: AttackContext
    fixed_dice: list[Annotated[int,Field(ge=1,le=100)]] | None = Field(default=None,max_length=1000)


class ResolutionPreview(StrictModel):
    kind: Literal['resolution_preview'] = 'resolution_preview'
    dice_mode: str
    attacker_version: int
    ac: dict
    attack: dict
    damage: dict
    hp: dict
    dice: list[dict]
    rule_refs: list[dict]
    source_refs: list[dict]
    trace: list[str]


def preview(characters: Characters, request: PreviewRequest):
    with characters.transaction() as (conn,scope):
        char=characters.load(conn,request.attacker_id)
        if char.version != request.expected_version:
            raise RuleError('version_conflict','Attacker version changed',409)
        ac=characters.ac_for(char,scope)
        scope.require(ATTACK);scope.require(DAMAGE)
        selected=[i for i in char.inventory if i.equipped and i.equipment_slot=='main_hand' and i.equipment_record_id==request.weapon_id]
        if len(selected)!=1:
            raise RuleError('invalid_equipment','Attack requires the equipped main-hand weapon')
        item=selected[0]
        weapon=scope.require(item.equipment_record_id,item.record_version).normalized_payload
        if not isinstance(weapon,WeaponDefinition) or weapon.damage_dice is None:
            raise RuleError('invalid_equipment','No supported weapon damage definition')
        dice=Dice(fixed=request.fixed_dice)
        result=attack(char.id,request.target_id,weapon,char.abilities,
                      weapon.proficiency_category in char.proficiencies,char.proficiency_bonus,
                      request.target_ac,request.context,dice,
                      armor_disadvantage=ac['equipment_consequences']['armor_nonproficiency'])
        damage_result=damage([DamageComponent(damage_type=weapon.damage_type,dice=weapon.damage_dice,
                            modifier=result.ability_modifier)],request.target_defenses,dice,critical=result.critical) if result.hit else {
                            'components':[],'total':0,'critical':False}
        hp=apply_hp(request.target_hp,damage_result['total'],critical=result.critical)
        dice.finish()
        evidence=scope.evidence()
        attack_result=result.model_dump();attack_result.update(evidence)
        return ResolutionPreview(dice_mode=dice.mode,attacker_version=char.version,ac=ac,
            attack=attack_result,damage=damage_result,hp=hp,dice=dice.log,**evidence,
            trace=['caller confirms scene, target AC and unconditional type defenses',
                   'one ordinary weapon attack; no action economy, reaction or turn legality',
                   'target HP updated only in this isolated preview; no encounter or character HP committed'])
