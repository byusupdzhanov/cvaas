from sqlalchemy import Column, Integer, String, Text, DateTime, func, Boolean, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from .mixins import TimestampMixin
from datetime import datetime

Base = declarative_base()

class Experience(Base, TimestampMixin):
    __tablename__ = "experience"
    id = Column(Integer, primary_key=True)
    company = Column(String)
    location = Column(String, nullable=True)
    role = Column(String)
    period = Column(String)
    description = Column(Text)
    start_date = Column(String)  # "YYYY-MM"
    end_date = Column(String, nullable=True)

class Skill(Base, TimestampMixin):
    __tablename__ = "skills"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    level = Column(Integer, default=3)

class Info(Base, TimestampMixin):
    __tablename__ = "info"
    id = Column(Integer, primary_key=True)
    field = Column(String, unique=True)
    value = Column(Text)

class Course(Base, TimestampMixin):
    __tablename__ = "courses"
    id = Column(Integer, primary_key=True)
    title = Column(String)
    organization = Column(String)
    year = Column(String)

class Education(Base, TimestampMixin):
    __tablename__ = "education"
    id = Column(Integer, primary_key=True)
    degree = Column(String)
    institution = Column(String)
    location = Column(String, nullable=True)
    start_date = Column(String)
    end_date = Column(String)
    specialization = Column(String)

class Language(Base, TimestampMixin):
    __tablename__ = "languages"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    level = Column(String)

class Project(Base, TimestampMixin):
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True)
    title = Column(String)
    description = Column(String)
    link = Column(String)
    stack = Column(String)
    position = Column(Integer, default=0)

class Certificate(Base, TimestampMixin):
    __tablename__ = "certificates"
    id = Column(Integer, primary_key=True)
    title = Column(String)
    issuer = Column(String)
    year = Column(Integer)
    file_path = Column(String, nullable=True)     
    link = Column(String, nullable=True)      

class Recommendation(Base, TimestampMixin):
    __tablename__ = "recommendations"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    company = Column(String)
    quote = Column(String)
    position = Column(Integer, default=0)
 
class Admin(Base):
    __tablename__ = "admin"
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True)
    password_hash = Column(String)
    totp_secret = Column(String, nullable=True)
    twofa_enabled = Column(Boolean, default=False)
    security_question = Column(String, default="Место рождения?")
    security_answer = Column(String)


class LoginAttempt(Base):
    __tablename__ = "login_attempts"
    __table_args__ = (
        UniqueConstraint("username", "ip_address", name="uq_login_attempt_username_ip"),
    )

    id = Column(Integer, primary_key=True)
    username = Column(String, nullable=False)
    ip_address = Column(String, nullable=False)
    attempts = Column(Integer, default=0, nullable=False)
    first_attempt_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_attempt_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    blocked_until = Column(DateTime, nullable=True)
