import os
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

# API Key 从环境变量注入（部署时由 K8s Secret 提供），不硬编码。
api_key = os.environ.get("API_KEY", "")
if not api_key:
    raise RuntimeError(
        "API Key is not configured. Please set up your API Key via the API_KEY environment variable."
    )

security = HTTPBearer()


def api_key_auth(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
):
    if credentials.credentials != api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API Key")
