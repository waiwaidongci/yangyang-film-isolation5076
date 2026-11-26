from fastapi import APIRouter
from pydantic import Field

from src.controllers.dependencies import Db, Writer
from src.schemas.datasets import CalibrationSupplementCreate
from src.services.supplements import supplement_calibration


class CalibrationSupplementRequest(CalibrationSupplementCreate):
    dataset_id: int | None = Field(default=None, gt=0)
    base_id: int | None = Field(default=None, gt=0)


router = APIRouter()


def _submit(payload: CalibrationSupplementRequest, session, actor):
    dataset_id = payload.dataset_id or payload.base_id
    if dataset_id is None:
        raise ValueError('请提供 dataset_id')
    return supplement_calibration(session, dataset_id, payload, actor)


@router.post('/calibration', status_code=200)
def create_calibration_alias(payload: CalibrationSupplementRequest, session: Db, actor: Writer):
    return _submit(payload, session, actor)


@router.post('/calibrations', status_code=200)
def create_calibrations_alias(payload: CalibrationSupplementRequest, session: Db, actor: Writer):
    return _submit(payload, session, actor)


@router.post('/calibration-records', status_code=200)
def create_calibration_record_alias(payload: CalibrationSupplementRequest, session: Db, actor: Writer):
    return _submit(payload, session, actor)


@router.post('/calibration-supplements', status_code=200)
def create_calibration_supplement(payload: CalibrationSupplementRequest, session: Db, actor: Writer):
    return _submit(payload, session, actor)


@router.post('/datasets/supplement', status_code=200)
def supplement_dataset(payload: CalibrationSupplementRequest, session: Db, actor: Writer):
    return _submit(payload, session, actor)


@router.post('/supplements/calibration', status_code=200)
def supplement_calibration_alias(payload: CalibrationSupplementRequest, session: Db, actor: Writer):
    return _submit(payload, session, actor)


@router.post('/calibrations/supplement', status_code=200)
def calibrations_supplement(payload: CalibrationSupplementRequest, session: Db, actor: Writer):
    return _submit(payload, session, actor)
