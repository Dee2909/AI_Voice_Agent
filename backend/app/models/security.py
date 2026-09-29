import datetime
import enum
from typing import Any

from sqlalchemy import Boolean, Column, DateTime, Enum as SQLEnum, ForeignKey, JSON, String, Text
from sqlalchemy.sql import func

from app.models.base import BaseModel


class SecuritySeverity(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ContactPermission(BaseModel):
    __tablename__ = "contact_permissions"

    contact_id = Column(ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False, unique=True)
    can_disclose_status = Column(Boolean, default=True, nullable=False)
    can_take_message = Column(Boolean, default=True, nullable=False)
    can_disclose_schedule = Column(Boolean, default=False, nullable=False)
    can_disclose_location = Column(Boolean, default=False, nullable=False)
    can_transfer = Column(Boolean, default=True, nullable=False)


class AuditLog(BaseModel):
    __tablename__ = "audit_logs"

    user_id = Column(String, index=True, nullable=False)
    event_type = Column(String, nullable=False, index=True)
    details = Column(JSON, nullable=True)
    ip_address = Column(String, nullable=True)


class SecurityEvent(BaseModel):
    __tablename__ = "security_events"

    user_id = Column(String, index=True, nullable=False)
    event_type = Column(String, nullable=False, index=True)
    severity = Column(SQLEnum(SecuritySeverity), default=SecuritySeverity.LOW, nullable=False)
    description = Column(Text, nullable=False)
    blocked = Column(Boolean, default=True, nullable=False)
    source_ip = Column(String, nullable=True)


def now_utc() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


class DeviceSession(BaseModel):
    __tablename__ = "device_sessions"

    user_id = Column(String, index=True, nullable=False)
    device_id = Column(String, nullable=False, index=True)
    device_name = Column(String, nullable=True)
    token_hash = Column(String, nullable=False)
    last_active = Column(DateTime(timezone=True), default=now_utc, nullable=False)
