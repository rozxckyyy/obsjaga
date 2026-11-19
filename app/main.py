from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException

from app import admin, tickets
from app.config import ROOT
from app.services import AuthService, ServiceError
from app.web import (
    HOME_ROUTES, Actor, CookieSessions, Db, PostedForm, SignInRequired, Visitor,
    field, page, redirect, settings,
)

app = FastAPI(title="Общежитие", docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(
    CookieSessions, secret_key=settings.secret_key, session_cookie="dorm_session",
    same_site="lax", https_only=settings.https_only, max_age=8 * 60 * 60,
)
app.mount("/static", StaticFiles(directory=ROOT / "app" / "static"), name="static")
app.include_router(tickets.router)
app.include_router(admin.router)


@app.middleware("http")
async def response_headers(request: Request, call_next):
    response = await call_next(request)
    if not request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'; form-action 'self'"
    )
    return response


@app.exception_handler(SignInRequired)
def sign_in_required(request: Request, exc: SignInRequired):
    return redirect(request, "login")


@app.exception_handler(ServiceError)
def service_error(request: Request, exc: ServiceError):
    return page(
        request, "error.html", status_code=exc.status_code,
        title={403: "Доступ ограничен", 404: "Страница не найдена", 409: "Заявка изменилась"}.get(
            exc.status_code, "Не удалось выполнить действие",
        ),
        error=str(exc), number=request.path_params.get("number") if exc.status_code == 409 else None,
    )


@app.exception_handler(RequestValidationError)
def invalid_request(request: Request, exc: RequestValidationError):
    return service_error(request, ServiceError("Проверьте адрес страницы.", 404))


@app.exception_handler(HTTPException)
def http_error(request: Request, exc: HTTPException):
    message = "Проверьте адрес страницы." if exc.status_code == 404 else "Действие недоступно."
    return service_error(request, ServiceError(message, exc.status_code))


@app.get("/")
def home(request: Request, user: Visitor):
    return redirect(request, HOME_ROUTES[user.role] if user else "login")


@app.get("/login")
def login(request: Request, user: Visitor):
    if user:
        return redirect(request, HOME_ROUTES[user.role])
    return page(request, "login.html", title="Вход", username="")


@app.post("/login")
def sign_in(request: Request, db: Db, form: PostedForm):
    username = field(form, "username")
    try:
        user = AuthService(db).authenticate(username, field(form, "password"))
    except ServiceError as exc:
        return page(request, "login.html", title="Вход", username=username, error=str(exc), status_code=401)
    request.session.clear()
    request.session["user_id"] = user.id
    return redirect(request, HOME_ROUTES[user.role])


@app.post("/logout")
def logout(request: Request, user: Actor, form: PostedForm):
    request.session.clear()
    return redirect(request, "login")


@app.get("/privacy-policy")
def privacy_policy(request: Request, user: Visitor):
    return page(
        request, "legal_document.html", title="Политика конфиденциальности",
        document_template="legal/privacy_policy.html",
    )


@app.get("/personal-data-consent")
def personal_data_consent(request: Request, user: Visitor):
    return page(
        request, "legal_document.html", title="Согласие на обработку персональных данных",
        document_template="legal/personal_data_consent.html",
    )
