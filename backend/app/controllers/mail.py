import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.integrations.google.client import GoogleError
from app.modules.auth.dependencies import CurrentUser
from app.schemas.mail import MailMessageDetail, MailMessagesResponse
from app.services import mail
from app.services.connections import ReauthorizationRequiredError

router = APIRouter(prefix="/mail", tags=["mail"])

DbSession = Annotated[Session, Depends(get_db)]

DEFAULT_LIMIT = 10
MAX_LIMIT = 25


@router.get("/messages", response_model=MailMessagesResponse)
def list_messages(
    db: DbSession,
    user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    unread: bool = False,
) -> mail.MailResult:
    return mail.list_messages(db, user_id=user.id, limit=limit, unread_only=unread)


@router.get("/messages/{account_id}/{message_id}", response_model=MailMessageDetail)
def get_message(
    account_id: uuid.UUID,
    message_id: Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,64}$")],
    db: DbSession,
    user: CurrentUser,
) -> mail.MailMessage:
    try:
        return mail.get_message(db, user_id=user.id, account_id=account_id, message_id=message_id)
    except mail.MailAccountNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Connected account not found") from None
    except mail.MailMessageNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Message not found") from None
    except mail.MailPermissionMissingError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "The account has no permission to read mail"
        ) from None
    except ReauthorizationRequiredError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "The account has to be connected again"
        ) from None
    except GoogleError:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "The mail service is not available right now"
        ) from None
