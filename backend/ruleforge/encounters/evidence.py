"""Offline candidates from the existing SHA-pinned xParse output (no parsing/API)."""
from pathlib import Path
from ruleforge.ingestion.pipeline import ExtractionContext
from ruleforge.ingestion.m2 import RAW_SHA256, PDF_SHA256
from ruleforge.ingestion.evidence import EvidenceError, digest_text
from ruleforge.catalog.service import canonical, content, CatalogService

TURN = 'srd51.general_rule.m3-turns'
READY = 'srd51.general_rule.m3-ready'


def candidates(root):
    ctx = ExtractionContext(root, 'srd51-full-001')
    if ctx.manifest['raw']['sha256'] != RAW_SHA256 or ctx.manifest['document']['sha256'] != PDF_SHA256:
        raise EvidenceError('M3 requires pinned SRD 5.1 artifacts')
    for slug, indices in [('m3-turns', [2230, 2231, 2232, 2234, 2237, 2239, 2240, 2252, 2253,
                                       2256, 2257, 2259, 2267, 2268, 2301, 2302, 2324]),
                           ('m3-ready', [2252, 2253, 2341, 2342, 2343])]:
        refs = [ctx.reference(i) for i in indices]
        yield ctx.candidate('general_rule', slug, slug, dict(category='action_economy',
            description='\n'.join(r.quote for r in refs),
            effect_specification=[dict(text=r.quote, source_ids=[r.id]) for r in refs]), refs)


def template_entries(root):
    return {r.id: dict(record=r.model_dump(), content_sha256=digest_text(canonical(content(r))),
                      sources=[s.model_dump() for s in refs]) for r, refs in candidates(root)}


def import_candidates(root, database):
    catalog = CatalogService(Path(root), Path(database))
    for record, refs in candidates(root):
        saved = catalog.create_candidate(record, refs)
        if saved.validation_status == 'extracted':
            catalog.validate_candidate(record.id)
    return catalog
