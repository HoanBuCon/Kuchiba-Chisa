"""Wiki inventory (ING-013) and sync-run log; supersedes the legacy wiki_sync_state table."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.models.base import Base


class WikiPageModel(Base):
    __tablename__ = "wiki_pages"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'pending_delete', 'deleted')", name="status"),
    )

    page_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    last_revid: Mapped[int] = mapped_column(BigInteger, nullable=False)
    touched: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    family: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    tier: Mapped[str | None] = mapped_column(String(8), nullable=True)
    templates: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    fetched_revid: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    fetched_touched: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    bronze_key: Mapped[str | None] = mapped_column(String(256), nullable=True)
    aliases: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)


class WikiSyncRunModel(Base):
    __tablename__ = "wiki_sync_runs"

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    stats: Mapped[dict[str, int]] = mapped_column(JSONB, nullable=False, default=dict)
