import json
from typing import Annotated, Literal
from pydantic import Field, model_validator
from ruleforge.domain.models import StrictModel, Abilities, Equipment

class Constant(StrictModel):
    op: Literal["const"]
    value: Annotated[int, Field(ge=-100, le=100)]

class AbilityModifier(StrictModel):
    op: Literal["ability_modifier"]
    ability: Literal["dexterity"]

class Add(StrictModel):
    op: Literal["add"]
    args: list["Expression"] = Field(min_length=2, max_length=8)

Expression = Annotated[Constant | AbilityModifier | Add, Field(discriminator="op")]
Add.model_rebuild()

class ArmorCondition(StrictModel):
    field: Literal["armor"]
    op: Literal["eq"]
    value: Literal["leather"]

class ShieldCondition(StrictModel):
    field: Literal["shield"]
    op: Literal["eq"]
    value: Literal[False]

class AlternativeCondition(StrictModel):
    field: Literal["alternative_ac"]
    op: Literal["eq"]
    value: Literal[False]

Condition = Annotated[ArmorCondition | ShieldCondition | AlternativeCondition, Field(discriminator="field")]

class RuleDSL(StrictModel):
    dsl_version: Literal["1"] = "1"
    id: Literal["srd51.ac.leather"]
    version: Literal[1] = 1
    ruleset: Literal["srd-5.1"]
    category: Literal["armor_class"]
    requires: list[Condition] = Field(min_length=3, max_length=3)
    expression: Expression

    @model_validator(mode="after")
    def validate_tree(self):
        if {c.field for c in self.requires} != {"armor", "shield", "alternative_ac"}:
            raise ValueError("all applicability guards required")
        todo, count = [(self.expression, 1)], 0
        while todo:
            node, depth = todo.pop()
            count += 1
            if count > 64 or depth > 8:
                raise ValueError("DSL complexity limit exceeded")
            if isinstance(node, Add):
                todo.extend((a, depth + 1) for a in node.args)
        return self

def base_ac_rule() -> RuleDSL:
    return RuleDSL.model_validate({
        "id": "srd51.ac.leather", "ruleset": "srd-5.1", "category": "armor_class",
        "requires": [
            {"field": "armor", "op": "eq", "value": "leather"},
            {"field": "shield", "op": "eq", "value": False},
            {"field": "alternative_ac", "op": "eq", "value": False}],
        "expression": {"op": "add", "args": [
            {"op": "const", "value": 11},
            {"op": "ability_modifier", "ability": "dexterity"}]}})

def canonical(rule: RuleDSL) -> str:
    return json.dumps(rule.model_dump(), sort_keys=True, separators=(",", ":"))

def evaluate(rule: RuleDSL, abilities: Abilities, equipment: Equipment) -> dict:
    # Explicit dispatch only: no eval, exec, getattr, imports or user functions.
    fields = {"armor": equipment.armor, "shield": equipment.shield, "alternative_ac": equipment.alternative_ac}
    if any(fields[c.field] != c.value for c in rule.requires):
        raise ValueError("Unsupported AC context: requires leather armor, no shield, no alternative formula")
    trace = []
    def visit(node):
        if isinstance(node, Constant):
            trace.append(f"constant = {node.value}")
            return node.value
        if isinstance(node, AbilityModifier):
            value = (abilities.dexterity - 10) // 2
            trace.append(f"dexterity modifier = floor(({abilities.dexterity} - 10) / 2) = {value}")
            return value
        if isinstance(node, Add):
            values = [visit(arg) for arg in node.args]
            value = sum(values)
            trace.append(f"add {values} = {value}")
            return value
        raise ValueError("unsupported operation")
    return {"ac": visit(rule.expression), "rule_id": rule.id, "rule_version": rule.version, "trace": trace}
