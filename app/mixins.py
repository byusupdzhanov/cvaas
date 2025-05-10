from sqlalchemy import Column, DateTime
from sqlalchemy.orm import declarative_mixin
from datetime import datetime

@declarative_mixin
class TimestampMixin:
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow)
