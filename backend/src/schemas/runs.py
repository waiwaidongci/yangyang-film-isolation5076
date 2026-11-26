from pydantic import BaseModel, ConfigDict, Field

from src.constants.workflow import RunStatus


class RunCreate(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    label: str = Field(min_length=2, max_length=140)
    dataset_id: int = Field(gt=0)
    settings: dict[str, float] = Field(default_factory=dict, max_length=20)


class RunInfo(BaseModel):
    id: int
    label: str
    dataset_id: int
    created_at: str
    status: RunStatus
    settings: dict
    decision: str | None
    source_version: int | None = 1
    version: int | None = 1
    basis_version: int | None = 1
    basis_digest: str | None = None
    digest: str | None = None
    basis_hash: str | None = None
    fingerprint: str | None = None
    is_current: bool | None = True
    verification_status: str | None = None
    superseded: bool | None = False
    superseded_by_id: int | None = None
