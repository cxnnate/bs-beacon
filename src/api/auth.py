import os
import secrets
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

security = HTTPBasic()


def require_auth(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    expected_user = os.getenv("API_USERNAME", "")
    expected_pass = os.getenv("API_PASSWORD", "")
    ok_user = secrets.compare_digest(credentials.username.encode(), expected_user.encode())
    ok_pass = secrets.compare_digest(credentials.password.encode(), expected_pass.encode())
    if not (ok_user and ok_pass):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username
