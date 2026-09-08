"""Durable workers rehydrate only exact, principal-owned source records."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import delete

from app.infrastructure.background.job_handlers import (
    BackgroundTurnSourceReader,
    DurableJobPayloadError,
)
from app.infrastructure.database.engine import AsyncSessionFactory
from app.infrastructure.database.models.conversation import Conversation
from app.infrastructure.database.models.message import Message, MessageRole
from app.infrastructure.database.models.user import User


@pytest.mark.asyncio
async def test_source_reader_enforces_exact_principal_and_message_roles(
    isolated_postgres: None,
) -> None:
    del isolated_postgres
    user_id = uuid.uuid4()
    other_user_id = uuid.uuid4()
    conversation_id = uuid.uuid4()
    user_message_id = uuid.uuid4()
    assistant_message_id = uuid.uuid4()
    async with AsyncSessionFactory() as session:
        session.add_all(
            [
                User(id=user_id, username=f"be01-{user_id}", discord_id="trusted-external"),
                User(id=other_user_id, username=f"be01-{other_user_id}"),
                Conversation(id=conversation_id, user_id=user_id),
                Message(
                    id=user_message_id,
                    conversation_id=conversation_id,
                    user_id=user_id,
                    role=MessageRole.USER,
                    content="source user content",
                    media_metadata=[{"image_id": "image-1", "url": "approved-object-url"}],
                ),
                Message(
                    id=assistant_message_id,
                    conversation_id=conversation_id,
                    user_id=user_id,
                    role=MessageRole.ASSISTANT,
                    content="source assistant content",
                ),
            ]
        )
        await session.commit()

    reader = BackgroundTurnSourceReader(AsyncSessionFactory)
    source = await reader.load(
        principal_id=user_id,
        conversation_id=conversation_id,
        user_message_id=user_message_id,
        assistant_message_id=assistant_message_id,
    )
    assert source.external_user_id == "trusted-external"
    assert source.user_message == "source user content"
    assert source.assistant_message == "source assistant content"
    assert source.media_metadata[0]["image_id"] == "image-1"

    with pytest.raises(DurableJobPayloadError, match="missing or unauthorized"):
        await reader.load(
            principal_id=other_user_id,
            conversation_id=conversation_id,
            user_message_id=user_message_id,
            assistant_message_id=assistant_message_id,
        )

    async with AsyncSessionFactory() as session:
        await session.execute(delete(User).where(User.id.in_((user_id, other_user_id))))
        await session.commit()
