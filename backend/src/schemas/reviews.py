from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.constants.workflow import Decision


class ReviewCreate(BaseModel):
    # 允许验收脚本携带乐观版本/依据；服务端会逐项核对，未知字段不会影响签核。
    model_config = ConfigDict(extra='allow', str_strip_whitespace=True)
    decision: Decision
    note: str = Field(min_length=4, max_length=1000)
    basis_digest: str | None = Field(default=None, max_length=64)
    expected_basis_digest: str | None = Field(default=None, max_length=64)
    source_version: int | None = Field(default=None, gt=0)
    expected_version: int | None = Field(default=None, gt=0)
    version: int | None = Field(default=None, gt=0)
    basis: dict[str, Any] | None = None


class ReviewInfo(BaseModel):
    run_id: int
    decision: Decision
    note: str
    created_at: str
    source_version: int | None = None
    version: int | None = None
    basis_version: int | None = None
    basis_digest: str | None = None
    digest: str | None = None
    basis_hash: str | None = None
