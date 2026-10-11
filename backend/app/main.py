from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.controllers import (
    admin,
    auth,
    calendar,
    chat,
    connections,
    health,
    integrations,
    settings,
    tasks,
)
from app.core.config import get_settings
from app.core.crypto import validate_encryption_key


def create_app() -> FastAPI:
    config = get_settings()
    if not config.jwt_secret_key:
        raise RuntimeError("JWT_SECRET_KEY must be set")
    validate_encryption_key()

    app = FastAPI(title=config.app_name)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(admin.router)
    app.include_router(integrations.router)
    app.include_router(connections.router)
    app.include_router(calendar.router)
    app.include_router(tasks.router)
    app.include_router(settings.router)
    app.include_router(chat.router)
    return app


app = create_app()
