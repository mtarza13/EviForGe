import os
import time
from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from redis import Redis

from eviforge.core.auth import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    Token,
    create_access_token,
    get_current_active_user,
    verify_password,
)
from eviforge.core.db import create_session_factory, get_setting, set_setting
from eviforge.core.models import User
from eviforge.core.audit import audit_from_user
from eviforge.config import ACK_TEXT, load_settings

router = APIRouter(prefix="/auth", tags=["auth"])

_MEM_RATE_LIMIT: dict[str, tuple[int, float]] = {}


def _client_ip(request: Request) -> str:
    trust_proxy = os.getenv("EVIFORGE_TRUST_PROXY", "0") == "1"
    if trust_proxy:
        fwd = request.headers.get("x-forwarded-for") or request.headers.get("x-real-ip")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _enforce_login_rate_limit(request: Request, *, redis_url: str) -> None:
    """
    Basic brute-force protection for /auth/token.

    Uses Redis when available; falls back to in-memory counters for local dev.
    """
    limit = int(os.getenv("EVIFORGE_LOGIN_RATE_LIMIT", "25"))
    window = int(os.getenv("EVIFORGE_LOGIN_RATE_WINDOW_SECONDS", "300"))
    if limit <= 0 or window <= 0:
        return

    ip = _client_ip(request)
    bucket = int(time.time()) // window
    key = f"eviforge:ratelimit:login:{ip}:{bucket}"

    try:
        r = Redis.from_url(redis_url)
        n = int(r.incr(key))
        if n == 1:
            r.expire(key, window)
        if n > limit:
            raise HTTPException(status_code=429, detail="Too many login attempts. Try again later.")
        return
    except HTTPException:
        raise
    except Exception:
        # Fallback: in-memory per-process.
        now = time.time()
        count, expires = _MEM_RATE_LIMIT.get(key, (0, now + window))
        if now > expires:
            count, expires = 0, now + window
        count += 1
        _MEM_RATE_LIMIT[key] = (count, expires)
        if count > limit:
            raise HTTPException(status_code=429, detail="Too many login attempts. Try again later.")


class AckRequest(BaseModel):
    text: str
    actor: str = "local"


@router.get("/ack/status")
def ack_status():
    settings = load_settings()
    SessionLocal = create_session_factory(settings.database_url)
    with SessionLocal() as session:
        ack = get_setting(session, "authorization_ack")
        return {"acknowledged": ack is not None, "required_text": ACK_TEXT}


@router.post("/ack")
def ack(req: AckRequest):
    if req.text.strip() != ACK_TEXT:
        raise HTTPException(status_code=400, detail={"error": "ack_text_mismatch", "required_text": ACK_TEXT})

    settings = load_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    SessionLocal = create_session_factory(settings.database_url)
    with SessionLocal() as session:
        set_setting(session, "authorization_ack", {"text": req.text, "actor": req.actor, "ts": datetime.utcnow().isoformat()})

    (settings.data_dir / "authorization.txt").write_text(req.text + "\n", encoding="utf-8")
    return {"acknowledged": True}

@router.post("/token", response_model=Token)
async def login_for_access_token(
    request: Request,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()]
):
    settings = load_settings()
    _enforce_login_rate_limit(request, redis_url=settings.redis_url)
    SessionLocal = create_session_factory(settings.database_url)
    
    with SessionLocal() as session:
        user = session.query(User).filter(User.username == form_data.username).first()
        
        if not user or not verify_password(form_data.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        try:
            audit_from_user(
                session,
                action="auth.login",
                user=user,
                request=request,
                details={},
            )
            session.commit()
        except Exception:
            pass
            
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": user.username}, expires_delta=access_token_expires
        )
        
        # Also set cookie for Admin UI access
        response = JSONResponse(content={"access_token": access_token, "token_type": "bearer"})
        cookie_secure = os.getenv("EVIFORGE_COOKIE_SECURE", "0") == "1"
        cookie_samesite = os.getenv("EVIFORGE_COOKIE_SAMESITE", "lax")
        response.set_cookie(
            key="access_token",
            value=f"Bearer {access_token}",
            httponly=True,
            secure=cookie_secure,
            samesite=cookie_samesite,
            max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            path="/",
        )
        return response

@router.get("/me", response_model=dict)
async def read_users_me(current_user: User = Depends(get_current_active_user)):
    return {
        "username": current_user.username,
        "role": current_user.role,
        "active": current_user.is_active
    }


@router.post("/logout")
def logout(request: Request, current_user: User = Depends(get_current_active_user)):
    settings = load_settings()
    SessionLocal = create_session_factory(settings.database_url)
    try:
        with SessionLocal() as session:
            audit_from_user(
                session,
                action="auth.logout",
                user=current_user,
                request=request,
                details={},
            )
            session.commit()
    except Exception:
        pass

    response = JSONResponse(content={"ok": True})
    response.delete_cookie("access_token", path="/")
    return response
