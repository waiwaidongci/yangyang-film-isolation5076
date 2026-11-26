import hashlib
import json

from fastapi import HTTPException
from sqlalchemy import select

from src.domain.inputs import COLUMNS
from src.domain.supplements import merge_late_calibration
from src.models.dataset import CalibrationSupplement, Dataset
from src.models.review import Review
from src.models.run import Run
from src.services.runs import recompute_run
from src.utils.csv_files import read_rows
from src.utils.time import utc_stamp
from .concurrency import workflow_lock


def _locked_dataset(session, dataset_id):
    dataset = session.scalar(
        select(Dataset).where(Dataset.id == dataset_id).with_for_update()
    )
    if dataset is None:
        raise LookupError('找不到来源台账')
    return dataset


def _payload_value(payload, name, default=None):
    if isinstance(payload, dict):
        return payload.get(name, default)
    return getattr(payload, name, default)


def _parse_additions(payload):
    csv_text = _payload_value(payload, 'csv')
    if csv_text:
        return read_rows(csv_text, COLUMNS), _payload_value(payload, 'filename') or 'late-calibration.csv'
    records = _payload_value(payload, 'rows')
    if records is None:
        records = _payload_value(payload, 'records')
    if records:
        return [dict(row) for row in records], _payload_value(payload, 'filename')
    raise ValueError('请提供晚到校准记录的 csv 或 rows/records')


def invalidate_unsigned_runs(session, dataset_id):
    """把未签核运行标记为失效；已签核运行不动，保留原依据。"""
    runs = list(session.scalars(
        select(Run).where(Run.dataset_id == dataset_id).with_for_update()
    ))
    stale_ids = []
    for run in runs:
        if session.get(Review, run.id) is not None:
            continue
        run.status = 'stale'
        run.is_current = False
        stale_ids.append(run.id)
    return stale_ids


def _supplement_locked(session, dataset_id, payload, actor):
    dataset = _locked_dataset(session, dataset_id)
    old_version = int(getattr(dataset, 'version', 1) or 1)
    expected_version = _payload_value(payload, 'expected_version')
    if expected_version is not None and int(expected_version) != old_version:
        raise HTTPException(409, f'台账已是第 {old_version} 版，请刷新后再补录')

    additions, filename = _parse_additions(payload)
    requested_change_id = _payload_value(payload, 'change_id')
    if requested_change_id:
        for row in additions:
            row.setdefault('change_id', requested_change_id)
            if row.get('change_id') != requested_change_id:
                raise ValueError('补录记录的换槽批次与 change_id 不一致')

    # 行锁已经串行化同一台账的并发补录；合并时仍做编号和原批校验。
    merged = merge_late_calibration(dataset.rows, additions)
    encoded = json.dumps(merged, ensure_ascii=False, sort_keys=True, allow_nan=False).encode()
    additions_encoded = json.dumps(additions, ensure_ascii=False, sort_keys=True, allow_nan=False).encode()

    dataset.rows = merged
    dataset.checksum = hashlib.sha256(encoded).hexdigest()
    dataset.version = old_version + 1
    dataset.updated_at = utc_stamp()

    change_ids = sorted({row['change_id'] for row in additions})
    stub = CalibrationSupplement(
        dataset_id=dataset.id,
        change_id=requested_change_id or (change_ids[0] if len(change_ids) == 1 else ''),
        filename=filename,
        checksum=hashlib.sha256(additions_encoded).hexdigest(),
        added_rows=additions,
        created_by=actor.id,
        created_at=utc_stamp(),
        dataset_version=dataset.version,
        note=_payload_value(payload, 'note'),
    )
    session.add(stub)

    runs = list(session.scalars(
        select(Run).where(Run.dataset_id == dataset.id).order_by(Run.id).with_for_update()
    ))
    recomputed_run_ids = []
    reviewed_run_ids = []
    for run in runs:
        review = session.get(Review, run.id)
        if review is not None:
            # 结果和签核依据原样保留；仅标识它已不是台账最新版的计算。
            run.is_current = False
            reviewed_run_ids.append(run.id)
            continue
        recompute_run(session, run, dataset)
        recomputed_run_ids.append(run.id)

    session.commit()
    return {
        'id': dataset.id,
        'name': dataset.name,
        'checksum': dataset.checksum,
        'count': len(dataset.rows),
        'version': dataset.version,
        'previous_version': old_version,
        'added_count': len(additions),
        'supplement_id': stub.id,
        'recomputed_run_ids': recomputed_run_ids,
        'reviewed_run_ids': reviewed_run_ids,
    }


def supplement_calibration(session, dataset_id, payload, actor):
    with workflow_lock:
        return _supplement_locked(session, dataset_id, payload, actor)
