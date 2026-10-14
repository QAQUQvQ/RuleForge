"""Offline, exact-artifact M2 extraction. No network and no implicit approval."""
import json
from pathlib import Path
from ruleforge.ingestion.pipeline import ExtractionContext, equipment, general_rule, money, weight
from ruleforge.ingestion.tables import table_grid
from ruleforge.ingestion.evidence import EvidenceError, digest_text
from ruleforge.catalog.service import canonical, content, CatalogService

RAW_SHA256 = '9473d981252593c3a554255b02b41e9435d2ec884399dcff4def580ca3ad841e'
PDF_SHA256 = '2504d2a0abb0a4d491a939be4f17910a2dde0312570ab8d208080225ccf0a1f0'


def candidates(root):
    ctx = ExtractionContext(root, 'srd51-full-001')
    if ctx.manifest['raw']['sha256'] != RAW_SHA256 or ctx.manifest['document']['sha256'] != PDF_SHA256:
        raise EvidenceError('M2 extractor requires the pinned SRD 5.1 artifacts')
    yield from equipment(ctx)
    yield from general_rule(ctx)
    # Indices are deliberately pinned to the above complete raw SHA, not guessed on new input.
    grid = table_grid(ctx.text(567))
    ref = ctx.reference(567, 'class_progression')
    rows = [dict(level=1, proficiency_bonus=int(grid[1][1]['text']),
                 feature_names=['Fighting Style', 'Second Wind'],
                 cells=[dict(c, source_id=ref.id) for c in grid[1]])]
    ids = [547, 549, 551, 552, 555, 556, 557, 558, 559, 561, 562, 563, 564, 565, 570, 574, 584]
    yield ctx.candidate('class', 'fighter', 'Fighter', dict(
        description='\n'.join(ctx.text(i) for i in ids), hit_die={'expression': '1d10'},
        proficiencies=dict(armor='All armor, shields', weapons='Simple weapons, martial weapons',
            tools='None', saving_throws=['Strength', 'Constitution'], skills=ctx.text(559)),
        progression_columns=[c['text'] for c in grid[0]], progression=rows,
        feature_references=[dict(name='Fighting Style: Defense', source_ids=[ctx.reference(574).id]),
                            dict(name='Second Wind (reference only)', source_ids=[ctx.reference(584).id])]),
        [ctx.reference(i) for i in ids]+[ref])
    for name, category, dice, props, extra in [
        ('Longsword', 'martial', '1d8', ['versatile'], {'versatile_damage_dice': {'expression': '1d10'}}),
        ('Handaxe', 'simple', '1d6', ['light', 'thrown'], {'normal_range': 20, 'long_range': 60})]:
        i, row = ctx.table_row(name, 5)
        text = [c['text'] for c in row]
        if text[2] != dice+' slashing':
            raise EvidenceError('weapon damage pattern changed')
        yield ctx.candidate('equipment', name.lower(), name, dict(equipment_type='weapon',
            description=' | '.join(text), cost=money(text[1]), weight=weight(text[3]),
            proficiency_category=category, attack_category='melee', damage_dice={'expression': dice},
            damage_type='slashing', weapon_properties=props, **extra),
            [ctx.reference(i, 'weapon_table', row[0])])
    yield ctx.candidate('equipment', 'explorers-pack', "Explorer's Pack", dict(
        equipment_type='adventuring_gear', description=ctx.text(1761), usage_description=ctx.text(1761),
        cost={'amount': '10', 'unit': 'gp'}), [ctx.reference(1761)])
    groups = {
        'm2-armor': ('armor_class', [1616, 1617, 1620, 1621, 1622, 1624, 1629, 1638]),
        'm2-attack': ('attack', [1665, 1671, 1674, 1876, 1877, 1878, 2355, 2359, 2360,
                               2363, 2365, 2368, 2369, 2381, 2383, 2386]),
        'm2-damage': ('damage', [2417, 2418, 2420, 2421, 2424, 2427, 2428, 2430,
                               *range(2432,2445), 2447, 2448, 2449, 2455, 2459, 2462, 2467,
                               2474, 2475, 2480, 2481, 2483, 8026, 6521]),
    }
    for slug, (category, indices) in groups.items():
        refs = [ctx.reference(i) for i in indices]
        yield ctx.candidate('general_rule', slug, slug, dict(category=category,
            description='\n'.join(r.quote for r in refs),
            effect_specification=[dict(text=r.quote, source_ids=[r.id]) for r in refs]), refs)


def template_entries(root):
    return {r.id: {'record': r.model_dump(), 'content_sha256': digest_text(canonical(content(r))),
                   'sources': [s.model_dump() for s in refs]}
            for r, refs in candidates(root)}


def import_candidates(root, database=None):
    service = CatalogService(Path(root), database)
    imported = []
    for record, refs in candidates(root):
        saved = service.create_candidate(record, refs)
        # Preserve M1+ validation reports and review history on an idempotent import.
        # create_candidate already checks the exact content and current source integrity.
        if saved.validation_status == 'extracted':
            service.validate_candidate(record.id)
        imported.append(record.id)
    return {'records': imported, 'policy': 'validated candidates only; no review, publication or execution grants'}
