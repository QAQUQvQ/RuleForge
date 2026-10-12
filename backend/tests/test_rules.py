import pytest
from pydantic import ValidationError
from ruleforge.domain.models import Abilities, Equipment, HitPoints, CombatState, DieRoll
from ruleforge.rules.dsl import RuleDSL, base_ac_rule, evaluate

@pytest.mark.parametrize("dex,expected", [(1,6),(2,7),(9,10),(10,11),(11,11),(14,13),(15,13),(20,16),(30,21)])
def test_leather_ac_goldens(dex, expected):
    result = evaluate(base_ac_rule(), Abilities(dexterity=dex), Equipment(armor="leather"))
    assert result["ac"] == expected
    assert result["rule_id"] == "srd51.ac.leather"
    assert result["trace"]

@pytest.mark.parametrize("equipment", [
    Equipment(), Equipment(armor="heavy"), Equipment(armor="light"),
    Equipment(armor="leather",shield=True), Equipment(armor="leather",alternative_ac=True)])
def test_unsupported_context_fails(equipment):
    with pytest.raises(ValueError, match="Unsupported"):
        evaluate(base_ac_rule(), Abilities(), equipment)

@pytest.mark.parametrize("expression", [
    {"op":"eval","code":"__import__('os').system('echo bad')"},
    {"op":"ability_modifier","ability":"__class__"},
    {"op":"const","value":True}, {"op":"const","value":100000},
    {"op":"add","args":[]}, "__import__('os')"])
def test_malicious_and_invalid_expressions(expression):
    draft = base_ac_rule().model_dump()
    draft["expression"] = expression
    with pytest.raises(ValidationError):
        RuleDSL.model_validate(draft)

def test_unknown_fields():
    draft = base_ac_rule().model_dump()
    draft["python"] = "print('unsafe')"
    with pytest.raises(ValidationError):
        RuleDSL.model_validate(draft)

def test_missing_applicability_guard():
    draft = base_ac_rule().model_dump()
    draft["requires"] = draft["requires"][:2]
    with pytest.raises(ValidationError):
        RuleDSL.model_validate(draft)

def test_depth_limit():
    draft = base_ac_rule().model_dump()
    expr = {"op":"const","value":1}
    for _ in range(9):
        expr = {"op":"add","args":[expr,{"op":"const","value":1}]}
    draft["expression"] = expr
    with pytest.raises(ValidationError):
        RuleDSL.model_validate(draft)

@pytest.mark.parametrize("score", [0,31,True,"14",14.5])
def test_strict_ability_bounds(score):
    with pytest.raises(ValidationError):
        Abilities(dexterity=score)

def test_domain_invariants():
    with pytest.raises(ValidationError):
        HitPoints(maximum=10,current=11)
    with pytest.raises(ValidationError):
        CombatState(id="battle",phase="action")
    with pytest.raises(ValidationError):
        DieRoll(sides=6,value=7)
