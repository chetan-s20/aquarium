"""Login / logout / session endpoints (Phase 6)."""
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import SESSION_COOKIE, _encode, require_user, verify_password
from app.db import get_db
from app.models import User
from app.schemas import ORM

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginCreate(BaseModel):
    name: str
    password: str


class UserRead(ORM):
    id: str
    name: str
    role: str


@router.post("/login")
def login(payload: LoginCreate, response: Response, db: Session = Depends(get_db)) -> UserRead:
    user = db.query(User).filter_by(name=payload.name).first()
    if not user or not verify_password(user.password_hash, payload.password, salt=user.name):
        raise HTTPException(status_code=401, detail="invalid credentials")
    response.set_cookie(SESSION_COOKIE, _encode(user), httponly=True, samesite="lax")
    return UserRead.model_validate(user)


@router.post("/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(SESSION_COOKIE)
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(require_user)) -> UserRead:
    return UserRead.model_validate(user)
