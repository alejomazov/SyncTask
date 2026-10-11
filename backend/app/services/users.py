import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.user import User


class CannotDisableOwnAccountError(Exception):
    pass


def list_users(
    db: Session, *, search: str | None = None, page: int = 1, page_size: int = 20
) -> tuple[list[User], int]:
    query = select(User)
    if search and search.strip():
        pattern = f"%{search.strip()}%"
        query = query.where(or_(User.email.ilike(pattern), User.full_name.ilike(pattern)))

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(
        query.order_by(User.created_at.desc(), User.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return list(items), total


def set_user_active(
    db: Session, *, user_id: uuid.UUID, is_active: bool, acting_user_id: uuid.UUID
) -> User | None:
    """Enable or disable an account. Returns None if the user does not exist."""
    user = db.get(User, user_id)
    if user is None:
        return None
    if user.id == acting_user_id and not is_active:
        raise CannotDisableOwnAccountError

    user.is_active = is_active
    db.commit()
    db.refresh(user)
    return user
