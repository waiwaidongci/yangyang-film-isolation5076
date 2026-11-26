from fastapi import APIRouter, Header, Query

from src.controllers.dependencies import Actor, Admin, Db, Writer
from src.controllers.report import report_csv, report_detail
from src.schemas.reviews import ReviewCreate, ReviewInfo
from src.schemas.runs import RunCreate, RunInfo
from src.services import reviews, runs
from src.services.runs import recompute_run as recompute_run_service

router = APIRouter(prefix='/runs')


@router.get('', response_model=list[RunInfo])
def list_all(session: Db, actor: Actor):
    return runs.list_runs(session, actor)


@router.post('', response_model=RunInfo, status_code=201)
def create(payload: RunCreate, session: Db, actor: Writer):
    return runs.create_run(session, payload, actor)


@router.get('/{run_id}')
def detail(run_id: int, session: Db, actor: Actor):
    return report_detail(session, run_id, actor)


@router.post('/{run_id}/review', response_model=ReviewInfo, status_code=201)
def review(
    run_id: int,
    payload: ReviewCreate,
    session: Db,
    actor: Admin,
    if_match: str | None = Header(default=None),
    x_basis_digest: str | None = Header(default=None),
    x_basis_version: int | None = Header(default=None),
    expected_version_query: int | None = Query(default=None, alias='expected_version'),
    version_query: int | None = Query(default=None, alias='version'),
    basis_digest_query: str | None = Query(default=None, alias='basis_digest'),
):
    # 除 JSON 字段外，也兼容用乐观锁头/查询参数携带所见版本或摘要的脚本。
    header_digest = x_basis_digest
    if not header_digest:
        if_match_value = _parse_if_match(if_match)
        if if_match_value and if_match_value.isdigit():
            x_basis_version = x_basis_version or int(if_match_value)
        else:
            header_digest = if_match_value
    if header_digest and not (payload.basis_digest or payload.expected_basis_digest):
        payload.basis_digest = header_digest
    if basis_digest_query and not (payload.basis_digest or payload.expected_basis_digest):
        payload.basis_digest = basis_digest_query
    query_version = expected_version_query or version_query or x_basis_version
    if query_version and payload.source_version is None:
        payload.source_version = query_version
    return reviews.submit(session, run_id, payload, actor)


def _parse_if_match(value):
    if not value:
        return None
    value = value.strip()
    if value == '*':
        return None
    if value.startswith('W/'):
        value = value[2:].strip()
    return value.strip('"') or None


@router.post('/{run_id}/sign', response_model=ReviewInfo, status_code=201)
def sign(run_id: int, payload: ReviewCreate, session: Db, actor: Admin,
         if_match: str | None = Header(default=None),
         x_basis_digest: str | None = Header(default=None),
         x_basis_version: int | None = Header(default=None)):
    return review(run_id, payload, session, actor, if_match, x_basis_digest,
                  x_basis_version, None, None, None)


@router.post('/{run_id}/recompute', response_model=RunInfo)
def recompute(run_id: int, session: Db, actor: Writer):
    from fastapi import HTTPException

    from src.models.review import Review
    from src.models.run import Run
    from src.services.concurrency import workflow_lock

    with workflow_lock:
        run = session.get(Run, run_id)
        if run is None:
            raise LookupError('找不到运行')
        if session.get(Review, run_id) is not None:
            raise HTTPException(409, '已签核运行保留原依据，不能原地重算；请新建运行')
        recompute_run_service(session, run)
        session.commit()
        review_obj = session.get(Review, run_id)
    return runs.run_info(run, review_obj)


@router.post('/{run_id}/recalculate', response_model=RunInfo)
def recalculate(run_id: int, session: Db, actor: Writer):
    return recompute(run_id, session, actor)


@router.get('/{run_id}/export/{key}')
def export(run_id: int, key: str, session: Db, actor: Actor):
    return report_csv(session, run_id, key, actor)
