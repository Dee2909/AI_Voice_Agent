import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ["DATABASE_URL"] = "sqlite:///./test.db"
os.environ["ENVIRONMENT"] = "test"
os.environ["MOCK_LLM_ENABLED"] = "true"

from app.core.database import Base, get_db
from app.main import api_app
from app.models.call import UrgencyLevel
from app.models.notification import Notification, NotificationType

engine = create_engine("sqlite:///./test.db", connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


api_app.dependency_overrides[get_db] = override_get_db
client = TestClient(api_app)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def test_notifications_crud_and_unread_count():
    db = TestingSessionLocal()
    n1 = Notification(
        user_id="user_123",
        title="Test Notification 1",
        body="Body 1",
        notification_type=NotificationType.SUMMARY,
        urgency=UrgencyLevel.NORMAL,
        is_read=False,
    )
    n2 = Notification(
        user_id="user_123",
        title="Test Notification 2",
        body="Body 2",
        notification_type=NotificationType.URGENT_CALL,
        urgency=UrgencyLevel.POTENTIALLY_URGENT,
        is_read=False,
    )
    db.add_all([n1, n2])
    db.commit()
    db.refresh(n1)
    db.refresh(n2)
    n1_id = str(n1.id)
    db.close()

    # 1. Unread count
    resp = client.get("/api/v1/notifications/unread-count")
    assert resp.status_code == 200
    assert resp.json()["unread_count"] == 2

    # 2. List notifications
    list_resp = client.get("/api/v1/notifications")
    assert list_resp.status_code == 200
    notifs = list_resp.json()
    assert len(notifs) == 2

    # 3. Mark read
    read_resp = client.post(f"/api/v1/notifications/{n1_id}/read")
    assert read_resp.status_code == 200
    assert read_resp.json()["is_read"] is True

    # 4. Check unread count decreased to 1
    resp2 = client.get("/api/v1/notifications/unread-count")
    assert resp2.json()["unread_count"] == 1


def test_memory_store_and_retrieve():
    # Create contact
    contact_resp = client.post("/api/v1/contacts", json={"phone_number": "+91 99887 76655", "saved_name": "Arun"})
    assert contact_resp.status_code == 200
    contact_id = contact_resp.json()["id"]

    # Store fact
    fact_resp = client.post(
        f"/api/v1/memory/{contact_id}",
        json={"key": "preferred_language", "value": "Tamil", "privacy_level": "PUBLIC"},
    )
    assert fact_resp.status_code == 200
    assert fact_resp.json()["key"] == "preferred_language"

    # Retrieve memory
    get_resp = client.get(f"/api/v1/memory/{contact_id}")
    assert get_resp.status_code == 200
    facts = get_resp.json()["facts"]
    assert facts.get("preferred_language") == "Tamil"
