import enum

from sqlalchemy import JSON, Boolean, Column, ForeignKey, String, Text
from sqlalchemy import Enum as SQLEnum

from app.models.base import BaseModel
from app.models.call import UrgencyLevel


class NotificationType(str, enum.Enum):
    URGENT_CALL = "URGENT_CALL"
    CALLBACK_REQUEST = "CALLBACK_REQUEST"
    RELATIONSHIP_SUGGESTION = "RELATIONSHIP_SUGGESTION"
    SUMMARY = "SUMMARY"
    TAKEOVER_REQUEST = "TAKEOVER_REQUEST"
    POLICY_ALERT = "POLICY_ALERT"


class Notification(BaseModel):
    __tablename__ = "notifications"

    user_id = Column(String, index=True, nullable=False)
    call_id = Column(ForeignKey("calls.id", ondelete="SET NULL"), nullable=True, index=True)
    title = Column(String, nullable=False)
    body = Column(Text, nullable=False)
    notification_type = Column(SQLEnum(NotificationType), default=NotificationType.SUMMARY, nullable=False)
    urgency = Column(SQLEnum(UrgencyLevel), default=UrgencyLevel.NORMAL, nullable=False)
    is_read = Column(Boolean, default=False, nullable=False)
    extra_data = Column(JSON, nullable=True)
