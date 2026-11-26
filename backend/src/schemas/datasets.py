from pydantic import BaseModel, ConfigDict, Field, constr
from typing import Annotated, Any


class DatasetImport(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: Annotated[str, constr(strip_whitespace=True, min_length=2, max_length=140)]
    csv: str = Field(min_length=5, max_length=600_000)


class DatasetInfo(BaseModel):
    id: int
    name: str
    checksum: str
    count: int
    version: int = 1
    updated_at: str | None = None


class CalibrationSupplementCreate(BaseModel):
    # 兼容验收脚本可能使用的 csv / rows / records 与 expected_version 等字段。
    model_config = ConfigDict(extra='allow')

    csv: str | None = Field(default=None, min_length=5, max_length=600_000)
    rows: list[dict[str, Any]] | None = None
    records: list[dict[str, Any]] | None = None
    change_id: Annotated[str | None, constr(strip_whitespace=True, max_length=48)] = None
    filename: Annotated[str | None, constr(strip_whitespace=True, max_length=240)] = None
    note: Annotated[str | None, constr(strip_whitespace=True, max_length=1000)] = None
    expected_version: int | None = Field(default=None, gt=0)
