from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.config.database import Base


class Review(Base):
    __tablename__ = 'reviews'

    run_id: Mapped[int] = mapped_column(ForeignKey('analysis_runs.id'), primary_key=True)
    reviewer_id: Mapped[int] = mapped_column(ForeignKey('accounts.id'))
    decision: Mapped[str] = mapped_column(String(16))
    note: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(32))
    source_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    basis_digest: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    basis: Mapped[dict | None] = mapped_column(JSON, nullable=True)
