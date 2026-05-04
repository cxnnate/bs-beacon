import asyncio
import logging
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.errors import FloodWaitError
from sqlalchemy import text

from src.db.connection import AsyncSessionLocal
from src.ingestion.checkpoint import get_last_id, update_last_id

logger = logging.getLogger(__name__)

_SETTINGS_PATH = Path(__file__).parent.parent.parent / "config" / "settings.yaml"
_CHANNELS_PATH = Path(__file__).parent.parent.parent / "config" / "channels.yaml"


def load_channels(path: str | None = None) -> list[dict]:
    p = path or str(_CHANNELS_PATH)
    with open(p) as f:
        data = yaml.safe_load(f)
    channels = []
    for domain, channel_list in data.get("channels", {}).items():
        for ch in channel_list:
            channels.append({
                "username": ch["username"],
                "domain": domain,
                "display_name": ch["display_name"],
            })
    return channels


def should_skip(message) -> bool:
    if not message.text:
        return True
    if len(message.text.strip()) < 20:
        return True
    return False


async def store_messages(session, messages: list[dict]) -> None:
    for msg in messages:
        await session.execute(
            text("""
            INSERT INTO raw_messages (
                telegram_msg_id, channel_id, channel_name, message_text,
                message_date, views, forwards, replies, media_type,
                media_file_id, forward_from
            ) VALUES (
                :telegram_msg_id, :channel_id, :channel_name, :message_text,
                :message_date, :views, :forwards, :replies, :media_type,
                :media_file_id, :forward_from
            )
            ON CONFLICT (channel_id, telegram_msg_id) DO NOTHING
            """),
            msg,
        )


async def fetch_channel(
    client, session, channel: dict, monitored_channel_ids: set
) -> int:
    username = channel["username"]
    channel_name = channel["display_name"]

    try:
        entity = await client.get_entity(username)
        channel_id = entity.id
        last_id = await get_last_id(session, channel_id)

        messages = []
        async for msg in client.iter_messages(entity, min_id=last_id, limit=100):
            if should_skip(msg):
                continue

            forward_from = None
            if msg.forward and hasattr(msg.forward, "chat_id") and msg.forward.chat_id:
                if msg.forward.chat_id in monitored_channel_ids:
                    continue
                forward_from = str(msg.forward.chat_id)

            media_type = None
            if msg.media:
                media_type = type(msg.media).__name__.lower().replace("messagemedia", "")

            messages.append({
                "telegram_msg_id": msg.id,
                "channel_id": channel_id,
                "channel_name": channel_name,
                "message_text": msg.text,
                "message_date": msg.date,
                "views": msg.views,
                "forwards": msg.forwards,
                "replies": msg.replies.replies if msg.replies else None,
                "media_type": media_type,
                "media_file_id": None,
                "forward_from": forward_from,
            })

        if messages:
            await store_messages(session, messages)
            new_last_id = max(m["telegram_msg_id"] for m in messages)
            await update_last_id(session, channel_id, channel_name, new_last_id)
            dates = [m["message_date"] for m in messages]
            oldest = min(dates).strftime("%Y-%m-%d %H:%M UTC")
            newest = max(dates).strftime("%Y-%m-%d %H:%M UTC")
            logger.info(f"[{channel_name}] ingested {len(messages)} message(s) [{oldest} → {newest}]")

        return len(messages)

    except FloodWaitError as e:
        logger.warning(f"Rate limited on {username}, sleeping {e.seconds}s")
        await asyncio.sleep(e.seconds)
        return 0
    except Exception:
        logger.exception(f"Error fetching {username}")
        return 0


async def run_scraper() -> None:
    load_dotenv()
    settings = yaml.safe_load(_SETTINGS_PATH.read_text())
    poll_interval = settings["scraper"]["poll_interval_seconds"]

    channels = load_channels()
    api_id = int(os.environ["TELEGRAM_API_ID"])
    api_hash = os.environ["TELEGRAM_API_HASH"]
    session_name = os.getenv("TELEGRAM_SESSION_NAME", "bsbeacon")

    async with AsyncSessionLocal() as session:
        await session.execute(text("SELECT 1"))
        logger.info("DB connection OK")

    async with TelegramClient(session_name, api_id, api_hash) as client:
        logger.info(f"Scraper started — monitoring {len(channels)} channels")

        async with AsyncSessionLocal() as session:
            for channel in channels:
                entity = await client.get_entity(channel["username"])
                last_id = await get_last_id(session, entity.id)
                logger.info(
                    f"  {channel['display_name']}: resuming from message id={last_id} "
                    f"({'first run' if last_id == 0 else 'checkpoint restored'})"
                )

        while True:
            async with AsyncSessionLocal() as session:
                for channel in channels:
                    # Phase 3: populate with resolved entity IDs to skip cross-channel forwards
                    count = await fetch_channel(client, session, channel, set())
                    if not count:
                        logger.info(f"[{channel['display_name']}] no new messages")
                await session.commit()
            logger.info(f"Poll complete — sleeping {poll_interval}s")
            await asyncio.sleep(poll_interval)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_scraper())
