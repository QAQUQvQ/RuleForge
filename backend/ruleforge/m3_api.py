"""Single-DM local API. Actor IDs select game actors; they are not credentials."""
import hmac
import os
from fastapi import APIRouter, Depends, Header
from ruleforge.catalog.service import CatalogService
from ruleforge.domain.models import Command, EndEncounterCommand
from ruleforge.encounters.contracts import CreateEncounter
from ruleforge.encounters.service import Encounters
from ruleforge.combat.errors import RuleError


def install(app, root, database, *, isolated_demo=False):
    service = Encounters(CatalogService(root, database), isolated_demo=isolated_demo)
    router = APIRouter(prefix='/api/encounters')

    def dm(x_ruleforge_admin: str | None = Header(default=None)):
        token = os.environ.get('RULEFORGE_ADMIN_TOKEN')
        if not token or not x_ruleforge_admin or not hmac.compare_digest(token, x_ruleforge_admin):
            raise RuleError('dm_required', 'Encounter writes require the configured local DM token', 403)

    @router.get('')
    def listing():
        with service.transaction() as (conn, _):
            return {'environment': service.mode, 'encounters': [dict(row) for row in conn.execute(
                'SELECT id,version FROM encounters WHERE initial_json IS NOT NULL ORDER BY rowid DESC')]}

    @router.get('/participants')
    def participants():
        with service.transaction() as (conn, _):
            return [dict(row) for row in conn.execute(
                "SELECT id,version,json_extract(state_json,'$.name') name FROM characters ORDER BY id")]

    @router.post('', dependencies=[Depends(dm)], status_code=201)
    def create(request: CreateEncounter):
        return service.create(request)

    @router.get('/{encounter_id}')
    @router.get('/{encounter_id}/state')
    def state(encounter_id: str):
        return service.get(encounter_id)

    @router.post('/{encounter_id}/commands', dependencies=[Depends(dm)])
    def execute(encounter_id: str, command: Command):
        if command.encounter_id != encounter_id:
            raise RuleError('encounter_mismatch', 'Path and command encounter ID differ')
        return service.execute(command)

    @router.get('/{encounter_id}/events')
    def events(encounter_id: str):
        return service.replay(encounter_id)['events']

    @router.get('/{encounter_id}/replay')
    def replay(encounter_id: str):
        return service.replay(encounter_id)

    @router.post('/{encounter_id}/end', dependencies=[Depends(dm)])
    def end(encounter_id: str, command: EndEncounterCommand):
        return execute(encounter_id, command)

    app.include_router(router)
