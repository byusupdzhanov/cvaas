from sqlalchemy import create_engine
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
