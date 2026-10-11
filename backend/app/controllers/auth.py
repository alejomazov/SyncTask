from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import create_access_token
from app.db.session import get_db
from app.models.user import User
from app.modules.audit import service as audit
from app.modules.audit.actions import AuditAction
from app.modules.auth import service
from app.modules.auth.dependencies import CurrentUser, OptionalUser
from app.schemas.auth import LoginRequest, UserCreate, UserRead

router = APIRouter(prefix="/auth", tags=["auth"])

DbSession = Annotated[Session, Depends(get_db)]


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _set_auth_cookie(response: Response, user: User) -> None:
    settings = get_settings()
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=create_access_token(user.id),
        max_age=settings.access_token_expire_minutes * 60,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        path="/",
    )


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, request: Request, response: Response, db: DbSession) -> User:
    try:
        user = service.register_user(
            db, email=payload.email, password=payload.password, full_name=payload.full_name
        )
    except service.EmailAlreadyRegisteredError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered") from None

    audit.record(
        db,
        AuditAction.AUTH_REGISTER,
        actor_id=user.id,
        target_type="user",
        target_id=user.id,
        ip_address=_client_ip(request),
    )
    _set_auth_cookie(response, user)
    return user


@router.post("/login", response_model=UserRead)
def login(payload: LoginRequest, request: Request, response: Response, db: DbSession) -> User:
    ip_address = _client_ip(request)
    user = service.authenticate_user(db, email=payload.email, password=payload.password)
    if user is None:
        audit.record(
            db,
            AuditAction.AUTH_LOGIN_FAILED,
            detail={"email": payload.email.lower(), "reason": "invalid_credentials"},
            ip_address=ip_address,
        )
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    if not user.is_active:
        audit.record(
            db,
            AuditAction.AUTH_LOGIN_FAILED,
            actor_id=user.id,
            detail={"email": user.email, "reason": "account_disabled"},
            ip_address=ip_address,
        )
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account disabled")

    audit.record(db, AuditAction.AUTH_LOGIN, actor_id=user.id, ip_address=ip_address)
    _set_auth_cookie(response, user)
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, db: DbSession, user: OptionalUser) -> None:
    if user is not None:
        audit.record(db, AuditAction.AUTH_LOGOUT, actor_id=user.id, ip_address=_client_ip(request))
    response.delete_cookie(get_settings().auth_cookie_name, path="/")


@router.get("/me", response_model=UserRead)
def me(user: CurrentUser) -> User:
    return user
