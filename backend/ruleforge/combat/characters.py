"""Versioned level-one Fighter service. All writes and authorization checks are atomic."""
from contextlib import contextmanager
from uuid import uuid4
from typing import Annotated, Literal
from pydantic import Field, model_validator
from ruleforge.domain.models import (StrictModel, Character, Abilities, HitPoints, EquipmentInstance,
                                     VersionedRecordRef)
from ruleforge.combat.runtime import Runtime, ResolutionScope
from ruleforge.combat.errors import RuleError
from ruleforge.combat.modifiers import ability_modifier, armor_class
from ruleforge.catalog.equipment import ArmorDefinition, ShieldDefinition, WeaponDefinition
from ruleforge.persistence.db import connect
from ruleforge.ingestion.evidence import evidence_snapshot

FIGHTER = 'srd51.class.fighter'
ABILITY = 'srd51.general_rule.ability-modifier'
ARMOR = 'srd51.general_rule.m2-armor'
ATTACK = 'srd51.general_rule.m2-attack'
DAMAGE = 'srd51.general_rule.m2-damage'
SKILLS = ['Acrobatics','Animal Handling','Athletics','History','Insight','Intimidation','Perception','Survival']
PROFICIENCIES = ['light','medium','heavy','shield','simple','martial','strength_save','constitution_save']


class CreateCharacter(StrictModel):
    name: str = Field(min_length=1,max_length=100)
    ruleset: Literal['srd-5.1'] = 'srd-5.1'
    level: Literal[1] = 1
    abilities: Abilities
    skills: list[str] = Field(min_length=2,max_length=2)
    # Externally supplied final ability scores and base speed; race/background not synthesized.
    speed_ft: Annotated[int,Field(ge=0,le=1000)]
    origin_confirmed: Literal[True]
    class_ref: VersionedRecordRef = VersionedRecordRef(id=FIGHTER)
    fighting_style: Literal['defense'] = 'defense'
    starting_loadout: Literal['chain-longsword-shield-handaxes-explorer'] = 'chain-longsword-shield-handaxes-explorer'

    @model_validator(mode='after')
    def skill_selection(self):
        if len(set(self.skills)) != 2 or not set(self.skills) <= set(SKILLS):
            raise ValueError('choose two distinct Fighter skills')
        if self.class_ref != VersionedRecordRef(id=FIGHTER):
            raise ValueError('only verified Fighter v1 level-one profile supported')
        return self


class PatchCharacter(StrictModel):
    expected_version: Annotated[int,Field(ge=0)]
    name: str | None = Field(default=None,min_length=1,max_length=100)
    abilities: Abilities | None = None
    skills: list[str] | None = Field(default=None,min_length=2,max_length=2)
    speed_ft: Annotated[int,Field(ge=0,le=1000)] | None = None
    inventory: list[EquipmentInstance] | None = Field(default=None,max_length=100)


class Characters:
    def __init__(self, catalog):
        self.catalog, self.runtime = catalog, Runtime(catalog)

    @contextmanager
    def transaction(self, *, write=False):
        with connect(self.catalog.database) as conn, evidence_snapshot():
            conn.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
            yield conn, ResolutionScope(self.runtime, conn)

    def load(self, conn, character_id):
        row = conn.execute('SELECT * FROM characters WHERE id=?',(character_id,)).fetchone()
        if not row:
            raise RuleError('not_found','Character not found',404)
        char = Character.model_validate_json(row['state_json'])
        if char.id != character_id or char.version != row['version']:
            raise RuleError('integrity_failure','Character identity/version mismatch',409)
        stored = [EquipmentInstance.model_validate_json(r[0]) for r in conn.execute(
            'SELECT instance_json FROM character_equipment WHERE character_id=? ORDER BY ordinal',(character_id,))]
        if stored != char.inventory:
            raise RuleError('integrity_failure','Equipment index differs from character snapshot',409)
        return char

    def validate(self, char, scope):
        if char.class_ref != VersionedRecordRef(id=FIGHTER) or char.level != 1 or char.fighting_style != 'defense':
            raise RuleError('unsupported_context','Only level-one Fighter / Defense profile is enabled')
        cls=scope.require(FIGHTER)
        scope.require(ABILITY)
        scope.require(ARMOR)
        if char.proficiency_bonus != cls.normalized_payload.progression[0].proficiency_bonus or char.proficiencies != PROFICIENCIES:
            raise RuleError('integrity_failure','Character proficiency differs from class template')
        if len(set(char.skills)) != 2 or not set(char.skills) <= set(SKILLS):
            raise RuleError('invalid_character','Invalid Fighter skill selection')
        if char.hp.maximum != 10+ability_modifier(char.abilities.constitution):
            raise RuleError('integrity_failure','HP maximum differs from verified class template')
        if char.conditions or char.equipment.alternative_ac or char.equipment.armor != 'none' or char.equipment.shield:
            raise RuleError('unsupported_context','Conditions and legacy equipment cannot be mixed into M2 calculations')
        slots, equipment = {}, []
        for item in char.inventory:
            if item.character_id != char.id:
                raise RuleError('invalid_equipment','Equipment belongs to a different character')
            try:
                record = scope.require(item.equipment_record_id,item.record_version)
            except RuleError as exc:
                if exc.code == 'missing_adapter':
                    raise RuleError('invalid_equipment',str(exc)) from exc
                raise
            if record.record_type != 'equipment':
                raise RuleError('invalid_equipment','Equipment reference must name an equipment definition')
            definition = record.normalized_payload
            equipment.append((item,definition))
            if item.equipped:
                if item.quantity != 1 or item.equipment_slot in slots:
                    raise RuleError('invalid_equipment','Only one equipped item per slot is allowed')
                if (isinstance(definition,ArmorDefinition) and item.equipment_slot != 'body'
                    or isinstance(definition,ShieldDefinition) and item.equipment_slot != 'off_hand'
                    or isinstance(definition,WeaponDefinition) and item.equipment_slot != 'main_hand'
                    or definition.equipment_type == 'adventuring_gear'):
                    raise RuleError('invalid_equipment','Unsupported equipment slot/type combination')
                slots[item.equipment_slot]=definition
        return equipment,slots

    def save(self, conn, char, expected=None):
        if expected is None:
            conn.execute('INSERT INTO characters VALUES (?,?,?)',(char.id,char.version,char.model_dump_json()))
        elif conn.execute('UPDATE characters SET version=?,state_json=? WHERE id=? AND version=?',
                          (char.version,char.model_dump_json(),char.id,expected)).rowcount != 1:
            raise RuleError('version_conflict','Character changed; reload before editing',409)
        conn.execute('DELETE FROM character_equipment WHERE character_id=?',(char.id,))
        conn.executemany('INSERT INTO character_equipment VALUES (?,?,?,?,?)',
            [(char.id,i,e.equipment_record_id,e.record_version,e.model_dump_json()) for i,e in enumerate(char.inventory)])

    def create(self, request: CreateCharacter):
        with self.transaction(write=True) as (conn,scope):
            cls=scope.require(FIGHTER)
            scope.require(ABILITY)
            char_id=uuid4().hex
            inventory=[EquipmentInstance(character_id=char_id,equipment_record_id='srd51.equipment.'+name,
                quantity=quantity,equipped=slot!='inventory',equipment_slot=slot)
                for name,quantity,slot in [('chain-mail',1,'body'),('longsword',1,'main_hand'),('shield',1,'off_hand'),
                                           ('handaxe',2,'inventory'),('explorers-pack',1,'inventory')]]
            maximum=10+ability_modifier(request.abilities.constitution)
            char=Character(id=char_id,name=request.name,abilities=request.abilities,version=1,
                hp=HitPoints(maximum=maximum,current=maximum),speed_ft=request.speed_ft,
                class_ref=request.class_ref,proficiency_bonus=cls.normalized_payload.progression[0].proficiency_bonus,
                skills=request.skills,proficiencies=PROFICIENCIES,fighting_style='defense',inventory=inventory,
                resources={'second_wind':1},
                creation_scope='Fighter class profile; final scores/speed supplied by caller; race/background excluded; Second Wind reference only')
            self.validate(char,scope)
            char=char.model_copy(update={'rule_refs':[VersionedRecordRef(id=r['id'],version=r['version']) for r in scope.refs.values()]})
            self.save(conn,char)
            return self.card(char,scope)

    def card(self,char,scope):
        return {'character':char.model_dump(), 'ability_modifiers':{k:ability_modifier(v) for k,v in char.abilities.model_dump().items()},
                'attacks':[{'weapon_id':i.equipment_record_id,'record_version':i.record_version}
                           for i in char.inventory if i.equipped and i.equipment_slot=='main_hand'], **scope.evidence()}

    def get(self,character_id):
        with self.transaction() as (conn,scope):
            char=self.load(conn,character_id)
            self.validate(char,scope)
            return self.card(char,scope)

    def patch(self,character_id,request: PatchCharacter):
        with self.transaction(write=True) as (conn,scope):
            char=self.load(conn,character_id)
            if char.version != request.expected_version:
                raise RuleError('version_conflict','Character changed; reload before editing',409)
            updates=request.model_dump(exclude_none=True,exclude={'expected_version'})
            state=char.model_dump();state.update(updates);state['version']+=1
            if request.abilities is not None:
                maximum=10+ability_modifier(request.abilities.constitution)
                state['hp'].update(maximum=maximum,current=min(maximum,char.hp.current))
            updated=Character.model_validate(state)
            self.validate(updated,scope)
            updated=updated.model_copy(update={'rule_refs':[VersionedRecordRef(id=r['id'],version=r['version']) for r in scope.refs.values()]})
            self.save(conn,updated,request.expected_version)
            return self.card(updated,scope)

    def ac_for(self,char,scope):
        _,slots=self.validate(char,scope)
        armor=slots.get('body');shield=slots.get('off_hand')
        if armor is None:
            raise RuleError('rule_unverified','Ordinary unarmored AC source is absent from pinned SRD extraction; calculation refused',409)
        result=armor_class(char.abilities.dexterity,armor,shield,defense=char.fighting_style=='defense')
        nonproficient=armor.armor_category not in char.proficiencies or bool(shield and 'shield' not in char.proficiencies)
        result.update(equipment_refs=[{'id':i.equipment_record_id,'version':i.record_version}
                      for i in char.inventory if i.equipped],
            equipment_consequences={'armor_nonproficiency':nonproficient,
                'stealth_disadvantage':armor.stealth_disadvantage,
                'speed_reduction_ft':10 if armor.strength_requirement and char.abilities.strength<armor.strength_requirement else 0},
            **scope.evidence())
        return result

    def ac(self,character_id):
        with self.transaction() as (conn,scope):
            return self.ac_for(self.load(conn,character_id),scope)
