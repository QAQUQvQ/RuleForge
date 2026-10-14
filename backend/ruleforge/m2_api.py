import hmac
import os
from fastapi import APIRouter, Header, Depends, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from ruleforge.catalog.service import CatalogService
from ruleforge.combat.characters import Characters, CreateCharacter, PatchCharacter
from ruleforge.combat.service import PreviewRequest, ResolutionPreview, preview
from ruleforge.combat.errors import RuleError
from ruleforge.combat.ac import EquipmentACRequest, equipment_ac
from ruleforge.ingestion.evidence import EvidenceError, evidence_snapshot


def install(app, root, database):
    catalog=CatalogService(root,database)
    characters=Characters(catalog)
    router=APIRouter(prefix='/api')

    @app.exception_handler(RuleError)
    async def rule_error(_request,exc):
        return JSONResponse(status_code=exc.status,content={'error':{'code':exc.code,'message':str(exc)}})

    @app.exception_handler(EvidenceError)
    async def evidence_error(_request,exc):
        return JSONResponse(status_code=409,content={'error':{'code':'source_integrity_failed','message':str(exc)}})

    @app.exception_handler(FileNotFoundError)
    async def missing_evidence(_request,exc):
        return JSONResponse(status_code=409,content={'error':{'code':'source_integrity_failed','message':'Required evidence file is unavailable'}})

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request,exc):
        # Preserve legacy FastAPI validation shape for the original endpoint.
        from fastapi.exception_handlers import request_validation_exception_handler
        if request.url.path=='/api/evaluate/ac':
            return await request_validation_exception_handler(request,exc)
        return JSONResponse(status_code=422,content={'error':{'code':'invalid_input','message':str(exc)}})

    def admin(x_ruleforge_admin: str | None=Header(default=None)):
        token=os.environ.get('RULEFORGE_ADMIN_TOKEN')
        if not token or not x_ruleforge_admin or not hmac.compare_digest(token,x_ruleforge_admin):
            raise RuleError('admin_required','Candidate view requires configured local admin token',403)

    def search_records(q,record_type,limit,offset,published):
        try:
            return catalog.search(q,record_type,published_only=published,limit=limit,offset=offset)
        except ValueError as exc:
            if isinstance(exc,(EvidenceError,RuleError)):
                raise
            raise RuleError('invalid_input',str(exc)) from exc

    @router.get('/catalog')
    @router.get('/search')
    def search(q: str='',record_type: str | None=None,limit: int=50,offset: int=0):
        return search_records(q,record_type,limit,offset,True)

    @router.get('/admin/catalog',dependencies=[Depends(admin)])
    def admin_catalog(q: str='',record_type: str | None=None,limit: int=50,offset: int=0):
        return search_records(q,record_type,limit,offset,False)

    def detail(record_id,version,published):
        try:
            with evidence_snapshot():
                record=catalog.get_record(record_id,version,published_only=published)
                return {'record':record.model_dump(),'sources':catalog.sources(record_id,version,published_only=published),
                        'execution_permission':'requires_independent_runtime_verification'}
        except KeyError as exc:
            raise RuleError('not_found','Record/version not found',404) from exc
        except EvidenceError as exc:
            if str(exc)=='record is not published':
                raise RuleError('not_found','Published record/version not found',404) from exc
            raise

    @router.get('/catalog/{record_id}')
    def get_record(record_id: str,version: int=1):
        return detail(record_id,version,True)

    @router.get('/catalog/{record_id}/sources')
    def get_sources(record_id: str,version: int=1):
        return detail(record_id,version,True)['sources']

    @router.get('/admin/catalog/{record_id}',dependencies=[Depends(admin)])
    def admin_detail(record_id: str,version: int=1):
        return detail(record_id,version,False)

    @router.post('/characters',status_code=201)
    def create(request: CreateCharacter):
        return characters.create(request)

    @router.get('/characters/{character_id}')
    def character(character_id: str):
        return characters.get(character_id)

    @router.patch('/characters/{character_id}')
    def patch(character_id: str,request: PatchCharacter):
        return characters.patch(character_id,request)

    @router.get('/characters/{character_id}/ac')
    def ac(character_id: str):
        return characters.ac(character_id)

    @router.post('/combat/preview',response_model=ResolutionPreview)
    def combat(request: PreviewRequest):
        return preview(characters,request)

    @router.post('/evaluate/equipment-ac')
    def generic_ac(request: EquipmentACRequest):
        return equipment_ac(characters,request)

    app.include_router(router)
