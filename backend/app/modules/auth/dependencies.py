from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.user import User, UserRole
from app.modules.auth import service


def get_optional_user(request: Request, db: Annotated[Session, Depends(get_db)]) -> User | None:
    """Return the active user owning the session cookie, or None if there is no valid session."""
    token = request.cookies.get(get_settings().auth_cookie_name)
    if token is None:
        return None

    user_id = decode_access_token(token)
    if user_id is None:
        return None

    user = service.get_user_by_id(db, user_id)
    if user is None or not user.is_active:
        return None
    return user


OptionalUser = Annotated[User | None, Depends(get_optional_user)]


def get_current_user(user: OptionalUser) -> User:
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_admin(user: CurrentUser) -> User:
    if user.role != UserRole.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin privileges required")
    return user


AdminUser = Annotated[User, Depends(require_admin)]
