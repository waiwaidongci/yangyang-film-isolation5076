from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.config.database import Base
from src.utils.time import utc_stamp


class Dataset(Base):
    __tablename__ = 'datasets'

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(140), unique=True)
    checksum: Mapped[str] = mapped_column(String(64))
    rows: Mapped[list] = mapped_column(JSON)
    created_by: Mapped[int] = mapped_column(ForeignKey('accounts.id'))
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False, server_default='1')
    updated_at: Mapped[str | None] = mapped_column(String(32), nullable=True)


class CalibrationSupplement(Base):
    """晚到校准记录的录入存根；合并后的全量行仍保存在 Dataset.rows。"""

    __tablename__ = 'calibration_supplements'

    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey('datasets.id'), index=True)
    change_id: Mapped[str] = mapped_column(String(48), index=True)
    filename: Mapped[str | None] = mapped_column(String(240), nullable=True)
    checksum: Mapped[str] = mapped_column(String(64))
    added_rows: Mapped[list] = mapped_column(JSON)
    created_by: Mapped[int] = mapped_column(ForeignKey('accounts.id'))
    created_at: Mapped[str] = mapped_column(String(32), default=utc_stamp)
    dataset_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
