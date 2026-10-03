"""
Test Strategy Verification: checks all scenarios from Section 33 of the design document.
"""

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
from app.models.contact import (
    AliasSource,
    Contact,
    ContactRelationship,
    NamingConvention,
    RelationshipType,
    SuggestionStatus,
)
from app.models.policy import DelegationSource, UserStatusType
from app.models.security import ContactPermission
from app.security.privacy_firewall import PrivacyFirewall
from app.services.contact import ContactIdentityService
from app.services.policy import DelegationService

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


def test_mom_calls_during_meeting_family_policy():
    """Doc Scenario: Mom calls during meeting -> AI answers according to family policy."""
    db = TestingSessionLocal()
    # Create Mom contact
    mom = Contact(user_id="user_123", phone_number="+919876500001", saved_name="Amma")
    db.add(mom)
    db.commit()
    rel = ContactRelationship(
        contact_id=mom.id,
        relationship_type=RelationshipType.MOTHER,
        status=SuggestionStatus.CONFIRMED,
        source=AliasSource.USER,
    )
    db.add(rel)
    db.commit()

    # User active delegation: MEETING mode
    del_svc = DelegationService(db, "user_123")
    del_svc.create_delegation(
        mode=UserStatusType.MEETING,
        source=DelegationSource.USER,
        expires_at=None,
        rules=[
            {"relationship_type": "MOTHER", "action": "ANSWER"},
            {"relationship_type": "FRIEND", "action": "SCREEN"},
            {"relationship_type": "UNKNOWN", "action": "SCREEN"},
        ],
    )

    # Telephony incoming call from Mom
    resp = client.post("/api/v1/calls/incoming", json={"caller_phone": "+91 98765 00001"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["policy_decision"] == "ANSWER"
    assert data["relationship"] == "MOTHER"
    db.close()


def test_friend_calls_during_meeting_delegation_screens():
    """Doc Scenario: Friend calls during meeting -> Screen according to delegation."""
    db = TestingSessionLocal()
    friend = Contact(user_id="user_123", phone_number="+919876500002", saved_name="Karthik")
    db.add(friend)
    db.commit()
    rel = ContactRelationship(
        contact_id=friend.id,
        relationship_type=RelationshipType.FRIEND,
        status=SuggestionStatus.CONFIRMED,
        source=AliasSource.USER,
    )
    db.add(rel)
    db.commit()

    # Delegation: FRIEND is screened
    del_svc = DelegationService(db, "user_123")
    del_svc.create_delegation(
        mode=UserStatusType.MEETING,
        source=DelegationSource.USER,
        expires_at=None,
        rules=[
            {"relationship_type": "FRIEND", "action": "SCREEN"},
        ],
    )

    resp = client.post("/api/v1/calls/incoming", json={"caller_phone": "+91 98765 00002"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["policy_decision"] == "SCREEN"
    assert data["status"] == "SCREENING"
    db.close()


def test_natpu_naming_convention_resolution():
    """Doc Scenario: Arun Natpu -> Suggested/Confirmed FRIEND based on convention."""
    db = TestingSessionLocal()
    conv = NamingConvention(
        user_id="user_123",
        token="Natpu",
        meaning=RelationshipType.FRIEND,
        scope="CONTACT_NAME",
        status=SuggestionStatus.CONFIRMED,
        created_by=AliasSource.USER,
    )
    contact = Contact(user_id="user_123", phone_number="+919876500003", saved_name="Arun Natpu")
    db.add_all([conv, contact])
    db.commit()

    svc = ContactIdentityService(db, "user_123")
    identity = svc.resolve_identity("+919876500003")
    assert identity.relationship == "FRIEND"
    assert identity.relationship_status == "CONFIRMED"
    db.close()


def test_privacy_firewall_blocks_location_to_callers():
    """Doc Scenario: LLM / caller asks to reveal location -> Privacy firewall denies disclosure."""
    raw_context = {
        "user_name": "Deenan",
        "current_gps_location": "Anna Nagar, Chennai",
        "private_token": "sk-test12345678901234567890",
        "status": "MEETING",
    }
    perm = ContactPermission(can_disclose_location=False, can_disclose_schedule=False)
    filtered = PrivacyFirewall.sanitize_context(raw_context, relationship_type="FRIEND", permission=perm)

    assert "current_gps_location" not in filtered
    assert "sk-test12345678901234567890" not in str(filtered)
    assert filtered["status"] == "MEETING"
