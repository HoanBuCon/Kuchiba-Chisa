"""Per-page silver check ledger and last-known-good pointer (ING-006)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.models.base import Base


class WikiPageSilverModel(Base):
    __tablename__ = "wiki_page_silver"
    __table_args__ = (
        CheckConstraint(
            "verdict IN ('accept', 'empty_after_clean', 'quarantine', 'hold')", name="verdict"
        ),
    )

    page_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    silver_path: Mapped[str] = mapped_column(String(256), nullable=False)
    output_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    verdict: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    reasons: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    unchanged_runs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    lkg_path: Mapped[str | None] = mapped_column(String(256), nullable=True)
