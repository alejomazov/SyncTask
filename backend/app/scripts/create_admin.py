"""Create the first administrator from ADMIN_EMAIL and ADMIN_PASSWORD.

Usage: python -m app.scripts.create_admin
"""

import sys

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.user import UserRole
from app.modules.auth import service


def main() -> int:
    settings = get_settings()
    if not settings.admin_email or not settings.admin_password:
        print("ADMIN_EMAIL and ADMIN_PASSWORD must be set", file=sys.stderr)
        return 1
    if len(settings.admin_password) < 8:
        print("ADMIN_PASSWORD must have at least 8 characters", file=sys.stderr)
        return 1

    with SessionLocal() as db:
        if service.get_user_by_email(db, settings.admin_email) is not None:
            print(f"User {settings.admin_email} already exists; nothing to do")
            return 0
        service.register_user(
            db,
            email=settings.admin_email,
            password=settings.admin_password,
            full_name=settings.admin_full_name,
            role=UserRole.ADMIN,
        )
    print(f"Administrator {settings.admin_email} created")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
