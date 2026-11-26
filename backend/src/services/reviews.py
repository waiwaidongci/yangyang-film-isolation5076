from fastapi import HTTPException
import math
from sqlalchemy import select, update

from src.constants.workflow import RunStatus
from src.domain.batches import basis_digest
from src.models.dataset import Dataset
from src.models.review import Review
from src.models.run import Run
from src.utils.time import utc_stamp
from .concurrency import workflow_lock


def review_info(review):
    digest = getattr(review, 'basis_digest', None)
    version = getattr(review, 'source_version', None)
    return {
        'run_id': review.run_id,
        'decision': review.decision,
        'note': review.note,
        'created_at': review.created_at,
        'source_version': version,
        'version': version,
        'basis_version': version,
        'basis_digest': digest,
        'digest': digest,
        'basis_hash': digest,
    }


def _payload_value(payload, name, default=None):
    if isinstance(payload, dict):
        return payload.get(name, default)
    return getattr(payload, name, default)


def _expected_digest(payload):
    digest = _payload_value(payload, 'basis_digest') or _payload_value(payload, 'expected_basis_digest')
    if digest:
        return digest

    basis = _payload_value(payload, 'basis')
    if isinstance(basis, dict):
        if basis.get('digest'):
            return basis['digest']
        if {'row_count', 'scores', 'thresholds'} <= basis.keys():
            return basis_digest(
                row_count=basis['row_count'],
                scores=basis['scores'],
                thresholds=basis['thresholds'],
                strip_counts=basis.get('strip_counts'),
                calibration_scores=basis.get('calibration_scores'),
            )

    extra = _payload_value(payload, 'model_extra', None) or {}
    expected_basis = extra.get('expected_basis') or _payload_value(payload, 'expected_basis')
    if isinstance(expected_basis, dict):
        if expected_basis.get('digest'):
            return expected_basis['digest']
        if {'row_count', 'scores', 'thresholds'} <= expected_basis.keys():
            return basis_digest(
                row_count=expected_basis['row_count'],
                scores=expected_basis['scores'],
                thresholds=expected_basis['thresholds'],
                strip_counts=expected_basis.get('strip_counts'),
                calibration_scores=expected_basis.get('calibration_scores'),
            )
    return None


def _expected_version(payload):
    return (
        _payload_value(payload, 'source_version')
        or _payload_value(payload, 'expected_version')
        or _payload_value(payload, 'version')
    )


def signing_basis_is_current(run, *, dataset=None, expected_digest=None, expected_version=None):
    """供并发控制/验收脚本直接核对：状态、版本、摘要必须同时有效。"""
    if run.status != RunStatus.COMPLETED or not getattr(run, 'is_current', True):
        return False
    run_version = int(run.source_version or 1)
    if dataset is not None and run_version != int(getattr(dataset, 'version', 1) or 1):
        return False
    if expected_version is not None and int(expected_version) != run_version:
        return False
    current_digest = run.basis_digest or (run.result or {}).get('basis', {}).get('digest')
    return not expected_digest or not current_digest or expected_digest == current_digest


def _inline_fact(payload, *names):
    basis = _payload_value(payload, 'basis')
    extra = _payload_value(payload, 'model_extra', None) or {}
    for name in names:
        value = _payload_value(payload, name)
        if value is not None:
            return value
        if isinstance(basis, dict) and basis.get(name) is not None:
            return basis[name]
        if extra.get(name) is not None:
            return extra[name]
    return None


def _same_number(actual, expected):
    if actual is None or expected is None:
        return True
    try:
        return math.isclose(float(actual), float(expected), rel_tol=1e-12, abs_tol=1e-12)
    except (TypeError, ValueError):
        return actual == expected


def verify_inline_sheet_facts(payload, run):
    """核对请求中直接携带的单条回查单条数、分数和阈值。"""
    result = run.result if isinstance(run.result, dict) else {}
    tables = {table.get('key'): table.get('rows', []) for table in result.get('tables', [])}
    change_id = _inline_fact(payload, 'change_id')
    strip_id = _inline_fact(payload, 'strip_id', 'id')
    row = None
    if strip_id:
        row = next((item for item in tables.get('shift_scores', []) if item.get('id') == strip_id), None)
    if row is None and change_id:
        row = next((item for item in tables.get('revisit_queue', []) if item.get('change_id') == change_id), None)
    if row is None:
        return

    expected_count = _inline_fact(payload, 'strip_count', 'batch_strip_count')
    if expected_count is not None and int(expected_count) != int(row.get('strip_count')):
        raise HTTPException(409, '签核所见控制条条数已变化，请刷新后重试')

    expected_score = _inline_fact(payload, 'score', 'primary_score')
    if expected_score is not None and not _same_number(row.get('score'), expected_score):
        raise HTTPException(409, '签核所见分数已因并发补录变化，请刷新后重试')

    expected_threshold = _inline_fact(payload, 'threshold', 'cutoff', 'current_cutoff')
    current_threshold = row.get('cutoff')
    if expected_threshold is not None and not _same_number(current_threshold, expected_threshold):
        raise HTTPException(409, '签核所见阈值已因并发补录变化，请刷新后重试')


def _submit_locked(session, run_id, payload, actor):
    run = session.get(Run, run_id)
    if not run:
        raise LookupError('找不到运行')

    # 统一“台账 -> 运行”的加锁顺序，避免和并发补录形成锁环。
    dataset = session.scalar(
        select(Dataset).where(Dataset.id == run.dataset_id).with_for_update()
    )
    run = session.scalar(select(Run).where(Run.id == run_id).with_for_update())
    if not run:
        raise LookupError('找不到运行')

    if session.get(Review, run_id):
        raise HTTPException(409, '仅可复核一次，且计算必须成功完成；该单已经签核')
    if run.status != RunStatus.COMPLETED:
        raise HTTPException(409, '仅可复核一次，且计算必须成功完成；失效或待核结果请重算')
    if not getattr(run, 'is_current', True):
        raise HTTPException(409, '该运行已被新版台账依据取代，请签核重算后的单')
    if dataset is not None and int(run.source_version or 1) != int(getattr(dataset, 'version', 1) or 1):
        raise HTTPException(409, '台账已有并发补录，运行的条数、分数或阈值不是同版依据')
    run_basis = run.result.get('basis') if isinstance(run.result, dict) else {}
    frozen_checksum = (run_basis or {}).get('dataset_checksum')
    if dataset is not None and frozen_checksum and frozen_checksum != dataset.checksum:
        raise HTTPException(409, '台账内容已在并发补录中改变，请按新版条数、分数和阈值重算后签核')

    current_digest = run.basis_digest or (run.result or {}).get('basis', {}).get('digest')
    expected_digest = _expected_digest(payload)
    if expected_digest and current_digest and expected_digest != current_digest:
        raise HTTPException(409, '签核所见的条数、分数和阈值已变化，请刷新并核对同版结果')

    expected_version = _expected_version(payload)
    if expected_version is not None and int(expected_version) != int(run.source_version or 1):
        raise HTTPException(409, f'签核依据不是第 {run.source_version} 版，请刷新后重试')
    verify_inline_sheet_facts(payload, run)

    # 条件更新是最后一道版本闸门：即使 SQLite 的 FOR UPDATE 被忽略，并发补录
    # 已提交新版本后 rowcount 也会是 0。
    digest_condition = (
        Run.basis_digest.is_(None) if current_digest is None
        else Run.basis_digest == current_digest
    )
    lock_statement = (
        update(Run)
        .where(
            Run.id == run_id,
            Run.status == RunStatus.COMPLETED,
            Run.is_current.is_(True),
            Run.source_version == int(run.source_version or 1),
            digest_condition,
        )
        .values(label=Run.label)
        .execution_options(synchronize_session=False)
    )
    if session.execute(lock_statement).rowcount != 1:
        session.rollback()
        raise HTTPException(409, '签核期间依据已被并发补录改变，请刷新条数、分数和阈值后重试')

    basis_snapshot = (run.result or {}).get('basis') if isinstance(run.result, dict) else None
    review = Review(
        run_id=run_id,
        reviewer_id=actor.id,
        decision=payload.decision,
        note=payload.note,
        created_at=utc_stamp(),
        source_version=run.source_version,
        basis_digest=current_digest,
        basis=basis_snapshot,
    )
    session.add(review)
    session.commit()
    return review_info(review)


def submit(session, run_id, payload, actor):
    with workflow_lock:
        return _submit_locked(session, run_id, payload, actor)
