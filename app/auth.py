from fastapi import Request, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.routing import APIRouter
from fastapi.templating import Jinja2Templates
from .database import SessionLocal, pwd_context
from .models import Admin

templates = Jinja2Templates(directory="templates")
router = APIRouter()

def is_logged_in(request: Request):
    return request.session.get("user") is not None

def require_login(request: Request):
    if not is_logged_in(request):
        return RedirectResponse(url="/login", status_code=302)

@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@router.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...)
):
    db = SessionLocal()
    admin = db.query(Admin).filter(Admin.username == username).first()
    db.close()

    if admin and pwd_context.verify(password, admin.password_hash):
        request.session["user"] = username
        return RedirectResponse(url="/admin", status_code=303)

    return templates.TemplateResponse("login.html", {
        "request": request,
        "error": "Неверный логин или пароль"
    }, status_code=401)

@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=302)
