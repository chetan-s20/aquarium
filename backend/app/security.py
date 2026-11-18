from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader

from app.config import settings

device_key_header = APIKeyHeader(name=settings.device_api_key_header, auto_error=False)
operator_key_header = APIKeyHeader(name="X-Operator-Key", auto_error=False)


def require_device_key(key: str | None = Security(device_key_header)):
    expected = getattr(settings, "device_api_key", "dev-device-key-change-me")
    if key != expected:
        raise HTTPException(status_code=401, detail="invalid device key")
    return key


def require_operator_key(key: str | None = Security(operator_key_header)):
    expected = getattr(settings, "operator_api_key", "dev-operator-key-change-me")
    if key != expected:
        raise HTTPException(status_code=401, detail="invalid operator key")
    return key
