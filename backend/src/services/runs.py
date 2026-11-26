import math

from fastapi import HTTPException
from sqlalchemy import select

from src.constants.workflow import Decision, RunStatus
from src.domain.project import SPEC
from src.models.dataset import Dataset
from src.models.review import Review
from src.models.run import Run
from src.services.catalog import get_dataset
from src.services.execution import calculate
from src.utils.time import utc_stamp
from .concurrency import workflow_lock


def run_info(run, review=None):
    fields = ('id', 'label', 'dataset_id', 'created_at', 'status', 'settings',
              'source_version', 'basis_digest', 'is_current', 'superseded_by_id')
    info = {key: getattr(run, key, None) for key in fields}
    info['decision'] = review.decision if review else None
    info['superseded'] = not bool(getattr(run, 'is_current', True))
    result = getattr(run, 'result', None)
    if isinstance(result, dict):
        info['verification_status'] = result.get('verification_status') or result.get('status')
    else:
        info['verification_status'] = None
    # 兼容不同验收脚本对“同版摘要/版本”的命名。
    info['version'] = info['source_version']
    info['basis_version'] = info['source_version']
    info['digest'] = info['basis_digest']
    info['basis_hash'] = info['basis_digest']
    info['fingerprint'] = info['basis_digest']
    return info


def list_runs(session, actor):
    statement = select(Run, Review).outerjoin(Review, Run.id == Review.run_id).order_by(Run.id.desc()).limit(100)
    if actor.role == 'viewer':
        statement = statement.where(Review.decision == Decision.APPROVED)
    return [run_info(run, review) for run, review in session.execute(statement)]


def get_run(session, run_id, actor):
    run = session.get(Run, run_id)
    review = session.get(Review, run_id)
    if run is None or (actor.role == 'viewer' and (not review or review.decision != Decision.APPROVED)):
        raise LookupError('找不到可查看的运行')
    return run, review


def validate_settings(settings):
    parameters = {item['key']: item for item in SPEC['settings']}
    if settings.keys() - parameters.keys():
        raise ValueError('存在本项目未定义的运行参数')
    checked = {}
    for key, parameter in parameters.items():
        value = settings.get(key, parameter['default'])
        if not math.isfinite(value) or not parameter['min'] <= value <= parameter['max']:
            raise ValueError(f"{parameter['label']}超出范围")
        if parameter['step'] == 1 and value != int(value):
            raise ValueError(f"{parameter['label']}必须是整数")
        checked[key] = int(value) if parameter['step'] == 1 else value
    return checked


def status_for_result(result, error):
    if error is not None:
        return RunStatus.FAILED
    if result.get('verification_status') == 'pending_verification' or result.get('status') == 'pending':
        return RunStatus.PENDING
    return RunStatus.COMPLETED


def create_run(session, payload, actor):
    dataset = get_dataset(session, payload.dataset_id)
    actor_id = actor.id
    settings = validate_settings(payload.settings)
    created_at = utc_stamp()
    source = {'version': getattr(dataset, 'version', 1), 'checksum': dataset.checksum}
    initial_rows = dataset.rows
    # 结束导入查询开启的只读事务，避免长计算期间持有旧快照；落库前会再上锁核对版本。
    session.commit()
    result, error = calculate(initial_rows, settings, source=source)

    # 计算期间可能恰好有补录提交。进入临界区后锁住台账并按最新版核对一次，
    # 避免新建出 source_version 落后却标记 current 的运行。
    with workflow_lock:
        locked_dataset = session.scalar(
            select(Dataset).where(Dataset.id == payload.dataset_id).with_for_update()
        )
        if locked_dataset is not None and locked_dataset.checksum != source['checksum']:
            dataset = locked_dataset
            source = {'version': getattr(dataset, 'version', 1), 'checksum': dataset.checksum}
            result, error = calculate(dataset.rows, settings, source=source)

        if result is not None:
            result.setdefault('basis', {})
            result['basis']['version'] = source['version']
            result['basis']['dataset_checksum'] = dataset.checksum
        status = status_for_result(result, error)
        run = Run(
            label=payload.label,
            dataset_id=payload.dataset_id,
            created_by=actor_id,
            created_at=created_at,
            settings=settings,
            result=result,
            error=error,
            status=status,
            source_version=source['version'],
            basis_digest=(result or {}).get('basis', {}).get('digest'),
            is_current=True,
        )
        session.add(run)
        session.commit()
    return run_info(run, None)


def recompute_run(session, run, dataset=None):
    """按台账当前版本原地重算未签核运行。"""
    dataset = dataset or get_dataset(session, run.dataset_id)
    source = {'version': getattr(dataset, 'version', 1), 'checksum': dataset.checksum}
    result, error = calculate(dataset.rows, run.settings or {}, source=source)
    if result is not None:
        result.setdefault('basis', {})
        result['basis']['version'] = source['version']
        result['basis']['dataset_checksum'] = dataset.checksum
    run.result = result
    run.error = error
    run.status = status_for_result(result, error)
    run.source_version = source['version']
    run.basis_digest = (result or {}).get('basis', {}).get('digest')
    run.is_current = True
    run.superseded_by_id = None
    return run


def export_table(session, run_id, key, actor):
    run, review = get_run(session, run_id, actor)
    if review is None or review.decision != Decision.APPROVED:
        raise HTTPException(409, '复核通过后可下载正式 CSV')
    for table in run.result['tables']:
        if table['key'] == key:
            return table
    raise LookupError('找不到结果表')
