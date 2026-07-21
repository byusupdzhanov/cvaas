from datetime import datetime, timedelta

from fastapi import Depends, Form, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.routing import APIRouter
from fastapi.templating import Jinja2Templates
from .database import SessionLocal, pwd_context
from .models import Admin, LoginAttempt
from .i18n import get_locale_from_db, translate
from .security import (
    MAX_LOGIN_ATTEMPTS,
    LOGIN_BLOCK_MINUTES,
    enforce_csrf_protection,
    get_client_ip,
    get_csrf_token,
    login_rate_limit_message,
    login_window_expired,
    normalize_text,
)

templates = Jinja2Templates(directory="templates")
router = APIRouter(dependencies=[Depends(enforce_csrf_protection)])

def is_logged_in(request: Request):
    return request.session.get("user") is not None

def require_login(request: Request):
    if not is_logged_in(request):
        return RedirectResponse(url="/login", status_code=302)

@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    db = SessionLocal()
    try:
        locale = get_locale_from_db(db)
    finally:
        db.close()
    return templates.TemplateResponse("login.html", {
        "request": request,
        "csrf_token": get_csrf_token(request),
        "locale": locale,
        "_": lambda text, **kwargs: translate(locale, text, **kwargs),
    })


def get_login_attempt(db, username: str, ip_address: str) -> LoginAttempt | None:
    return (
        db.query(LoginAttempt)
        .filter(LoginAttempt.username == username, LoginAttempt.ip_address == ip_address)
        .first()
    )


def reset_login_attempt(attempt: LoginAttempt) -> None:
    attempt.attempts = 0
    attempt.first_attempt_at = datetime.utcnow()
    attempt.last_attempt_at = datetime.utcnow()
    attempt.blocked_until = None


def register_failed_login(db, username: str, ip_address: str) -> LoginAttempt:
    attempt = get_login_attempt(db, username, ip_address)
    now = datetime.utcnow()

    if not attempt:
        attempt = LoginAttempt(
            username=username,
            ip_address=ip_address,
            attempts=1,
            first_attempt_at=now,
            last_attempt_at=now,
        )
        db.add(attempt)
    else:
        if login_window_expired(attempt.first_attempt_at):
            attempt.attempts = 0
            attempt.first_attempt_at = now
        attempt.attempts += 1
        attempt.last_attempt_at = now

    if attempt.attempts >= MAX_LOGIN_ATTEMPTS:
        attempt.blocked_until = now + timedelta(minutes=LOGIN_BLOCK_MINUTES)

    db.commit()
    return attempt


def clear_login_attempts(db, username: str, ip_address: str) -> None:
    attempt = get_login_attempt(db, username, ip_address)
    if attempt:
        db.delete(attempt)
        db.commit()

@router.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...)
):
    username = normalize_text(username, max_length=120)
    ip_address = get_client_ip(request)
    db = SessionLocal()

    try:
        attempt = get_login_attempt(db, username, ip_address)
        if attempt and attempt.blocked_until and attempt.blocked_until > datetime.utcnow():
            locale = get_locale_from_db(db)
            return templates.TemplateResponse("login.html", {
                "request": request,
                "csrf_token": get_csrf_token(request),
                "error": login_rate_limit_message(attempt.blocked_until),
                "locale": locale,
                "_": lambda text, **kwargs: translate(locale, text, **kwargs),
            }, status_code=429)

        if attempt and login_window_expired(attempt.first_attempt_at):
            reset_login_attempt(attempt)
            db.commit()

        admin = db.query(Admin).filter(Admin.username == username).first()
        if admin and pwd_context.verify(password, admin.password_hash):
            clear_login_attempts(db, username, ip_address)
            request.session.clear()
            request.session["user"] = username
            get_csrf_token(request)
            return RedirectResponse(url="/admin", status_code=303)

        failed_attempt = register_failed_login(db, username, ip_address)
        error_message = "Неверный логин или пароль"
        status_code = 401
        if failed_attempt.blocked_until and failed_attempt.blocked_until > datetime.utcnow():
            error_message = login_rate_limit_message(failed_attempt.blocked_until)
            status_code = 429
        locale = get_locale_from_db(db)

        return templates.TemplateResponse("login.html", {
            "request": request,
            "csrf_token": get_csrf_token(request),
            "error": error_message,
            "locale": locale,
            "_": lambda text, **kwargs: translate(locale, text, **kwargs),
        }, status_code=status_code)
    finally:
        db.close()

@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=302)
