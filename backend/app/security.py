import secrets

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

from app.config import settings

device_key_header = APIKeyHeader(name="X-Device-Key", auto_error=False)
operator_key_header = APIKeyHeader(name="X-Operator-Key", auto_error=False)


def _check(key: str | None, expected: str, who: str) -> str:
    if not key or not secrets.compare_digest(key, expected):
        raise HTTPException(status_code=401, detail=f"invalid {who} key")
    return key


def require_device_key(key: str | None = Security(device_key_header)) -> str:
    return _check(key, settings.device_api_key, "device")


def require_operator_key(key: str | None = Security(operator_key_header)) -> str:
    return _check(key, settings.operator_api_key, "operator")
