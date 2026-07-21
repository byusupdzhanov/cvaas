from fastapi import APIRouter, Depends, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from .database import SessionLocal, pwd_context
from .auth import require_login
from .models import Experience, Course, Skill, Info, Education, Language, Project, Certificate, Recommendation, Admin
from fastapi.templating import Jinja2Templates
templates = Jinja2Templates(directory="templates")
from datetime import datetime
import os
import tempfile
import json
import zipfile
import io
from pathlib import Path
import pyotp 
import secrets
from jinja2 import pass_context
from .security import (
    ALLOWED_SALARY_CURRENCIES,
    MAX_CERTIFICATE_BYTES,
    MAX_IMPORT_JSON_BYTES,
    MAX_PHOTO_BYTES,
    enforce_csrf_protection,
    get_csrf_token,
    normalize_text,
    normalize_url,
    read_limited_upload,
    save_certificate_file,
    save_profile_photo,
)
from .i18n import get_locale_from_db, get_locale_from_info, normalize_locale, translate

router = APIRouter(dependencies=[Depends(enforce_csrf_protection)])

MONTH_OPTIONS = [
    ("01", "Январь"),
    ("02", "Февраль"),
    ("03", "Март"),
    ("04", "Апрель"),
    ("05", "Май"),
    ("06", "Июнь"),
    ("07", "Июль"),
    ("08", "Август"),
    ("09", "Сентябрь"),
    ("10", "Октябрь"),
    ("11", "Ноябрь"),
    ("12", "Декабрь"),
]

YEAR_OPTIONS = [str(year) for year in range(datetime.now().year + 2, 1969, -1)]


def build_year_options(start_year: int = 1970):
    return [str(year) for year in range(datetime.now().year + 2, start_year - 1, -1)]


def split_year_month(value: str | None):
    if not value:
        return "", ""

    normalized = value.strip()

    if len(normalized) == 7 and normalized[4] == "-":
        year, month = normalized.split("-")
        return year, month

    if len(normalized) == 7 and normalized[2] == ".":
        month, year = normalized.split(".")
        return year, month

    return "", ""


def combine_year_month(year: str | None, month: str | None, *, required: bool = False):
    year_value = (year or "").strip()
    month_value = (month or "").strip()

    if not year_value and not month_value and not required:
        return None

    if not year_value or not month_value:
        raise ValueError("Укажите месяц и год")

    datetime.strptime(f"{year_value}-{month_value}", "%Y-%m")
    return f"{year_value}-{month_value}"


def format_period(start_value: str, end_value: str | None = None, current: bool = False):
    start_fmt = datetime.strptime(start_value, "%Y-%m").strftime("%m.%Y")
    if current:
        return f"{start_fmt} — н.в."
    if end_value:
        end_fmt = datetime.strptime(end_value, "%Y-%m").strftime("%m.%Y")
        return f"{start_fmt} — {end_fmt}"
    return start_fmt


def get_next_position(db: Session, model):
    current = db.query(func.max(model.position)).scalar()
    return (current or 0) + 1


def move_item(db: Session, model, item_id: int, direction: str):
    item = db.query(model).filter_by(id=item_id).first()
    if not item:
        return False

    comparator = model.position < item.position if direction == "up" else model.position > item.position
    order_clause = model.position.desc() if direction == "up" else model.position.asc()

    swap_target = (
        db.query(model)
        .filter(comparator)
        .order_by(order_clause)
        .first()
    )

    if not swap_target:
        return False

    item.position, swap_target.position = swap_target.position, item.position
    db.commit()
    return True


def build_dashboard_readiness(info: dict[str, str], stats: dict[str, int]):
    profile_checks = [
        {
            "label": "Имя и позиция заполнены",
            "done": bool(info.get("name") and info.get("position")),
            "href": "/admin/info",
        },
        {
            "label": "Добавлено краткое описание профиля",
            "done": bool(info.get("about") and len(info.get("about", "").strip()) >= 80),
            "href": "/admin/info",
        },
        {
            "label": "Есть минимум один контакт",
            "done": any(info.get(key) for key in ["email", "phone", "telegram", "linkedin", "github", "whatsapp"]),
            "href": "/admin/info",
        },
        {
            "label": "Загружена фотография",
            "done": Path("static/uploads/photo.jpg").exists(),
            "href": "/admin/info",
        },
        {
            "label": "Добавлен опыт работы",
            "done": stats["experience"] > 0,
            "href": "/admin/add",
        },
        {
            "label": "Добавлены ключевые навыки",
            "done": stats["skills"] >= 3,
            "href": "/admin/skills",
        },
        {
            "label": "Заполнен хотя бы один дополнительный блок",
            "done": any(stats[key] > 0 for key in ["projects", "certificates", "recommendations", "courses"]),
            "href": "/admin/projects",
        },
        {
            "label": "Резюме открыто для публикации",
            "done": info.get("visibility", "public") == "public",
            "href": "/admin/settings",
        },
    ]

    completed = sum(1 for item in profile_checks if item["done"])
    total = len(profile_checks)
    percent = int(round((completed / total) * 100)) if total else 0

    blockers = [item for item in profile_checks if not item["done"]]
    suggestions = []

    if stats["experience"] and stats["projects"] == 0:
        suggestions.append("Добавь проекты: они усиливают опыт и показывают конкретный результат.")
    if stats["skills"] and stats["languages"] == 0:
        suggestions.append("Если язык правда есть, заполни блок языков: рекрутеры это быстро считывают.")
    if info.get("salary_expectation") and not info.get("location"):
        suggestions.append("Есть зарплатная вилка, но нет географии. Добавь город или формат работы.")
    if stats["recommendations"] == 0:
        suggestions.append("Рекомендации не обязательны, но одна сильная рекомендация повышает доверие.")

    is_ready = completed >= 6 and stats["experience"] > 0 and stats["skills"] >= 3 and bool(info.get("about"))
    status_label = "Готово к публикации" if is_ready else "Нужно допилить"

    return {
        "items": profile_checks,
        "completed": completed,
        "total": total,
        "percent": percent,
        "is_ready": is_ready,
        "status_label": status_label,
        "blockers": blockers,
        "suggestions": suggestions[:3],
    }


def build_publication_state(info: dict[str, str], stats: dict[str, int]):
    visibility = info.get("visibility", "public")
    is_public = visibility == "public"
    hidden_message = info.get("hidden_message", "").strip()

    blockers = []
    if not info.get("name") or not info.get("position"):
        blockers.append("Не заполнены имя или позиция.")
    if not info.get("about"):
        blockers.append("Нет блока «Обо мне».")
    if stats["experience"] == 0:
        blockers.append("Не добавлен опыт работы.")
    if not any(info.get(key) for key in ["email", "phone", "telegram", "linkedin", "github", "whatsapp"]):
        blockers.append("Не добавлен ни один контакт.")

    return {
        "is_public": is_public,
        "status_label": "Опубликовано" if is_public else "Скрыто",
        "status_copy": (
            "Посетитель видит публичное резюме по ссылке."
            if is_public
            else "Посетитель видит сообщение о том, что резюме скрыто."
        ),
        "hidden_message": hidden_message or "Резюме временно скрыто владельцем.",
        "blockers": blockers,
        "has_blockers": len(blockers) > 0,
    }


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def set_flash(request: Request, message: str, kind: str = "success"):
    request.session["_admin_flash"] = {
        "message": message,
        "kind": kind,
    }


def consume_flash(request: Request):
    return request.session.pop("_admin_flash", None)


def admin_template(
    request: Request,
    template_name: str,
    context: dict | None = None,
    status_code: int = 200,
):
    db = SessionLocal()
    try:
        locale = get_locale_from_db(db)
    finally:
        db.close()
    payload = {
        "request": request,
        "flash": consume_flash(request),
        "csrf_token": get_csrf_token(request),
        "locale": locale,
        "_": lambda text, **kwargs: translate(locale, text, **kwargs),
    }
    if context:
        payload.update(context)
    return templates.TemplateResponse(template_name, payload, status_code=status_code)

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

    info = {item.field: item.value for item in db.query(Info).all()}
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
    readiness = build_dashboard_readiness(info, stats)

    return admin_template(request, "admin_dashboard.html", {
        "stats": stats,
        "resume_updated": resume_updated,
        "readiness": readiness,
        "info": info,
    })

@router.post("/admin/reset")
def reset_resume(request: Request, db: Session = Depends(get_db)):
    auth_redirect = require_login(request)
    if auth_redirect: return auth_redirect

    for model in [Experience, Skill, Info, Course, Education, Language, Project, Certificate, Recommendation]:
        db.query(model).delete()

    db.commit()
    set_flash(request, "Резюме полностью обнулено.")
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
    return admin_template(request, "admin_import_json.html")


@router.post("/admin/import-json")
async def import_json(
    request: Request,
    json_file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    auth_redirect = require_login(request)
    if auth_redirect: return auth_redirect

    try:
        if not (json_file.filename or "").lower().endswith(".json"):
            raise ValueError
        content = await read_limited_upload(json_file, MAX_IMPORT_JSON_BYTES)
        data = json.loads(content.decode("utf-8"))
    except Exception:
        return admin_template(request, "admin_import_json.html", {
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
        "skills": ["name", "level"],
        "experience": ["company", "location", "role", "period", "description", "start_date", "end_date"],
        "courses": ["title", "organization", "year"],
        "educations": ["degree", "institution", "location", "start_date", "end_date", "specialization"],
        "languages": ["name", "level"],
        "projects": ["title", "description", "link", "stack", "position"],
        "certificates": ["title", "issuer", "year", "file_path", "link"],
        "recommendations": ["name", "company", "quote", "position"]
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

    return admin_template(request, "admin_import_json.html", {
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
        set_flash(request, "Запись опыта удалена.")
    return RedirectResponse("/admin/experience", status_code=303)




@router.get("/admin/edit/{id}", response_class=HTMLResponse)
def edit_experience_form(id: int, request: Request, db: Session = Depends(get_db)):
    auth_redirect = require_login(request)
    if auth_redirect: return auth_redirect
    exp = db.query(Experience).get(id)
    if not exp:
        return HTMLResponse(content="Не найдено", status_code=404)
    return admin_template(request, "admin_experience_edit.html", {
        "exp": exp,
        "months": MONTH_OPTIONS,
        "years": YEAR_OPTIONS,
    })

@router.post("/admin/edit/{id}")
def edit_experience(
    id: int,
    request: Request,
    company: str = Form(...),
    location: str = Form(""),
    role: str = Form(...),
    start_month: str = Form(...),
    start_year: str = Form(...),
    end_month: str = Form(""),
    end_year: str = Form(""),
    current: str = Form(None),
    description: str = Form(...),
    db: Session = Depends(get_db)
):
    auth_redirect = require_login(request)
    if auth_redirect: return auth_redirect
    exp = db.query(Experience).get(id)
    if not exp:
        return HTMLResponse("Опыт не найден", status_code=404)

    try:
        start = combine_year_month(start_year, start_month, required=True)
        end = None if current else combine_year_month(end_year, end_month)
    except ValueError:
        return HTMLResponse("Неверный формат даты", status_code=400)

    period = format_period(start, end, bool(current))

    exp.company = company
    exp.location = location
    exp.role = role
    exp.period = period
    exp.description = description
    exp.start_date = start
    exp.end_date = None if current else end
    db.commit()
    set_flash(request, "Запись опыта обновлена.")
    return RedirectResponse(url="/admin/add", status_code=303)




@router.get("/admin/add", response_class=HTMLResponse)
def form_add_experience(request: Request, db: Session = Depends(get_db)):
    auth_redirect = require_login(request)
    if auth_redirect: return auth_redirect
    experiences = db.query(Experience).order_by(Experience.start_date.desc()).all()
    return admin_template(request, "admin_experience_add.html", {
        "experiences": experiences,
        "months": MONTH_OPTIONS,
        "years": YEAR_OPTIONS,
    })


@router.post("/admin/add")
def add_experience(request: Request,
    company: str = Form(...),
    location: str = Form(""),
    role: str = Form(...),
    start_month: str = Form(...),
    start_year: str = Form(...),
    end_month: str = Form(""),
    end_year: str = Form(""),
    current: str = Form(None),
    description: str = Form(...),
    db: Session = Depends(get_db),
):
    auth_redirect = require_login(request)
    if auth_redirect: return auth_redirect

    try:
        start = combine_year_month(start_year, start_month, required=True)
        end = None if current else combine_year_month(end_year, end_month)
    except ValueError:
        return HTMLResponse("Неверный формат даты", status_code=400)

    period = format_period(start, end, bool(current))

    exp = Experience(
    company=company,
    location=location,
    role=role,
    period=period,
    description=description,
    start_date=start,
    end_date=None if current else end
    )
    db.add(exp)
    db.commit()
    set_flash(request, "Опыт работы добавлен.")
    return RedirectResponse(url="/admin/add", status_code=303)


@router.post("/admin/delete/{id}")
def delete_experience(request: Request, id: int, db: Session = Depends(get_db)):
    auth_redirect = require_login(request)
    if auth_redirect: return auth_redirect
    exp = db.query(Experience).get(id)
    if exp:
        db.delete(exp)
        db.commit()
        set_flash(request, "Запись опыта удалена.")
    return RedirectResponse(url="/admin/add", status_code=303)

@router.get("/recover", response_class=HTMLResponse)
def recover_form(request: Request, db: Session = Depends(get_db)):
    admin = db.query(Admin).first()
    question = admin.security_question if admin else "Где вы родились?"
    locale = get_locale_from_db(db)
    return templates.TemplateResponse("recover.html", {
        "request": request,
        "question": question,
        "admin": admin,
        "csrf_token": get_csrf_token(request),
        "locale": locale,
        "_": lambda text, **kwargs: translate(locale, text, **kwargs),
    })

@router.post("/recover", response_class=HTMLResponse)
async def recover_post(
    request: Request,
    answer: str = Form(...),
    totp: str = Form(...),
    db: Session = Depends(get_db)
):
    admin = db.query(Admin).first()
    locale = get_locale_from_db(db)
    if not admin or not admin.security_answer or admin.security_answer.strip().lower() != answer.strip().lower():
        return templates.TemplateResponse("recover.html", {
            "request": request,
            "csrf_token": get_csrf_token(request),
            "error": "Неверный ответ на контрольный вопрос"
            ,
            "locale": locale,
            "_": lambda text, **kwargs: translate(locale, text, **kwargs),
        })

    if admin.twofa_enabled:
        totp_obj = pyotp.TOTP(admin.totp_secret)
        if not totp_obj.verify(totp):
            return templates.TemplateResponse("recover.html", {
                "request": request,
                "csrf_token": get_csrf_token(request),
                "error": "Неверный код 2FA"
                ,
                "locale": locale,
                "_": lambda text, **kwargs: translate(locale, text, **kwargs),
            })

    new_password = secrets.token_urlsafe(10)
    admin.password_hash = pwd_context.hash(new_password)
    db.commit()

    return templates.TemplateResponse("recover_success.html", {
        "request": request,
        "username": admin.username,
        "password": new_password,
        "locale": locale,
        "_": lambda text, **kwargs: translate(locale, text, **kwargs),
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
        set_flash(request, "Не удалось подготовить 2FA. Попробуй еще раз.", "error")
        return RedirectResponse("/admin/settings", status_code=303)

    totp = pyotp.TOTP(admin.totp_secret)

    if totp.verify(code.strip()):
        admin.twofa_enabled = True
        db.commit()
        set_flash(request, "Двухфакторная защита включена.")
        return RedirectResponse("/admin/settings", status_code=303)
    else:
        set_flash(request, "Неверный код 2FA. Попробуй еще раз.", "error")
        return RedirectResponse("/admin/settings", status_code=303)
    
@router.post("/admin/disable-2fa")
def disable_2fa(request: Request, db: Session = Depends(get_db)):
    auth_redirect = require_login(request)
    if auth_redirect: return auth_redirect

    admin = db.query(Admin).first()
    if admin:
        admin.twofa_enabled = False
        admin.totp_secret = None
        db.commit()
        set_flash(request, "2FA отключена.")

    return RedirectResponse("/admin/settings", status_code=303)


@router.get("/admin/courses", response_class=HTMLResponse)
def course_list(request: Request, db: Session = Depends(get_db)):
    auth_redirect = require_login(request)
    if auth_redirect: return auth_redirect
    courses = db.query(Course).all()
    return admin_template(request, "admin_courses.html", {
    "courses": courses,
    "range": range
})


@router.get("/admin/courses/add", response_class=HTMLResponse)
def course_form(request: Request):
    auth_redirect = require_login(request)
    if auth_redirect: return auth_redirect
    return RedirectResponse(url="/admin/courses", status_code=303)

@router.post("/admin/courses/add")
def add_course(request: Request, title: str = Form(...), organization: str = Form(...), year: str = Form(...), db: Session = Depends(get_db)):
    auth_redirect = require_login(request)
    if auth_redirect: return auth_redirect
    course = Course(title=title, organization=organization, year=year)
    db.add(course)
    db.commit()
    set_flash(request, "Курс добавлен.")
    return RedirectResponse(url="/admin/courses", status_code=303)

@router.post("/admin/courses/delete/{id}")
def delete_course(request: Request, id: int, db: Session = Depends(get_db)):
    auth_redirect = require_login(request)
    if auth_redirect: return auth_redirect
    course = db.query(Course).get(id)
    if course:
        db.delete(course)
        db.commit()
        set_flash(request, "Курс удален.")
    return RedirectResponse(url="/admin/courses", status_code=303)

@router.get("/admin/info", response_class=HTMLResponse)
def edit_info_page(request: Request, db: Session = Depends(get_db)):
    auth_redirect = require_login(request)
    if auth_redirect: return auth_redirect
    infos = {i.field: i.value for i in db.query(Info).all()}
    photo_path = Path("static/uploads/photo.jpg")
    return admin_template(request, "admin_info.html", {
        "info": infos,
        "photo": photo_path.exists(),
        "photo_version": int(photo_path.stat().st_mtime) if photo_path.exists() else None,
    })


from fastapi import File, UploadFile

@router.post("/admin/info")
async def update_info(
    request: Request,
    name: str = Form(""),
    position: str = Form(""),
    location: str = Form(""),
    salary_expectation: str = Form(""),
    salary_currency: str = Form("rub"),
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

    try:
        salary_currency = salary_currency if salary_currency in ALLOWED_SALARY_CURRENCIES else "rub"
        fields = {
        "name": normalize_text(name, max_length=160),
        "position": normalize_text(position, max_length=160),
        "email": normalize_text(email, max_length=160),
        "phone": normalize_text(phone, max_length=80),
        "salary_expectation": normalize_text(salary_expectation, max_length=80),
        "salary_currency": salary_currency,
        "telegram": normalize_url(telegram) if telegram else "",
        "about": normalize_text(about, max_length=4000),
        "github": normalize_url(github) if github else "",
        "linkedin": normalize_url(linkedin) if linkedin else "",
        "whatsapp": normalize_url(whatsapp) if whatsapp else "",
        "vkontakte": normalize_url(vkontakte) if vkontakte else "",
        "custom_link": normalize_url(custom_link) if custom_link else "",
        "hide_phone": "1" if hide_phone == "on" else "0",
        "job_search_status": normalize_text(job_search_status, max_length=32),
        "location": normalize_text(location, max_length=160),
        }
    except ValueError as error:
        set_flash(request, str(error), "error")
        return RedirectResponse(url="/admin/info", status_code=303)

    for field, value in fields.items():
        record = db.query(Info).filter(Info.field == field).first()
        if record:
            record.value = value
        else:
            db.add(Info(field=field, value=value))
    db.commit()
    set_flash(request, "Публичный профиль сохранен.")
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
    stats = {
        "experience": db.query(Experience).count(),
        "skills": db.query(Skill).count(),
        "education": db.query(Education).count(),
        "courses": db.query(Course).count(),
        "languages": db.query(Language).count(),
        "projects": db.query(Project).count(),
        "certificates": db.query(Certificate).count(),
        "recommendations": db.query(Recommendation).count(),
    }
    return admin_template(request, "admin_settings.html", {
        "info": infos,
        "admin": admin,
        "qr_base64": qr_base64,
        "publication": build_publication_state(infos, stats),
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
    set_flash(request, "Контрольный вопрос обновлен.")
    return RedirectResponse(url="/admin/settings", status_code=303)


@router.post("/admin/settings")
async def update_settings(request: Request, db: Session = Depends(get_db)):
    auth_redirect = require_login(request)
    if auth_redirect: return auth_redirect

    form = await request.form()
    existing_info = {i.field: i.value for i in db.query(Info).all()}
    visibility_action = form.get("visibility_action")
    visibility_value = existing_info.get("visibility", "public")

    if visibility_action in {"public", "hidden"}:
        visibility_value = visibility_action

    fields = {
        "template": form.get("template", existing_info.get("template", "classic")),
        "visibility": visibility_value,
        "hidden_message": form.get("hidden_message", existing_info.get("hidden_message", "")),
        "locale": normalize_locale(form.get("locale", existing_info.get("locale", "ru"))),
    }

    for field, value in fields.items():
        record = db.query(Info).filter(Info.field == field).first()
        if record:
            record.value = value
        else:
            db.add(Info(field=field, value=value))
    db.commit()

    stats = {
        "experience": db.query(Experience).count(),
        "skills": db.query(Skill).count(),
        "education": db.query(Education).count(),
        "courses": db.query(Course).count(),
        "languages": db.query(Language).count(),
        "projects": db.query(Project).count(),
        "certificates": db.query(Certificate).count(),
        "recommendations": db.query(Recommendation).count(),
    }
    publication = build_publication_state(
        {**existing_info, **fields},
        stats,
    )

    if visibility_action == "public":
        if publication["has_blockers"]:
            set_flash(
                request,
                "Резюме опубликовано, но еще есть базовые пробелы: " + " ".join(publication["blockers"][:2]),
                "warning",
            )
        else:
            set_flash(request, "Резюме опубликовано.")
    elif visibility_action == "hidden":
        set_flash(request, "Резюме скрыто.")
    else:
        set_flash(request, "Настройки публикации сохранены.")
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
        response = admin_template(request, "admin_settings.html", {
            "admin": admin,
            "info": info,
            "cred_error": "❌ Неверный текущий пароль"
        })
        db.close()
        return response

    if new_password and new_password != confirm_password:
        response = admin_template(request, "admin_settings.html", {
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

    response = admin_template(request, "admin_settings.html", {
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
    skills = db.query(Skill).order_by(Skill.level.desc(), Skill.name.asc()).all()
    last_updated = db.query(Skill).order_by(Skill.updated_at.desc()).first()
    return admin_template(request, "admin_skills.html", {
        "skills": skills,
        "last_updated": last_updated.updated_at if last_updated else None
    })


@router.post("/admin/skills/add")
def add_skill(request: Request, name: str = Form(...), level: int = Form(3), db: Session = Depends(get_db)):
    auth_redirect = require_login(request)
    if auth_redirect: return auth_redirect
    db.add(Skill(name=name, level=max(1, min(level, 5))))
    db.commit()
    set_flash(request, "Навык добавлен.")
    return RedirectResponse(url="/admin/skills", status_code=303)

@router.post("/admin/skills/update/{id}")
def update_skill(id: int, request: Request, level: int = Form(3), db: Session = Depends(get_db)):
    auth_redirect = require_login(request)
    if auth_redirect:
        return auth_redirect

    skill = db.query(Skill).get(id)
    if skill:
        skill.level = max(1, min(level, 5))
        db.commit()
        set_flash(request, "Уровень навыка обновлен.")
    return RedirectResponse(url="/admin/skills", status_code=303)

@router.post("/admin/skills/delete/{id}")
def delete_skill(request: Request, id: int, db: Session = Depends(get_db)):
    auth_redirect = require_login(request)
    if auth_redirect: return auth_redirect
    skill = db.query(Skill).get(id)
    if skill:
        db.delete(skill)
        db.commit()
        set_flash(request, "Навык удален.")
    return RedirectResponse(url="/admin/skills", status_code=303)

@router.get("/admin/education", response_class=HTMLResponse)
def view_education(request: Request, db: Session = Depends(get_db)):
    auth_redirect = require_login(request)
    if auth_redirect: return auth_redirect
    educations = db.query(Education).all()
    return admin_template(request, "admin_education.html", {
        "educations": educations,
        "months": MONTH_OPTIONS,
        "years": YEAR_OPTIONS,
    })

@router.post("/admin/education/add")
def add_education(
    request: Request,
    degree: str = Form(...),
    institution: str = Form(...),
    start_month: str = Form(...),
    start_year: str = Form(...),
    end_month: str = Form(...),
    end_year: str = Form(...),
    specialization: str = Form(...),
    db: Session = Depends(get_db)
):
    try:
        start_value = combine_year_month(start_year, start_month, required=True)
        end_value = combine_year_month(end_year, end_month, required=True)
        start_fmt = datetime.strptime(start_value, "%Y-%m").strftime("%m.%Y")
        end_fmt = datetime.strptime(end_value, "%Y-%m").strftime("%m.%Y")
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
    set_flash(request, "Образование добавлено.")
    return RedirectResponse(url="/admin/education", status_code=303)

@router.post("/admin/education/delete/{id}")
def delete_education(id: int, request: Request, db: Session = Depends(get_db)):
    auth_redirect = require_login(request)
    if auth_redirect: return auth_redirect
    edu = db.query(Education).get(id)
    if edu:
        db.delete(edu)
        db.commit()
        set_flash(request, "Запись об образовании удалена.")
    return RedirectResponse(url="/admin/education", status_code=303)

@router.post("/admin/upload-photo")
async def upload_photo(
    request: Request,
    photo: UploadFile = File(...),
):
    auth_redirect = require_login(request)
    if auth_redirect: return auth_redirect

    if photo and photo.filename:
        try:
            content = await read_limited_upload(photo, MAX_PHOTO_BYTES)
            save_profile_photo(content, Path("static/uploads/photo.jpg"))
        except ValueError as error:
            set_flash(request, str(error), "error")
            return RedirectResponse(url="/admin/info", status_code=303)
        set_flash(request, "Фотография обновлена.")
    else:
        set_flash(request, "Не удалось загрузить фотографию.", "error")
    return RedirectResponse(url="/admin/info", status_code=303)


@router.get("/admin/languages", response_class=HTMLResponse)
def view_languages(request: Request, db: Session = Depends(get_db)):
    auth_redirect = require_login(request)
    if auth_redirect: return auth_redirect
    langs = db.query(Language).all()
    levels = ["A1 — Начальный", "A2 — Элементарный", "B1 — Средний", "B2 — Выше среднего", "C1 — Продвинутый", "Родной"]
    return admin_template(request, "admin_languages.html", {
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
    set_flash(request, "Язык добавлен.")
    return RedirectResponse(url="/admin/languages", status_code=303)

@router.post("/admin/languages/delete/{id}")
def delete_language(id: int, request: Request, db: Session = Depends(get_db)):
    auth_redirect = require_login(request)
    if auth_redirect: return auth_redirect
    lang = db.query(Language).get(id)
    if lang:
        db.delete(lang)
        db.commit()
        set_flash(request, "Язык удален.")
    return RedirectResponse(url="/admin/languages", status_code=303)


@router.get("/admin/projects", response_class=HTMLResponse)
def view_projects(request: Request, db: Session = Depends(get_db)):
    auth_redirect = require_login(request)
    if auth_redirect: return auth_redirect
    projects = db.query(Project).order_by(Project.position.asc(), Project.id.asc()).all()
    return admin_template(request, "admin_projects.html", {
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
    try:
        link = normalize_url(link) if link else ""
    except ValueError as error:
        set_flash(request, str(error), "error")
        return RedirectResponse(url="/admin/projects", status_code=303)
    db.add(Project(
        title=normalize_text(title, max_length=180),
        description=normalize_text(description, max_length=3000),
        link=link,
        stack=normalize_text(stack, max_length=500),
        position=get_next_position(db, Project),
    ))
    db.commit()
    set_flash(request, "Проект добавлен.")
    return RedirectResponse(url="/admin/projects", status_code=303)

@router.post("/admin/projects/move/{id}/{direction}")
def move_project(id: int, direction: str, request: Request, db: Session = Depends(get_db)):
    auth_redirect = require_login(request)
    if auth_redirect:
        return auth_redirect

    if direction in {"up", "down"} and move_item(db, Project, id, direction):
        set_flash(request, "Порядок проектов обновлен.")
    return RedirectResponse(url="/admin/projects", status_code=303)

@router.post("/admin/projects/delete/{id}")
def delete_project(id: int, request: Request, db: Session = Depends(get_db)):
    auth_redirect = require_login(request)
    if auth_redirect: return auth_redirect
    project = db.query(Project).get(id)
    if project:
        db.delete(project)
        db.commit()
        set_flash(request, "Проект удален.")
    return RedirectResponse(url="/admin/projects", status_code=303)


@router.get("/admin/certificates", response_class=HTMLResponse)
def view_certificates(request: Request, db: Session = Depends(get_db)):
    auth_redirect = require_login(request)
    if auth_redirect: return auth_redirect
    certificates = db.query(Certificate).all()
    return admin_template(request, "admin_certificates.html", {
        "certificates": certificates,
        "certificate_years": build_year_options(1980),
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

    try:
        link = normalize_url(link) if link else ""
        file_path = ""
        if file and file.filename:
            content = file.file.read(MAX_CERTIFICATE_BYTES + 1)
            if len(content) > MAX_CERTIFICATE_BYTES:
                raise ValueError("Файл сертификата слишком большой")
            file_path = save_certificate_file(content, file.filename, Path("static/uploads/certificates"))
    except ValueError as error:
        set_flash(request, str(error), "error")
        return RedirectResponse(url="/admin/certificates", status_code=303)

    cert = Certificate(
        title=normalize_text(title, max_length=180),
        issuer=normalize_text(issuer, max_length=180),
        year=year,
        link=link or None,
        file_path=file_path or None,
    )
    db.add(cert)
    db.commit()
    set_flash(request, "Сертификат добавлен.")
    return RedirectResponse(url="/admin/certificates", status_code=303)

@router.post("/admin/certificates/delete/{id}")
def delete_certificate(id: int, request: Request, db: Session = Depends(get_db)):
    auth_redirect = require_login(request)
    if auth_redirect: return auth_redirect
    cert = db.query(Certificate).get(id)
    if cert:
        if cert.file_path and os.path.exists(cert.file_path[1:]):
            os.remove(cert.file_path[1:])
        db.delete(cert)
        db.commit()
        set_flash(request, "Сертификат удален.")
    return RedirectResponse(url="/admin/certificates", status_code=303)

@router.get("/admin/recommendations", response_class=HTMLResponse)
def view_recommendations(request: Request, db: Session = Depends(get_db)):
    auth_redirect = require_login(request)
    if auth_redirect: return auth_redirect
    recs = db.query(Recommendation).order_by(Recommendation.position.asc(), Recommendation.id.asc()).all()
    return admin_template(request, "admin_recommendations.html", {
        "recommendations": recs
    })

@router.post("/admin/recommendations/add")
def add_recommendation(
    request: Request,
    name: str = Form(...),
    company: str = Form(...),
    quote: str = Form(""),
    without_text: str = Form(None),
    db: Session = Depends(get_db)
):
    auth_redirect = require_login(request)
    if auth_redirect: return auth_redirect

    r = Recommendation(
        name=name,
        company=company,
        quote="" if without_text == "on" else quote,
        position=get_next_position(db, Recommendation),
    )
    db.add(r)
    db.commit()
    set_flash(request, "Рекомендация добавлена.")
    return RedirectResponse(url="/admin/recommendations", status_code=303)

@router.post("/admin/recommendations/move/{id}/{direction}")
def move_recommendation(id: int, direction: str, request: Request, db: Session = Depends(get_db)):
    auth_redirect = require_login(request)
    if auth_redirect:
        return auth_redirect

    if direction in {"up", "down"} and move_item(db, Recommendation, id, direction):
        set_flash(request, "Порядок рекомендаций обновлен.")
    return RedirectResponse(url="/admin/recommendations", status_code=303)

@router.post("/admin/recommendations/delete/{id}")
def delete_recommendation(id: int, request: Request, db: Session = Depends(get_db)):
    auth_redirect = require_login(request)
    if auth_redirect: return auth_redirect
    r = db.query(Recommendation).get(id)
    if r:
        db.delete(r)
        db.commit()
        set_flash(request, "Рекомендация удалена.")
    return RedirectResponse(url="/admin/recommendations", status_code=303)
