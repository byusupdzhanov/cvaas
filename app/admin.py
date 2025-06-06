from fastapi import APIRouter, Depends, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from .database import SessionLocal, pwd_context
from passlib import hash
from .auth import require_login
from .models import Experience, Course, Skill, Info, Education, Language, Project, Certificate, Recommendation, Admin
from fastapi.templating import Jinja2Templates
templates = Jinja2Templates(directory="templates")
from datetime import datetime
import shutil
import os
import tempfile
import json
import zipfile
import io
from pathlib import Path
import pyotp 
import secrets
from jinja2 import pass_context

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@pass_context
def nl2br(ctx, value):
    return value.replace('\n', '<br>')

templates.env.filters['nl2br'] = nl2br

@router.get("/admin")
def admin_home_redirect():
    return RedirectResponse(url="/admin/dashboard", status_code=303)

@router.get("/admin/dashboard", response_class=HTMLResponse)
def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    auth_redirect = require_login(request)
    if auth_redirect: return auth_redirect

    stats = {
        "skills": db.query(Skill).count(),
        "experience": db.query(Experience).count(),
        "education": db.query(Education).count(),
        "courses": db.query(Course).count(),
        "languages": db.query(Language).count(),
        "projects": db.query(Project).count(),
        "certificates": db.query(Certificate).count(),
        "recommendations": db.query(Recommendation).count()
    }

    latest_dates = []

    for model in [Experience, Skill, Education, Course, Language, Project, Certificate, Recommendation]:
        dt = db.query(func.max(model.updated_at)).scalar()
        if dt:
            latest_dates.append(dt)

    resume_updated = max(latest_dates) if latest_dates else None

    return templates.TemplateResponse("admin_dashboard.html", {
        "request": request,
        "stats": stats,
        "resume_updated": resume_updated
    })

@router.post("/admin/reset")
def reset_resume(request: Request, db: Session = Depends(get_db)):
    auth_redirect = require_login(request)
    if auth_redirect: return auth_redirect

    for model in [Experience, Skill, Info, Course, Education, Language, Project, Certificate, Recommendation]:
        db.query(model).delete()

    db.commit()
    return RedirectResponse(url="/admin", status_code=303)

@router.get("/admin/backup")
def download_backup(request: Request):
    auth_redirect = require_login(request)
    if auth_redirect: return auth_redirect

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
        zipf.write("resume.db", arcname="resume.db")

        upload_dir = Path("static/uploads")
        for file in upload_dir.glob("*"):
            zipf.write(file, arcname=f"uploads/{file.name}")

    buffer.seek(0)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"backup_{timestamp}.zip"

    return StreamingResponse(buffer, media_type="application/zip", headers={
        "Content-Disposition": f"attachment; filename={filename}"
    })

@router.get("/admin/export-json")
def export_json(request: Request, db: Session = Depends(get_db)):
    auth_redirect = require_login(request)
    if auth_redirect: return auth_redirect

    def serialize(obj):
        result = {}
        for col in obj.__table__.columns:
            value = getattr(obj, col.name)
            if isinstance(value, datetime):
                value = value.isoformat()
            result[col.name] = value
        return result

    data = {
        "info": [serialize(i) for i in db.query(Info).all()],
        "experience": [serialize(e) for e in db.query(Experience).all()],
        "skills": [serialize(s) for s in db.query(Skill).all()],
        "courses": [serialize(c) for c in db.query(Course).all()],
        "educations": [serialize(e) for e in db.query(Education).all()],
        "languages": [serialize(l) for l in db.query(Language).all()],
        "projects": [serialize(p) for p in db.query(Project).all()],
        "certificates": [serialize(c) for c in db.query(Certificate).all()],
        "recommendations": [serialize(r) for r in db.query(Recommendation).all()],
    }

    now = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"resume_{now}.json"

    with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".json") as tmp:
        json.dump(data, tmp, indent=4, ensure_ascii=False)
        tmp.flush()
        return FileResponse(tmp.name, filename=filename, media_type="application/json")
    
@router.get("/admin/import-json", response_class=HTMLResponse)
def show_import_page(request: Request, db: Session = Depends(get_db)):
    auth_redirect = require_login(request)
    if auth_redirect: return auth_redirect
    return templates.TemplateResponse("admin_import_json.html", {
        "request": request
    })


@router.post("/admin/import-json")
async def import_json(
    request: Request,
    json_file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    auth_redirect = require_login(request)
    if auth_redirect: return auth_redirect

    try:
        content = await json_file.read()
        data = json.loads(content)
    except Exception:
        return templates.TemplateResponse("admin_import_json.html", {
            "request": request,
            "json_error": "Невалидный JSON-файл"
        })

    db.query(Info).delete()
    db.query(Skill).delete()
    db.query(Experience).delete()
    db.query(Course).delete()
    db.query(Education).delete()
    db.query(Language).delete()
    db.query(Project).delete()
    db.query(Certificate).delete()
    db.query(Recommendation).delete()
    db.commit()

    allowed = {
        "info": ["field", "value"],
        "skills": ["name"],
        "experience": ["company", "role", "period", "description"],
        "courses": ["title", "organization", "year"],
        "educations": ["degree", "institution", "start_date", "end_date", "specialization"],
        "languages": ["name", "level"],
        "projects": ["title", "description", "link", "stack"],
        "certificates": ["title", "issuer", "year", "file_path", "link"],
        "recommendations": ["name", "company", "quote"]
    }

    models = {
        "skills": Skill,
        "experience": Experience,
        "courses": Course,
        "educations": Education,
        "languages": Language,
        "projects": Project,
        "certificates": Certificate,
        "recommendations": Recommendation
    }

    def clean(item, fields):
        return {k: v for k, v in item.items() if k in fields}

    if "info" in data:
        for item in data["info"]:
            db.add(Info(**clean(item, allowed["info"])))

    for key, model in models.items():
        for item in data.get(key, []):
            try:
                db.add(model(**clean(item, allowed[key])))
            except Exception as e:
                print(f"Ошибка в {key}: {e}")

    db.commit()

    return templates.TemplateResponse("admin_import_json.html", {
        "request": request,
        "json_success": "Резюме успешно импортировано"
    })


@router.post("/admin/experience/delete")
def delete_experience(request: Request, id: int = Form(...), db: Session = Depends(get_db)):
    auth_redirect = require_login(request)
    if auth_redirect: return auth_redirect

    exp = db.query(Experience).filter_by(id=id).first()
    if exp:
        db.delete(exp)
        db.commit()

    return RedirectResponse("/admin/experience", status_code=303)




@router.get("/admin/edit/{id}", response_class=HTMLResponse)
def edit_experience_form(id: int, request: Request, db: Session = Depends(get_db)):
    auth_redirect = require_login(request)
    if auth_redirect: return auth_redirect
    exp = db.query(Experience).get(id)
    if not exp:
        return HTMLResponse(content="Не найдено", status_code=404)
    return templates.TemplateResponse("admin_experience_edit.html", {
        "request": request,
        "exp": exp
    })

@router.post("/admin/edit/{id}")
def edit_experience(
    id: int,
    request: Request,
    company: str = Form(...),
    role: str = Form(...),
    start: str = Form(...),
    end: str = Form(None),
    current: str = Form(None),
    description: str = Form(...),
    db: Session = Depends(get_db)
):
    auth_redirect = require_login(request)
    if auth_redirect: return auth_redirect
    exp = db.query(Experience).get(id)
    if not exp:
        return HTMLResponse("Опыт не найден", status_code=404)

    start_fmt = datetime.strptime(start, "%Y-%m").strftime("%m.%Y")
    if current:
        period = f"{start_fmt} — н.в."
    elif end:
        end_fmt = datetime.strptime(end, "%Y-%m").strftime("%m.%Y")
        period = f"{start_fmt} — {end_fmt}"
    else:
        period = start_fmt

    exp.company = company
    exp.role = role
    exp.period = period
    exp.description = description
    exp.start_date = start
    exp.end_date = None if current else end
    db.commit()

    return RedirectResponse(url="/admin/add", status_code=303)




@router.get("/admin/add", response_class=HTMLResponse)
def form_add_experience(request: Request, db: Session = Depends(get_db)):
    auth_redirect = require_login(request)
    if auth_redirect: return auth_redirect
    experiences = db.query(Experience).order_by(Experience.start_date.desc()).all()
    return templates.TemplateResponse("admin_experience_add.html", {
        "request": request,
        "experiences": experiences
    })


@router.post("/admin/add")
def add_experience(request: Request,
    company: str = Form(...),
    role: str = Form(...),
    start: str = Form(...),    
    end: str = Form(None),     
    current: str = Form(None),
    description: str = Form(...),
    db: Session = Depends(get_db),
):
    auth_redirect = require_login(request)
    if auth_redirect: return auth_redirect
    start_fmt = datetime.strptime(start, "%Y-%m").strftime("%m.%Y")
    if current:
        period = f"{start_fmt} — н.в."
    elif end:
        end_fmt = datetime.strptime(end, "%Y-%m").strftime("%m.%Y")
        period = f"{start_fmt} — {end_fmt}"
    else:
        period = start_fmt

    exp = Experience(
    company=company,
    role=role,
    period=period,
    description=description,
    start_date=start,
    end_date=None if current else end
    )
    db.add(exp)
    db.commit()
    return RedirectResponse(url="/admin/add", status_code=303)


@router.get("/admin/delete/{id}")
def delete_experience(request: Request, id: int, db: Session = Depends(get_db)):
    auth_redirect = require_login(request)
    if auth_redirect: return auth_redirect
    exp = db.query(Experience).get(id)
    if exp:
        db.delete(exp)
        db.commit()
    return RedirectResponse(url="/admin/add", status_code=303)

@router.get("/recover", response_class=HTMLResponse)
def recover_form(request: Request, db: Session = Depends(get_db)):
    admin = db.query(Admin).first()
    question = admin.security_question if admin else "Где вы родились?"
    return templates.TemplateResponse("recover.html", {"request": request, "question": question, "admin": admin})

@router.post("/recover", response_class=HTMLResponse)
async def recover_post(
    request: Request,
    answer: str = Form(...),
    totp: str = Form(...),
    db: Session = Depends(get_db)
):
    admin = db.query(Admin).first()
    if not admin or not admin.security_answer or admin.security_answer.strip().lower() != answer.strip().lower():
        return templates.TemplateResponse("recover.html", {
            "request": request,
            "error": "Неверный ответ на контрольный вопрос"
        })

    if admin.twofa_enabled:
        totp_obj = pyotp.TOTP(admin.totp_secret)
        if not totp_obj.verify(totp):
            return templates.TemplateResponse("recover.html", {
                "request": request,
                "error": "Неверный код 2FA"
            })

    new_password = secrets.token_urlsafe(10)
    admin.password_hash = pwd_context.hash(new_password)
    db.commit()

    return templates.TemplateResponse("recover_success.html", {
        "request": request,
        "username": admin.username,
        "password": new_password
    })

@router.post("/admin/enable-2fa")
def enable_2fa(
    request: Request,
    code: str = Form(...),
    db: Session = Depends(get_db)
):
    auth_redirect = require_login(request)
    if auth_redirect: return auth_redirect

    admin = db.query(Admin).first()
    if not admin or not admin.totp_secret:
        return RedirectResponse("/admin/settings", status_code=303)

    totp = pyotp.TOTP(admin.totp_secret)

    if totp.verify(code.strip()):
        admin.twofa_enabled = True
        db.commit()
        return RedirectResponse("/admin/settings", status_code=303)
    else:
        return RedirectResponse("/admin/settings?error=invalid_2fa", status_code=303)
    
@router.post("/admin/disable-2fa")
def disable_2fa(request: Request, db: Session = Depends(get_db)):
    auth_redirect = require_login(request)
    if auth_redirect: return auth_redirect

    admin = db.query(Admin).first()
    if admin:
        admin.twofa_enabled = False
        admin.totp_secret = None
        db.commit()

    return RedirectResponse("/admin/settings?disabled_2fa=true", status_code=303)


@router.get("/admin/courses", response_class=HTMLResponse)
def course_list(request: Request, db: Session = Depends(get_db)):
    auth_redirect = require_login(request)
    if auth_redirect: return auth_redirect
    courses = db.query(Course).all()
    return templates.TemplateResponse("admin_courses.html", {
    "request": request,
    "courses": courses,
    "range": range
})


@router.get("/admin/courses/add", response_class=HTMLResponse)
def course_form(request: Request):
    auth_redirect = require_login(request)
    if auth_redirect: return auth_redirect
    return """
    <h2>Добавить курс</h2>
    <form action="/admin/courses/add" method="post">
        Название: <input name="title"><br>
        Организация: <input name="organization"><br>
        Год: <input name="year"><br>
        <input type="submit" value="Добавить">
    </form>
    """

@router.post("/admin/courses/add")
def add_course(request: Request, title: str = Form(...), organization: str = Form(...), year: str = Form(...), db: Session = Depends(get_db)):
    auth_redirect = require_login(request)
    if auth_redirect: return auth_redirect
    course = Course(title=title, organization=organization, year=year)
    db.add(course)
    db.commit()
    return RedirectResponse(url="/admin/courses", status_code=303)

@router.get("/admin/courses/delete/{id}")
def delete_course(request: Request, id: int, db: Session = Depends(get_db)):
    auth_redirect = require_login(request)
    if auth_redirect: return auth_redirect
    course = db.query(Course).get(id)
    if course:
        db.delete(course)
        db.commit()
    return RedirectResponse(url="/admin/courses", status_code=303)

@router.get("/admin/info", response_class=HTMLResponse)
def edit_info_page(request: Request, db: Session = Depends(get_db)):
    auth_redirect = require_login(request)
    if auth_redirect: return auth_redirect
    infos = {i.field: i.value for i in db.query(Info).all()}
    return templates.TemplateResponse("admin_info.html", {"request": request, "info": infos})


from fastapi import File, UploadFile

@router.post("/admin/info")
async def update_info(
    request: Request,
    name: str = Form(""),
    position: str = Form(""),
    email: str = Form(""),
    phone: str = Form(""),
    telegram: str = Form(""),
    job_search_status: str = Form("none"),
    about: str = Form(""),
    github: str = Form(""),
    linkedin: str = Form(""),
    whatsapp: str = Form(""),
    vkontakte: str = Form(""),
    custom_link: str = Form(""),
    hide_phone: str = Form(None),
    db: Session = Depends(get_db)
):
    auth_redirect = require_login(request)
    if auth_redirect: return auth_redirect

    fields = {
        "name": name,
        "position": position,
        "email": email,
        "phone": phone,
        "telegram": telegram,
        "about": about,
        "github": github,
        "linkedin": linkedin,
        "whatsapp": whatsapp,
        "vkontakte": vkontakte,
        "custom_link": custom_link,
        "hide_phone": "1" if hide_phone == "on" else "0",
        "job_search_status": job_search_status,
    }

    for field, value in fields.items():
        record = db.query(Info).filter(Info.field == field).first()
        if record:
            record.value = value
        else:
            db.add(Info(field=field, value=value))
    db.commit()

    return RedirectResponse(url="/admin/info", status_code=303)


@router.get("/admin/settings", response_class=HTMLResponse)
def show_settings(request: Request, db: Session = Depends(get_db)):
    auth_redirect = require_login(request)
    if auth_redirect: return auth_redirect

    admin = db.query(Admin).first()

    import pyotp, qrcode, io, base64

    if not admin.totp_secret:
        secret = pyotp.random_base32()
        admin.totp_secret = secret
        db.commit()
    else:
        secret = admin.totp_secret

    totp_uri = pyotp.TOTP(secret).provisioning_uri(name=admin.username, issuer_name="CVaaS")
    img = qrcode.make(totp_uri)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    qr_base64 = base64.b64encode(buffer.getvalue()).decode()

    infos = {i.field: i.value for i in db.query(Info).all()}
    json_status = request.session.pop("json_status", None)

    return templates.TemplateResponse("admin_settings.html", {
        "request": request,
        "info": infos,
        "admin": admin,
        "qr_base64": qr_base64,
        "json_success": json_status[1] if json_status and json_status[0] == "success" else None,
        "json_error": json_status[1] if json_status and json_status[0] == "error" else None
    })

@router.post("/admin/change-security-question")
def change_security_question(
    request: Request,
    security_question: str = Form(...),
    security_answer: str = Form(...),
    db: Session = Depends(get_db)
):
    auth_redirect = require_login(request)
    if auth_redirect: return auth_redirect

    admin = db.query(Admin).first()
    if not admin:
        return RedirectResponse("/login", status_code=302)

    if security_question.strip():
        admin.security_question = security_question.strip()

    if security_answer.strip():
        admin.security_answer = security_answer.strip()

    db.commit()

    info = {i.field: i.value for i in db.query(Info).all()}
    response = templates.TemplateResponse("admin_settings.html", {
        "request": request,
        "admin": admin,
        "info": info,
        "question_success": True
    })
    db.close()
    return response


@router.post("/admin/settings")
async def update_settings(request: Request, db: Session = Depends(get_db)):
    auth_redirect = require_login(request)
    if auth_redirect: return auth_redirect

    form = await request.form()

    fields = {
        "template": form.get("template", "classic"),
        "visibility": "public" if form.get("visibility") == "public" else "hidden",
        "hidden_message": form.get("hidden_message", "")
    }

    for field, value in fields.items():
        record = db.query(Info).filter(Info.field == field).first()
        if record:
            record.value = value
        else:
            db.add(Info(field=field, value=value))
    db.commit()

    return RedirectResponse(url="/admin/settings", status_code=303)

@router.post("/admin/change-credentials")
async def change_credentials(
    request: Request,
    current_password: str = Form(...),
    new_username: str = Form(...),
    new_password: str = Form(""),
    confirm_password: str = Form("")
):
    auth_redirect = require_login(request)
    if auth_redirect:
        return auth_redirect

    db = SessionLocal()
    admin = db.query(Admin).first()
    info = {i.field: i.value for i in db.query(Info).all()}

    if not admin:
        db.close()
        return RedirectResponse("/login", status_code=302)

    if not pwd_context.verify(current_password, admin.password_hash):
        response = templates.TemplateResponse("admin_settings.html", {
            "request": request,
            "admin": admin,
            "info": info,
            "cred_error": "❌ Неверный текущий пароль"
        })
        db.close()
        return response

    if new_password and new_password != confirm_password:
        response = templates.TemplateResponse("admin_settings.html", {
            "request": request,
            "admin": admin,
            "info": info,
            "cred_error": "❌ Пароли не совпадают"
        })
        db.close()
        return response

    admin.username = new_username
    if new_password:
        admin.password_hash = pwd_context.hash(new_password)

    db.commit()
    request.session["user"] = new_username

    response = templates.TemplateResponse("admin_settings.html", {
        "request": request,
        "admin": admin,
        "info": info,
        "cred_success": "✅ Данные администратора обновлены"
    })
    db.close()
    return response




@router.get("/admin/skills", response_class=HTMLResponse)
def view_skills(request: Request, db: Session = Depends(get_db)):
    auth_redirect = require_login(request)
    if auth_redirect: return auth_redirect
    skills = db.query(Skill).all()
    last_updated = db.query(Skill).order_by(Skill.updated_at.desc()).first()
    return templates.TemplateResponse("admin_skills.html", {
        "request": request,
        "skills": skills,
        "last_updated": last_updated.updated_at if last_updated else None
    })


@router.post("/admin/skills/add")
def add_skill(request: Request, name: str = Form(...), db: Session = Depends(get_db)):
    auth_redirect = require_login(request)
    if auth_redirect: return auth_redirect
    db.add(Skill(name=name))
    db.commit()
    return RedirectResponse(url="/admin/skills", status_code=303)

@router.get("/admin/skills/delete/{id}")
def delete_skill(request: Request, id: int, db: Session = Depends(get_db)):
    auth_redirect = require_login(request)
    if auth_redirect: return auth_redirect
    skill = db.query(Skill).get(id)
    if skill:
        db.delete(skill)
        db.commit()
    return RedirectResponse(url="/admin/skills", status_code=303)

@router.get("/admin/education", response_class=HTMLResponse)
def view_education(request: Request, db: Session = Depends(get_db)):
    auth_redirect = require_login(request)
    if auth_redirect: return auth_redirect
    educations = db.query(Education).all()
    return templates.TemplateResponse("admin_education.html", {
        "request": request,
        "educations": educations
    })

@router.post("/admin/education/add")
def add_education(
    request: Request,
    degree: str = Form(...),
    institution: str = Form(...),
    start: str = Form(...),
    end: str = Form(...),
    specialization: str = Form(...),
    db: Session = Depends(get_db)
):
    from datetime import datetime
    try:
        start_fmt = datetime.strptime(start, "%Y-%m").strftime("%m.%Y")
        end_fmt = datetime.strptime(end, "%Y-%m").strftime("%m.%Y")
    except ValueError:
        return HTMLResponse("Неверный формат даты", status_code=400)

    edu = Education(
        degree=degree,
        institution=institution,
        start_date=start_fmt,
        end_date=end_fmt,
        specialization=specialization
    )
    db.add(edu)
    db.commit()
    return RedirectResponse(url="/admin/education", status_code=303)

@router.get("/admin/education/delete/{id}")
def delete_education(id: int, request: Request, db: Session = Depends(get_db)):
    auth_redirect = require_login(request)
    if auth_redirect: return auth_redirect
    edu = db.query(Education).get(id)
    if edu:
        db.delete(edu)
        db.commit()
    return RedirectResponse(url="/admin/education", status_code=303)

@router.post("/admin/upload-photo")
async def upload_photo(
    request: Request,
    photo: UploadFile = File(...),
):
    auth_redirect = require_login(request)
    if auth_redirect: return auth_redirect

    if photo and photo.filename:
        content = await photo.read()
        Path("static/uploads/photo.jpg").write_bytes(content)

    return RedirectResponse(url="/admin/info", status_code=303)


@router.get("/admin/languages", response_class=HTMLResponse)
def view_languages(request: Request, db: Session = Depends(get_db)):
    auth_redirect = require_login(request)
    if auth_redirect: return auth_redirect
    langs = db.query(Language).all()
    levels = ["A1 — Начальный", "A2 — Элементарный", "B1 — Средний", "B2 — Выше среднего", "C1 — Продвинутый", "Родной"]
    return templates.TemplateResponse("admin_languages.html", {
        "request": request,
        "languages": langs,
        "levels": levels
    })

@router.post("/admin/languages/add")
def add_language(
    request: Request,
    name: str = Form(...),
    level: str = Form(...),
    db: Session = Depends(get_db)
):
    auth_redirect = require_login(request)
    if auth_redirect: return auth_redirect

    db.add(Language(name=name, level=level))
    db.commit()
    return RedirectResponse(url="/admin/languages", status_code=303)

@router.get("/admin/languages/delete/{id}")
def delete_language(id: int, request: Request, db: Session = Depends(get_db)):
    auth_redirect = require_login(request)
    if auth_redirect: return auth_redirect
    lang = db.query(Language).get(id)
    if lang:
        db.delete(lang)
        db.commit()
    return RedirectResponse(url="/admin/languages", status_code=303)


@router.get("/admin/projects", response_class=HTMLResponse)
def view_projects(request: Request, db: Session = Depends(get_db)):
    auth_redirect = require_login(request)
    if auth_redirect: return auth_redirect
    projects = db.query(Project).all()
    return templates.TemplateResponse("admin_projects.html", {
        "request": request,
        "projects": projects
    })

@router.post("/admin/projects/add")
def add_project(
    request: Request,
    title: str = Form(...),
    description: str = Form(...),
    link: str = Form(""),
    stack: str = Form(""),
    db: Session = Depends(get_db)
):
    auth_redirect = require_login(request)
    if auth_redirect: return auth_redirect
    if link and not link.startswith("http"):
        link = "https://" + link
    db.add(Project(title=title, description=description, link=link, stack=stack))
    db.commit()
    return RedirectResponse(url="/admin/projects", status_code=303)

@router.get("/admin/projects/delete/{id}")
def delete_project(id: int, request: Request, db: Session = Depends(get_db)):
    auth_redirect = require_login(request)
    if auth_redirect: return auth_redirect
    project = db.query(Project).get(id)
    if project:
        db.delete(project)
        db.commit()
    return RedirectResponse(url="/admin/projects", status_code=303)


@router.get("/admin/certificates", response_class=HTMLResponse)
def view_certificates(request: Request, db: Session = Depends(get_db)):
    auth_redirect = require_login(request)
    if auth_redirect: return auth_redirect
    certificates = db.query(Certificate).all()
    return templates.TemplateResponse("admin_certificates.html", {
        "request": request,
        "certificates": certificates
    })

@router.post("/admin/certificates/add")
def add_certificate(
    request: Request,
    title: str = Form(...),
    issuer: str = Form(...),
    year: int = Form(...),
    link: str = Form(""),
    file: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    auth_redirect = require_login(request)
    if auth_redirect: return auth_redirect

    file_path = ""
    if file:
        dest = f"static/uploads/certificates/{file.filename}"
        with open(dest, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        file_path = "/" + dest

    cert = Certificate(title=title, issuer=issuer, year=year, link=link or None, file_path=file_path or None)
    db.add(cert)
    db.commit()
    return RedirectResponse(url="/admin/certificates", status_code=303)

@router.get("/admin/certificates/delete/{id}")
def delete_certificate(id: int, request: Request, db: Session = Depends(get_db)):
    auth_redirect = require_login(request)
    if auth_redirect: return auth_redirect
    cert = db.query(Certificate).get(id)
    if cert:
        if cert.file_path and os.path.exists(cert.file_path[1:]):
            os.remove(cert.file_path[1:])
        db.delete(cert)
        db.commit()
    return RedirectResponse(url="/admin/certificates", status_code=303)

@router.get("/admin/recommendations", response_class=HTMLResponse)
def view_recommendations(request: Request, db: Session = Depends(get_db)):
    auth_redirect = require_login(request)
    if auth_redirect: return auth_redirect
    recs = db.query(Recommendation).all()
    return templates.TemplateResponse("admin_recommendations.html", {
        "request": request,
        "recommendations": recs
    })

@router.post("/admin/recommendations/add")
def add_recommendation(
    request: Request,
    name: str = Form(...),
    company: str = Form(...),
    quote: str = Form(...),
    db: Session = Depends(get_db)
):
    auth_redirect = require_login(request)
    if auth_redirect: return auth_redirect

    r = Recommendation(name=name, company=company, quote=quote)
    db.add(r)
    db.commit()
    return RedirectResponse(url="/admin/recommendations", status_code=303)

@router.get("/admin/recommendations/delete/{id}")
def delete_recommendation(id: int, request: Request, db: Session = Depends(get_db)):
    auth_redirect = require_login(request)
    if auth_redirect: return auth_redirect
    r = db.query(Recommendation).get(id)
    if r:
        db.delete(r)
        db.commit()
    return RedirectResponse(url="/admin/recommendations", status_code=303)



