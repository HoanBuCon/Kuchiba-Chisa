"""Structured knowledge per corpus version (KNW-004); replaces the legacy entity tables."""

from __future__ import annotations

from sqlalchemy import BigInteger, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.models.base import Base

VERSION_LENGTH = 32


class KbEntityModel(Base):
    __tablename__ = "kb_entities"

    corpus_version: Mapped[str] = mapped_column(String(VERSION_LENGTH), primary_key=True)
    page_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fields: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False)
    nation: Mapped[str | None] = mapped_column(String(256), nullable=True)
    nation_source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    game_version: Mapped[str | None] = mapped_column(String(16), nullable=True)
    version_source: Mapped[str | None] = mapped_column(String(32), nullable=True)


class KbAliasModel(Base):
    __tablename__ = "kb_aliases"

    corpus_version: Mapped[str] = mapped_column(String(VERSION_LENGTH), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    alias: Mapped[str] = mapped_column(Text, nullable=False)
    target: Mapped[str] = mapped_column(String(512), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[str] = mapped_column(String(16), nullable=False)
    evidence: Mapped[list[str]] = mapped_column(JSONB, nullable=False)


class KbGlossaryModel(Base):
    __tablename__ = "kb_glossary"

    corpus_version: Mapped[str] = mapped_column(String(VERSION_LENGTH), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    term: Mapped[str] = mapped_column(Text, nullable=False)
    definition: Mapped[str] = mapped_column(Text, nullable=False)
    pages: Mapped[int] = mapped_column(Integer, nullable=False)
    variants: Mapped[list[str]] = mapped_column(JSONB, nullable=False)


class KbQuestModel(Base):
    __tablename__ = "kb_quests"

    corpus_version: Mapped[str] = mapped_column(String(VERSION_LENGTH), primary_key=True)
    page_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    fields: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    steps: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    narration: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    speakers: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    locations: Mapped[list[str]] = mapped_column(JSONB, nullable=False)


class KbLocationEdgeModel(Base):
    __tablename__ = "kb_location_edges"

    corpus_version: Mapped[str] = mapped_column(String(VERSION_LENGTH), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    child: Mapped[str] = mapped_column(String(512), nullable=False)
    parent: Mapped[str] = mapped_column(String(512), nullable=False)
    source: Mapped[str] = mapped_column(String(512), nullable=False)
