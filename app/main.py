import os

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from .models import Experience, Skill, Info, Course, Education, Language, Project, Certificate, Recommendation
from .version import __version__
from sqlalchemy.orm import Session
from .database import SessionLocal
from .auth import router as auth_router
from starlette.middleware.sessions import SessionMiddleware
from os.path import exists, getmtime
from datetime import datetime
from dateutil.relativedelta import relativedelta
from jinja2 import pass_context
from .security import build_session_secret
from .i18n import get_locale_from_info, translate, status_label


app = FastAPI()
app.add_middleware(
    SessionMiddleware,
    secret_key=build_session_secret(),
    same_site="lax",
    https_only=os.getenv("CVAAS_SECURE_COOKIES", "0") == "1",
    max_age=60 * 60 * 8,
)

app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")

@pass_context
def nl2br(ctx, value):
    return value.replace('\n', '<br>')

templates.env.filters['nl2br'] = nl2br


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    return response

@app.get("/", response_class=HTMLResponse)
def read_root(request: Request):
    db: Session = SessionLocal()
    infos = {i.field: i.value for i in db.query(Info).all()}
    locale = get_locale_from_info(infos)
    visibility = infos.get("visibility", "public")
    if visibility != "public":
        return templates.TemplateResponse("resume_hidden.html", {
            "request": request,
            "message": infos.get("hidden_message", "❌ Резюме временно скрыто владельцем."),
            "locale": locale,
            "_": lambda text, **kwargs: translate(locale, text, **kwargs),
        })
    experiences = db.query(Experience).order_by(Experience.start_date.desc()).all()
    skills = db.query(Skill).order_by(Skill.level.desc(), Skill.name.asc()).all()
    courses = db.query(Course).all()
    educations = db.query(Education).all()
    photo_exists = exists("static/uploads/photo.jpg")
    photo_version = int(getmtime("static/uploads/photo.jpg")) if photo_exists else None
    languages = db.query(Language).all()
    projects = db.query(Project).order_by(Project.position.asc(), Project.id.asc()).all()
    certificates = db.query(Certificate).all()
    recommendations = db.query(Recommendation).order_by(Recommendation.position.asc(), Recommendation.id.asc()).all()
    last_updated = get_latest_updated(db)
    template_name = infos.get("template", "classic")
    total_experience = calculate_total_experience(experiences)
    db.close()

    return templates.TemplateResponse("resume.html", {
        "request": request,
        "experience": experiences,
        "total_experience": total_experience,
        "courses": courses,
        "skills": skills,
        "info": infos,
        "educations": educations,
        "photo": photo_exists,
        "photo_version": photo_version,
        "languages": languages,
        "projects": projects,
        "certificates": certificates, 
        "recommendations": recommendations,
        "last_updated": last_updated,
        "template": template_name,
        "version": __version__,
        "locale": locale,
        "_": lambda text, **kwargs: translate(locale, text, **kwargs),
        "status_label": lambda status: status_label(status, locale),
    })

def calculate_total_experience(experiences):
    total_months = 0
    now = datetime.today()

    for exp in experiences:
        if "—" not in exp.period:
            continue
        start_str, end_str = exp.period.split("—")
        start = datetime.strptime(start_str.strip(), "%m.%Y")

        end_str = end_str.strip()
        end = now if end_str == "н.в." else datetime.strptime(end_str, "%m.%Y")

        delta = relativedelta(end, start)
        total_months += delta.years * 12 + delta.months

    years = total_months // 12
    months = total_months % 12

    year_word = pluralize_ru(years, ["год", "года", "лет"])
    month_word = pluralize_ru(months, ["месяц", "месяца", "месяцев"])

    if years and months:
        return f"{years} {year_word} {months} {month_word}"
    elif years:
        return f"{years} {year_word}"
    elif months:
        return f"{months} {month_word}"
    else:
        return "меньше месяца"

def pluralize_ru(number, forms):
    """
    Склонение по числу: ["год", "года", "лет"] и ["месяц", "месяца", "месяцев"]
    """
    number = abs(number)
    if number % 10 == 1 and number % 100 != 11:
        return forms[0]
    elif 2 <= number % 10 <= 4 and not (12 <= number % 100 <= 14):
        return forms[1]
    else:
        return forms[2]

def get_latest_updated(db: Session) -> datetime | None:
    timestamps = []

    models = [Experience, Skill, Info, Course, Education, Language, Project, Certificate, Recommendation]
    for model in models:
        latest = db.query(model).order_by(model.updated_at.desc().nullslast()).first()
        if latest and latest.updated_at:
            timestamps.append(latest.updated_at)

    return max(timestamps) if timestamps else None

@app.get("/preview", response_class=HTMLResponse)
def preview_resume(request: Request):
    db: Session = SessionLocal()
    experiences = db.query(Experience).all()
    skills = db.query(Skill).order_by(Skill.level.desc(), Skill.name.asc()).all()
    infos = {i.field: i.value for i in db.query(Info).all()}
    courses = db.query(Course).all()
    educations = db.query(Education).all()
    photo_exists = exists("static/uploads/photo.jpg")
    photo_version = int(getmtime("static/uploads/photo.jpg")) if photo_exists else None
    languages = db.query(Language).all()
    projects = db.query(Project).order_by(Project.position.asc(), Project.id.asc()).all()
    certificates = db.query(Certificate).all()
    recommendations = db.query(Recommendation).order_by(Recommendation.position.asc(), Recommendation.id.asc()).all()
    last_skill = db.query(Skill).order_by(Skill.updated_at.desc()).first()
    last_updated = get_latest_updated(db)
    total_experience = calculate_total_experience(experiences)
    locale = get_locale_from_info(infos)
    db.close()

    return templates.TemplateResponse("resume.html", {
        "request": request,
        "experience": experiences,
        "total_experience": total_experience,
        "courses": courses,
        "skills": skills,
        "info": infos,
        "educations": educations,
        "photo": photo_exists,
        "photo_version": photo_version,
        "languages": languages,
        "projects": projects,
        "certificates": certificates,
        "recommendations": recommendations,
        "last_updated": last_updated,
        "preview": True,
        "version": __version__,
        "locale": locale,
        "_": lambda text, **kwargs: translate(locale, text, **kwargs),
        "status_label": lambda status: status_label(status, locale),
    })


from .database import init_db, init_admin_user
from .admin import router as admin_router

init_db()
init_admin_user(SessionLocal())
app.include_router(admin_router)
app.include_router(auth_router)
