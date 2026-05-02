from typing import Optional
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def get_last_id(session: AsyncSession, channel_id: int) -> int:
    """
    Get the last processed message ID for a channel.

    Args:
        session: AsyncSession instance
        channel_id: ID of the channel

    Returns:
        The last message ID stored in checkpoints, or 0 if no checkpoint exists
    """
    result = await session.execute(
        text("SELECT last_msg_id FROM checkpoints WHERE channel_id = :channel_id"),
        {"channel_id": channel_id},
    )
    row = result.fetchone()
    return row[0] if row else 0


async def update_last_id(
    session: AsyncSession, channel_id: int, channel_name: str, last_msg_id: int
) -> None:
    """
    Update the last processed message ID for a channel.

    Uses UPSERT logic: inserts a new checkpoint if it doesn't exist,
    or updates it if it does. Only updates if the new message ID is greater
    than the existing one (idempotent).

    Args:
        session: AsyncSession instance
        channel_id: ID of the channel
        channel_name: Name of the channel
        last_msg_id: Message ID to store
    """
    await session.execute(
        text("""
        INSERT INTO checkpoints (channel_id, channel_name, last_msg_id, updated_at)
        VALUES (:channel_id, :channel_name, :last_msg_id, NOW())
        ON CONFLICT (channel_id) DO UPDATE SET
            last_msg_id = GREATEST(checkpoints.last_msg_id, EXCLUDED.last_msg_id),
            updated_at = NOW()
        """),
        {"channel_id": channel_id, "channel_name": channel_name, "last_msg_id": last_msg_id},
    )
