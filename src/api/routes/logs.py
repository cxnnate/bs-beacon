import docker as docker_sdk
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from src.api.auth import require_auth

router = APIRouter()

_ALLOWED = {"scraper", "processor"}


@router.get("/logs/{service}", response_class=PlainTextResponse)
async def get_logs(service: str, _: str = Depends(require_auth)):
    if service not in _ALLOWED:
        raise HTTPException(status_code=400, detail=f"Unknown service: {service!r}")
    try:
        client = docker_sdk.from_env()
        container = client.containers.get(f"bsbeacon-{service}")
        logs = container.logs(tail=30, stdout=True, stderr=True)
        return logs.decode("utf-8", errors="replace") if isinstance(logs, bytes) else str(logs)
    except docker_sdk.errors.NotFound:
        raise HTTPException(status_code=404, detail=f"Container bsbeacon-{service} not found")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
