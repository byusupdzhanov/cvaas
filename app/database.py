from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from .models import Base, Admin
from passlib.context import CryptContext
import os

SQLALCHEMY_DATABASE_URL = "sqlite:///./resume.db"

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def init_db():
    Base.metadata.create_all(bind=engine)
    ensure_sqlite_columns()


def ensure_sqlite_columns():
    with engine.begin() as connection:
        existing_columns = {
            row[1]
            for row in connection.execute(text("PRAGMA table_info(experience)")).fetchall()
        }
        if "location" not in existing_columns:
            connection.execute(text("ALTER TABLE experience ADD COLUMN location VARCHAR"))

        existing_columns = {
            row[1]
            for row in connection.execute(text("PRAGMA table_info(education)")).fetchall()
        }
        if "location" not in existing_columns:
            connection.execute(text("ALTER TABLE education ADD COLUMN location VARCHAR"))

        skill_columns = {
            row[1]
            for row in connection.execute(text("PRAGMA table_info(skills)")).fetchall()
        }
        if "level" not in skill_columns:
            connection.execute(text("ALTER TABLE skills ADD COLUMN level INTEGER DEFAULT 3"))
        connection.execute(text("UPDATE skills SET level = 3 WHERE level IS NULL"))

        project_columns = {
            row[1]
            for row in connection.execute(text("PRAGMA table_info(projects)")).fetchall()
        }
        if "position" not in project_columns:
            connection.execute(text("ALTER TABLE projects ADD COLUMN position INTEGER DEFAULT 0"))
        project_rows = connection.execute(text("SELECT id, position FROM projects ORDER BY id ASC")).fetchall()
        if project_rows and all((row[1] or 0) == 0 for row in project_rows):
            for index, row in enumerate(project_rows, start=1):
                connection.execute(
                    text("UPDATE projects SET position = :position WHERE id = :id"),
                    {"position": index, "id": row[0]},
                )

        recommendation_columns = {
            row[1]
            for row in connection.execute(text("PRAGMA table_info(recommendations)")).fetchall()
        }
        if "position" not in recommendation_columns:
            connection.execute(text("ALTER TABLE recommendations ADD COLUMN position INTEGER DEFAULT 0"))
        recommendation_rows = connection.execute(text("SELECT id, position FROM recommendations ORDER BY id ASC")).fetchall()
        if recommendation_rows and all((row[1] or 0) == 0 for row in recommendation_rows):
            for index, row in enumerate(recommendation_rows, start=1):
                connection.execute(
                    text("UPDATE recommendations SET position = :position WHERE id = :id"),
                    {"position": index, "id": row[0]},
                )

def init_admin_user(db: Session):
    try:
        if db.query(Admin).first() is None:
            username = os.getenv("CVAAS_ADMIN_USER", "admin")
            raw_password = os.getenv("CVAAS_ADMIN_PASSWORD")
            password_hash = pwd_context.hash(raw_password)
            db.add(Admin(username=username, password_hash=password_hash))
            db.commit()
    finally:
        db.close()

from sqlalchemy import event
from .mixins import TimestampMixin
from datetime import datetime

@event.listens_for(TimestampMixin, 'before_update', propagate=True)
def receive_before_update(mapper, connection, target):
    target.updated_at = datetime.utcnow()
