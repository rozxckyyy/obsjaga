from collections.abc import AsyncIterator
from hmac import compare_digest
from secrets import token_urlsafe
from typing import Annotated

from fastapi import Depends, Path, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.datastructures import FormData
from starlette.exceptions import HTTPException
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import RedirectResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.config import ROOT, Settings
from app.db import get_db
from app.models import ROLE_NAMES, SPECIALTY_NAMES, STATUS_NAMES, Role, User
from app.services import AuthService, ServiceError

settings = Settings.from_env()
templates = Jinja2Templates(directory=ROOT / "app" / "templates")
templates.env.globals.update(roles=ROLE_NAMES, specialties=SPECIALTY_NAMES, statuses=STATUS_NAMES)
templates.env.filters["local_time"] = lambda dt: dt.astimezone(settings.timezone).strftime("%d.%m.%Y, %H:%M")

Db = Annotated[Session, Depends(get_db)]
RecordId = Annotated[int, Path(ge=1, le=2_147_483_647)]
HOME_ROUTES = {
    Role.STUDENT: "student_tickets",
    Role.SPECIALIST: "specialist_queue",
    Role.ADMIN: "admin_tickets",
}


class SignInRequired(Exception):
    pass


class CookieSessions:
    def __init__(self, app: ASGIApp, *, https_only: bool, **options):
        self.secure = SessionMiddleware(app, https_only=True, **options)
        self.local = self.secure if https_only else SessionMiddleware(app, **options)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        middleware = self.secure if scope.get("scheme") in {"https", "wss"} else self.local
        await middleware(scope, receive, send)


def current_user(request: Request, db: Db) -> User | None:
    user_id = request.session.get("user_id")
    user = AuthService(db).active_user(user_id) if isinstance(user_id, int) else None
    request.state.user = user
    return user


def signed_in(user: Annotated[User | None, Depends(current_user)]) -> User:
    if user is None:
        raise SignInRequired()
    return user


Actor = Annotated[User, Depends(signed_in)]
Visitor = Annotated[User | None, Depends(current_user)]


def csrf_token(request: Request) -> str:
    token = request.session.get("csrf")
    if token is None:
        token = token_urlsafe(32)
        request.session["csrf"] = token
    return token


async def checked_form(request: Request) -> AsyncIterator[FormData]:
    try:
        async with request.form(max_files=1, max_fields=16, max_part_size=32 * 1024) as form:
            expected = request.session.get("csrf")
            received = field(form, "csrf")
            if not expected or not compare_digest(expected.encode(), received.encode()):
                raise ServiceError("Форма устарела. Обновите страницу и повторите действие.", 403)
            yield form
    except HTTPException as exc:
        if exc.status_code != 400:
            raise
        raise ServiceError("Не удалось прочитать форму. Прикрепите максимум одно фото.", 400) from None


PostedForm = Annotated[FormData, Depends(checked_form)]


def field(form: FormData, name: str) -> str:
    value = form.get(name)
    return value if isinstance(value, str) else ""


def fields(form: FormData, names: tuple[str, ...]) -> dict[str, str]:
    return {name: field(form, name) for name in names}


def redirect(request: Request, endpoint: str, **parameters):
    return RedirectResponse(request.url_for(endpoint, **parameters).path, status_code=303)


def page(request: Request, template: str, *, status_code: int = 200, **context):
    return templates.TemplateResponse(
        request=request,
        name=template,
        context={
            "user": getattr(request.state, "user", None),
            "csrf": csrf_token(request),
            "notice": request.session.pop("notice", None),
            **context,
        },
        status_code=status_code,
    )
