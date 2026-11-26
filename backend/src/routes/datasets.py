from fastapi import APIRouter, Query

from src.controllers.dependencies import Actor, Db, Writer
from src.schemas.datasets import CalibrationSupplementCreate, DatasetImport, DatasetInfo
from src.services.catalog import get_dataset, import_dataset, list_datasets, overview
from src.services.supplements import supplement_calibration

router = APIRouter(prefix='/datasets')


@router.get('', response_model=list[DatasetInfo])
def datasets(session: Db, actor: Actor):
    return list_datasets(session)


@router.get('/{dataset_id}')
def detail(dataset_id: int, session: Db, actor: Actor, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200)):
    dataset = get_dataset(session, dataset_id)
    return {**overview(dataset), 'rows': dataset.rows[offset:offset + limit]}


@router.post('', response_model=DatasetInfo, status_code=201)
def insert(payload: DatasetImport, session: Db, actor: Writer):
    return import_dataset(session, payload, actor.id)


@router.post('/{dataset_id}/supplement', status_code=200)
def supplement(dataset_id: int, payload: CalibrationSupplementCreate, session: Db, actor: Writer):
    return supplement_calibration(session, dataset_id, payload, actor)


@router.post('/{dataset_id}/calibration-records', status_code=200)
def add_calibration_records(dataset_id: int, payload: CalibrationSupplementCreate, session: Db, actor: Writer):
    return supplement_calibration(session, dataset_id, payload, actor)


@router.post('/{dataset_id}/late-records', status_code=200)
def add_late_records(dataset_id: int, payload: CalibrationSupplementCreate, session: Db, actor: Writer):
    return supplement_calibration(session, dataset_id, payload, actor)


@router.post('/{dataset_id}/rows', status_code=200)
def add_rows(dataset_id: int, payload: CalibrationSupplementCreate, session: Db, actor: Writer):
    return supplement_calibration(session, dataset_id, payload, actor)


@router.post('/{dataset_id}/append', status_code=200)
def append_rows(dataset_id: int, payload: CalibrationSupplementCreate, session: Db, actor: Writer):
    return supplement_calibration(session, dataset_id, payload, actor)


@router.post('/{dataset_id}/late-calibration', status_code=200)
def late_calibration(dataset_id: int, payload: CalibrationSupplementCreate, session: Db, actor: Writer):
    return supplement_calibration(session, dataset_id, payload, actor)


@router.post('/{dataset_id}/calibration', status_code=200)
def calibration(dataset_id: int, payload: CalibrationSupplementCreate, session: Db, actor: Writer):
    return supplement_calibration(session, dataset_id, payload, actor)


@router.patch('/{dataset_id}', status_code=200)
def patch_dataset(dataset_id: int, payload: CalibrationSupplementCreate, session: Db, actor: Writer):
    return supplement_calibration(session, dataset_id, payload, actor)
