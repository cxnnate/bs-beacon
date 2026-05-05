import subprocess
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from src.api.auth import require_auth

router = APIRouter()

_ALLOWED = {"scraper", "processor"}


@router.get("/logs/{service}", response_class=PlainTextResponse)
async def get_logs(service: str, _: str = Depends(require_auth)):
    if service not in _ALLOWED:
        raise HTTPException(status_code=400, detail=f"Unknown service: {service!r}")
    result = subprocess.run(
        ["docker", "logs", "--tail", "30", f"bsbeacon-{service}"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    return result.stdout + result.stderr
