"""Runtime golden vectors: failures revoke capability, never fall back to defaults."""
from ruleforge.combat.modifiers import ability_modifier, proficiency, armor_class
from ruleforge.combat.dice import Dice
from ruleforge.combat.attacks import attack, AttackContext
from ruleforge.combat.damage import damage, apply_hp, DamageComponent, Defenses
from ruleforge.domain.models import Abilities, HitPoints
from ruleforge.catalog.models import parse_record
from ruleforge.ingestion.evidence import EvidenceError


def fixed_tests():
    from ruleforge.combat.runtime import templates
    data = templates()
    equip = lambda name: parse_record(data['srd51.equipment.'+name]['record']).normalized_payload
    cases = []

    def check(name, actual, expected):
        if actual != expected:
            raise EvidenceError('runtime golden failed: '+name)
        cases.append({'name': name, 'expected': expected, 'actual': actual})

    for score, expected in [(1,-5),(9,-1),(10,0),(14,2),(30,10)]:
        check('ability '+str(score), ability_modifier(score), expected)
    for level, expected in [(1,2),(4,2),(5,3),(9,4),(13,5),(17,6),(20,6)]:
        check('proficiency '+str(level), proficiency(level), expected)
    for name, dex, expected in [('leather',14,13),('chain-shirt',18,15),('chain-shirt',9,12),('chain-mail',9,16)]:
        check(name+str(dex), armor_class(dex, equip(name))['ac'], expected)
    check('chain + shield', armor_class(18,equip('chain-mail'),equip('shield'))['ac'],18)
    check('Defense', armor_class(18,equip('chain-mail'),equip('shield'),defense=True)['ac'],19)
    check('fighter starting HP', 10+ability_modifier(14),12)
    ctx = dict(mode='melee',distance_ft=5,scene_confirmed=True,target_visible=True,cover='none',hostile_within_5ft=False)
    for rolls, flags, expected in [([1],{},[False,False,1]),([20],{},[True,True,20]),
            ([3,17],{'advantage':True},[True,False,17]),([3,17],{'disadvantage':True},[False,False,3]),
            ([12],{'advantage':True,'disadvantage':True},[True,False,12])]:
        result = attack('a','b',equip('dagger'),Abilities(dexterity=14),True,2,14,AttackContext(**ctx,**flags),Dice(fixed=rolls))
        check('attack '+str(rolls)+str(flags),[result.hit,result.critical,result.selected_d20],expected)
    result = damage([DamageComponent(damage_type='piercing',dice={'expression':'1d4+1'},modifier=2)],
                    Defenses(resistance=['piercing'],vulnerability=['piercing']),Dice(fixed=[3,4]),critical=True)
    check('critical fixed bonus once then resistance/vulnerability',result['total'],10)
    check('immunity',damage([DamageComponent(damage_type='fire',dice={'expression':'1d6'})],
          Defenses(immunity=['fire']),Dice(fixed=[6]))['total'],0)
    hp=apply_hp(HitPoints(maximum=10,current=5,temporary=2),8)
    check('HP overflow',[hp['after']['current'],hp['temporary_absorbed'],hp['overflow']],[0,2,1])
    return {'status':'passed','cases':cases}
