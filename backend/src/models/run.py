from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.config.database import Base


class Run(Base):
    __tablename__ = 'analysis_runs'

    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String(140))
    dataset_id: Mapped[int] = mapped_column(ForeignKey('datasets.id'), index=True)
    created_by: Mapped[int] = mapped_column(ForeignKey('accounts.id'))
    created_at: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), index=True)
    settings: Mapped[dict] = mapped_column(JSON)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text)
    source_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False, server_default='1')
    basis_digest: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, server_default='1')
    superseded_by_id: Mapped[int | None] = mapped_column(ForeignKey('analysis_runs.id'), nullable=True)

    @property
    def version(self) -> int:
        return int(self.source_version or 1)

    @version.setter
    def version(self, value: int) -> None:
        self.source_version = int(value)

    @property
    def digest(self) -> str | None:
        return self.basis_digest
