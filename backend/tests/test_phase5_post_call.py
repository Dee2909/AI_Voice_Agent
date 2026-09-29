import os
import uuid
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ["DATABASE_URL"] = "sqlite:///./test.db"
os.environ["ENVIRONMENT"] = "test"
os.environ["MOCK_LLM_ENABLED"] = "true"

from app.core.database import Base
from app.models.base import BaseModel
from app.models.call import (
    Call,
    CallDirection,
    CallStatus,
    CallTranscript,
    SpeakerType,
    UrgencyLevel,
)
from app.models.contact import Contact, RelationshipType
from app.models.notification import Notification
from app.services.post_call import PostCallService

engine = create_engine("sqlite:///./test.db", connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def test_post_call_normal_summary():
    db = TestingSessionLocal()
    call = Call(
        user_id="user_123",
        caller_phone="+919876543210",
        status=CallStatus.ACTIVE,
        direction=CallDirection.INBOUND,
    )
    db.add(call)
    db.commit()
    db.refresh(call)

    # Add transcripts
    t1 = CallTranscript(
        call_id=call.id,
        speaker=SpeakerType.CALLER,
        text="Hi, I am calling to discuss the weekend trip plans.",
    )
    t2 = CallTranscript(
        call_id=call.id,
        speaker=SpeakerType.ASSISTANT,
        text="Noted, I will inform the user.",
    )
    db.add_all([t1, t2])
    db.commit()

    svc = PostCallService(db, "user_123")
    res = svc.process_call(call.id)

    assert res["urgency"] == "NORMAL"
    assert "weekend trip" in res["reason"].lower()
    assert call.status == CallStatus.COMPLETED

    # Check notification created
    notif = db.query(Notification).filter(Notification.call_id == call.id).first()
    assert notif is not None
    assert notif.urgency == UrgencyLevel.NORMAL
    db.close()


def test_post_call_potentially_urgent_alert():
    db = TestingSessionLocal()
    call = Call(
        user_id="user_123",
        caller_phone="+919876543210",
        status=CallStatus.ACTIVE,
        direction=CallDirection.INBOUND,
    )
    db.add(call)
    db.commit()

    t1 = CallTranscript(
        call_id=call.id,
        speaker=SpeakerType.CALLER,
        text="Production server down! Urgent assistance required immediately.",
    )
    db.add(t1)
    db.commit()

    svc = PostCallService(db, "user_123")
    res = svc.process_call(call.id)

    assert res["urgency"] == "POTENTIALLY_URGENT"

    notif = db.query(Notification).filter(Notification.call_id == call.id).first()
    assert notif is not None
    assert "Potentially Urgent" in notif.title
    db.close()


def test_post_call_emergency_claim():
    db = TestingSessionLocal()
    call = Call(
        user_id="user_123",
        caller_phone="+919876543210",
        status=CallStatus.ACTIVE,
        direction=CallDirection.INBOUND,
    )
    db.add(call)
    db.commit()

    t1 = CallTranscript(
        call_id=call.id,
        speaker=SpeakerType.CALLER,
        text="Hospital emergency! Please call me back at 9 PM.",
    )
    db.add(t1)
    db.commit()

    svc = PostCallService(db, "user_123")
    res = svc.process_call(call.id)

    assert res["urgency"] == "EMERGENCY_CLAIM"
    assert res["actions_count"] >= 1

    notif = db.query(Notification).filter(Notification.call_id == call.id).first()
    assert notif is not None
    assert "EMERGENCY CLAIM" in notif.title
    db.close()


def test_post_call_self_identify_creates_suggestion_not_overwrite():
    db = TestingSessionLocal()
    contact = Contact(
        user_id="user_123",
        phone_number="+919876543210",
        saved_name="Kutti",
    )
    db.add(contact)
    db.commit()

    call = Call(
        user_id="user_123",
        caller_phone="+919876543210",
        contact_id=contact.id,
        status=CallStatus.ACTIVE,
        direction=CallDirection.INBOUND,
    )
    db.add(call)
    db.commit()

    # Caller says "Naan Karthik pesuren"
    t1 = CallTranscript(
        call_id=call.id,
        speaker=SpeakerType.CALLER,
        text="Vanakkam, naan Karthik pesuren. Please ask him to call me back.",
    )
    db.add(t1)
    db.commit()

    svc = PostCallService(db, "user_123")
    res = svc.process_call(call.id)

    assert res["suggestion_created"] is True

    # Ensure original saved name was NOT overwritten!
    db.refresh(contact)
    assert contact.saved_name == "Kutti"

    # Verify suggestion was saved
    assert len(contact.suggestions) == 1
    assert contact.suggestions[0].suggested_name == "Karthik"
    db.close()
