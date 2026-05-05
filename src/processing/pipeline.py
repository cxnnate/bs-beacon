import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path

import yaml
from dotenv import load_dotenv
from sqlalchemy import text as sql_text

from src.alerts.dispatcher import dispatch_alert
from src.db.connection import AsyncSessionLocal
from src.processing.claim_extractor import LLMClient, make_llm_client
from src.processing.dedup import (
    compute_text_hash, find_by_text_hash, find_similar_claim,
    merge_claim, insert_claim, copy_claims_from_message,
)
from src.processing.embeddings import Embedder
from src.processing.language import detect_language
from src.processing.urgency import check_urgency, combine_urgency

logger = logging.getLogger(__name__)

_SETTINGS_PATH = Path(__file__).parent.parent.parent / "config" / "settings.yaml"


async def fetch_batch(session, batch_size: int = 20) -> list[dict]:
    result = await session.execute(
        sql_text("""
        SELECT id, message_text, channel_name, channel_id, message_date, views, forwards
        FROM raw_messages
        WHERE processed = FALSE
          AND message_text IS NOT NULL
          AND length(message_text) >= 20
        ORDER BY message_date ASC
        LIMIT :limit
        """),
        {"limit": batch_size},
    )
    return [dict(row._mapping) for row in result.fetchall()]


async def mark_processed(session, msg_id: int) -> None:
    await session.execute(
        sql_text("UPDATE raw_messages SET processed = TRUE WHERE id = :id"),
        {"id": msg_id},
    )


async def mark_failed(session, msg_id: int) -> None:
    await session.execute(
        sql_text("UPDATE raw_messages SET failed_attempts = failed_attempts + 1 WHERE id = :id"),
        {"id": msg_id},
    )


async def should_abandon(session, msg_id: int, max_attempts: int = 3) -> bool:
    result = await session.execute(
        sql_text("SELECT failed_attempts FROM raw_messages WHERE id = :id"),
        {"id": msg_id},
    )
    row = result.fetchone()
    return bool(row and row[0] >= max_attempts)


async def process_message(session, message: dict, llm_client: LLMClient, embedder: Embedder) -> None:
    msg_id = message["id"]
    msg_text = message["message_text"]
    channel = message["channel_name"]

    source_language = detect_language(msg_text)

    text_hash = compute_text_hash(msg_text)
    await session.execute(
        sql_text("UPDATE raw_messages SET text_hash = :hash WHERE id = :id"),
        {"hash": text_hash, "id": msg_id},
    )

    existing_msg_id = await find_by_text_hash(session, text_hash, exclude_id=msg_id)
    if existing_msg_id:
        logger.info(f"[{channel}] msg {msg_id}: duplicate of msg {existing_msg_id} (text-hash match) — copying claims")
        await copy_claims_from_message(
            session, existing_msg_id, msg_id,
            message["channel_name"], message["message_date"],
        )
        await mark_processed(session, msg_id)
        return

    rules_urgent = check_urgency(msg_text)

    extraction = llm_client.extract(
        text=msg_text,
        channel_name=message["channel_name"],
        message_date=str(message["message_date"]),
        view_count=message.get("views") or 0,
        forward_count=message.get("forwards") or 0,
    )

    urgency = combine_urgency(rules_urgent, extraction.meta.urgency_signals)

    if not extraction.claims:
        logger.info(f"[{channel}] msg {msg_id}: no claims extracted (lang={source_language})")
        await mark_processed(session, msg_id)
        return

    new_count = merged_count = 0
    for claim in extraction.claims:
        embedding = embedder.embed(claim.text)
        similar_id = await find_similar_claim(session, embedding)
        if similar_id:
            await merge_claim(session, similar_id, msg_id, message["channel_name"], message["message_date"])
            merged_count += 1
            action = "merged"
        else:
            await insert_claim(session, claim, embedding, source_language, urgency, extraction.meta, message)
            new_count += 1
            action = "new"
            if urgency:
                asyncio.create_task(
                    dispatch_alert(claim.text, channel, claim.checkworthy_score)
                )
        if len(claim.text.split()) <= 25:
            logger.info(f"  [{action}] \"{claim.text}\"")

    intake = message["message_date"]
    intake_str = intake.strftime("%Y-%m-%d %H:%M UTC") if hasattr(intake, "strftime") else str(intake)
    processed_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    logger.info(
        f"[{channel}] msg {msg_id}: {len(extraction.claims)} claim(s) — "
        f"{new_count} new, {merged_count} merged "
        f"(lang={source_language}, urgent={urgency}, intake={intake_str}, processed={processed_str})"
    )
    await mark_processed(session, msg_id)


async def run_pipeline() -> None:
    load_dotenv()
    settings = yaml.safe_load(_SETTINGS_PATH.read_text())
    batch_size = settings["processor"]["batch_size"]
    poll_interval = settings["processor"]["poll_interval_seconds"]
    max_attempts = settings["processor"]["max_failed_attempts"]

    llm_client = make_llm_client()
    embedder = Embedder()

    async with AsyncSessionLocal() as session:
        await session.execute(sql_text("SELECT 1"))
        logger.info("DB connection OK")
        result = await session.execute(
            sql_text("SELECT count(*) FROM raw_messages WHERE processed = FALSE AND message_text IS NOT NULL AND length(message_text) >= 20")
        )
        queued = result.scalar()
    logger.info(f"Processor started — {queued} message(s) queued for processing")

    while True:
        async with AsyncSessionLocal() as session:
            batch = await fetch_batch(session, batch_size)
            if not batch:
                logger.info("No unprocessed messages — sleeping")
            for message in batch:
                msg_id = message["id"]
                if await should_abandon(session, msg_id, max_attempts):
                    logger.warning(f"[{message['channel_name']}] msg {msg_id}: abandoning after {max_attempts} failed attempts")
                    await mark_processed(session, msg_id)
                    await session.commit()
                    continue
                try:
                    await process_message(session, message, llm_client, embedder)
                    await session.commit()
                except Exception:
                    await session.rollback()
                    await mark_failed(session, msg_id)
                    await session.commit()
                    logger.exception(f"Failed to process message {msg_id}")

        await asyncio.sleep(poll_interval)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_pipeline())
