import logging
import os
import httpx

logger = logging.getLogger(__name__)


async def dispatch_alert(claim_text: str, channel_name: str, score: float) -> None:
    topic = os.getenv("NTFY_TOPIC")
    if not topic:
        return
    server = os.getenv("NTFY_SERVER", "https://ntfy.sh")
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{server}/{topic}",
                content=claim_text,
                headers={
                    "Title": f"BSBeacon Alert — {channel_name}",
                    "Priority": "high",
                    "Tags": "warning,bsbeacon",
                },
                timeout=5,
            )
    except Exception:
        logger.warning("Failed to dispatch ntfy alert", exc_info=True)
