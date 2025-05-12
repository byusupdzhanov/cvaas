from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, FileResponse
from starlette.responses import RedirectResponse
from .models import Experience, Skill, Info, Course, Education, Language, Project, Certificate, Recommendation
from sqlalchemy.orm import Session
from .database import SessionLocal
from .auth import router as auth_router, require_login
from fastapi.middleware import Middleware
from starlette.middleware.sessions import SessionMiddleware
from os.path import exists
from datetime import datetime
from time import time
from jinja2 import pass_context


app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key="devops_secret_key_2025_!@#%&xyz")

app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")

@pass_context
def nl2br(ctx, value):
    return value.replace('\n', '<br>')

templates.env.filters['nl2br'] = nl2br

@app.get("/", response_class=HTMLResponse)
def read_root(request: Request):
    db: Session = SessionLocal()
    infos = {i.field: i.value for i in db.query(Info).all()}
    visibility = infos.get("visibility", "public")
    if visibility != "public":
        return templates.TemplateResponse("resume_hidden.html", {
            "request": request,
            "message": infos.get("hidden_message", "❌ Резюме временно скрыто владельцем.")
        })
    experiences = db.query(Experience).all()
    skills = db.query(Skill).all()
    courses = db.query(Course).all()
    educations = db.query(Education).all()
    photo_exists = exists("static/uploads/photo.jpg")
    languages = db.query(Language).all()
    projects = db.query(Project).all()
    certificates = db.query(Certificate).all()
    recommendations = db.query(Recommendation).all()
    last_updated = get_latest_updated(db)
    template_name = infos.get("template", "classic")
    db.close()

    return templates.TemplateResponse("resume.html", {
        "request": request,
        "experience": experiences,
        "courses": courses,
        "skills": skills,
        "info": infos,
        "educations": educations,
        "photo": photo_exists,
        "languages": languages,
        "projects": projects,
        "certificates": certificates, 
        "recommendations": recommendations,
        "last_updated": last_updated,
        "template": template_name
    })
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
    skills = db.query(Skill).all()
    infos = {i.field: i.value for i in db.query(Info).all()}
    courses = db.query(Course).all()
    educations = db.query(Education).all()
    photo_exists = exists("static/uploads/photo.jpg")
    languages = db.query(Language).all()
    projects = db.query(Project).all()
    certificates = db.query(Certificate).all()
    recommendations = db.query(Recommendation).all()
    last_skill = db.query(Skill).order_by(Skill.updated_at.desc()).first()
    last_updated = get_latest_updated(db)
    db.close()

    return templates.TemplateResponse("resume.html", {
        "request": request,
        "experience": experiences,
        "courses": courses,
        "skills": skills,
        "info": infos,
        "educations": educations,
        "photo": photo_exists,
        "languages": languages,
        "projects": projects,
        "certificates": certificates,
        "recommendations": recommendations,
        "last_updated": last_updated,
        "preview": True
    })


from .database import init_db, init_admin_user
from .admin import router as admin_router

init_db()
init_admin_user(SessionLocal())
app.include_router(admin_router)
app.include_router(auth_router)
