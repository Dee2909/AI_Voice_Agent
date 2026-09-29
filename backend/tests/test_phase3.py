import os

import pytest

os.environ["DATABASE_URL"] = "sqlite:///./test.db"
os.environ["ENVIRONMENT"] = "test"
os.environ["MOCK_LLM_ENABLED"] = "true"

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.core.utils import normalize_phone_number
from app.main import api_app
from app.models.contact import (
    AliasSource,
    ContactRelationship,
    RelationshipType,
    SuggestionStatus,
)
from app.services.contact import ContactIdentityService
from app.tools.gateway import gateway
from app.tools.schemas import ToolCall

# Setup SQLite in-memory DB for tests
engine = create_engine("sqlite:///./test.db", connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)

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

def test_normalize_phone_number():
    assert normalize_phone_number("+91 98765 43210") == "+919876543210"
    assert normalize_phone_number("09876543210") == "09876543210"
    assert normalize_phone_number("") == ""

def test_create_contact_and_find_by_phone():
    response = client.post("/api/v1/contacts", json={
        "phone_number": "+91 98765 43210",
        "saved_name": "Kutti",
        "status": "ACTIVE"
    })
    assert response.status_code == 200
    data = response.json()
    assert data["phone_number"] == "+919876543210"
    
    # Find by identity
    resp_ident = client.get(f"/api/v1/contacts/{data['id']}/identity")
    assert resp_ident.status_code == 200
    ident_data = resp_ident.json()
    assert ident_data["saved_name"] == "Kutti"

def test_unknown_phone_number():
    db = TestingSessionLocal()
    svc = ContactIdentityService(db, "user_123")
    ident = svc.resolve_identity("+919999999999")
    assert ident.contact_id is None
    assert ident.relationship == "UNKNOWN"

@pytest.mark.asyncio
async def test_relationship_suggestion_flow():
    # 1. Create a contact via API
    client.post("/api/v1/contacts", json={"phone_number": "+919876543210", "saved_name": "Kutti"})
    
    # 2. Caller says "Naan Karthik pesuren" -> Trigger tool
    tc = ToolCall(tool_call_id=str(uuid.uuid4()), name="create_relationship_suggestion", arguments={
        "phone_number": "+919876543210",
        "suggested_name": "Karthik",
        "suggested_relationship": "FRIEND",
        "reason": "Caller identified himself as Karthik"
    })
    
    res = await gateway.execute_tool(tc, called_by_llm=True)
    assert res.success
    assert res.data["status"] == "UNCONFIRMED"
    s_id = res.data["suggestion_id"]
    
    # Check that identity remains UNCONFIRMED/SUGGESTED
    db = TestingSessionLocal()
    svc = ContactIdentityService(db, "user_123")
    ident = svc.resolve_identity("+919876543210")
    assert ident.relationship == "FRIEND"
    assert ident.relationship_status == "SUGGESTED"
    assert ident.saved_name == "Kutti"
    
    # 3. User confirms
    conf_resp = client.post(f"/api/v1/relationships/{s_id}/confirm")
    assert conf_resp.status_code == 200
    
    # Check identity after confirmation
    ident_confirmed = svc.resolve_identity("+919876543210")
    assert ident_confirmed.relationship == "FRIEND"
    assert ident_confirmed.relationship_status == "CONFIRMED"
    
def test_reject_relationship():
    # Similar to above, but reject
    resp = client.post("/api/v1/contacts", json={"phone_number": "+919876543211", "saved_name": "Unknown"})
    db = TestingSessionLocal()
    svc = ContactIdentityService(db, "user_123")
    s = svc.suggest_relationship(uuid.UUID(resp.json()["id"]), "Test", RelationshipType.WORK, "test")
    
    rej = client.post(f"/api/v1/relationships/{s.id}/reject")
    assert rej.status_code == 200
    
    ident = svc.resolve_identity("+919876543211")
    assert ident.relationship == "UNKNOWN"

def test_natpu_convention():
    # User creates "natpu" naming convention
    resp = client.post("/api/v1/naming-conventions", json={
        "token": "natpu",
        "meaning": "FRIEND",
        "scope": "CONTACT_NAME",
        "created_by": "USER",
        "status": "CONFIRMED"
    })
    assert resp.status_code == 200
    
    client.post("/api/v1/contacts", json={"phone_number": "+918888888888", "saved_name": "Arun Natpu"})
    
    db = TestingSessionLocal()
    svc = ContactIdentityService(db, "user_123")
    ident = svc.resolve_identity("+918888888888")
    assert ident.relationship == "FRIEND"
    assert ident.relationship_status == "CONFIRMED"

@pytest.mark.asyncio
async def test_llm_cannot_confirm_relationship():
    # Security test: LLM calling confirm_relationship
    tc = ToolCall(tool_call_id="1", name="confirm_relationship", arguments={"contact_id": "c1", "relationship": "FRIEND"})
    res = await gateway.execute_tool(tc, called_by_llm=True)
    assert not res.success
    assert res.error.code == "ACTION_NOT_AUTHORIZED"

def test_duplicate_phone_number():
    client.post("/api/v1/contacts", json={"phone_number": "123", "saved_name": "A"})
    resp = client.post("/api/v1/contacts", json={"phone_number": "123", "saved_name": "B"})
    assert resp.status_code == 400

@pytest.mark.asyncio
async def test_get_caller_info_tool():
    # Create contact and explicit relationship
    resp = client.post("/api/v1/contacts", json={"phone_number": "+12345", "saved_name": "Test"})
    c_id = resp.json()["id"]
    
    db = TestingSessionLocal()
    rel = ContactRelationship(contact_id=uuid.UUID(c_id), relationship_type=RelationshipType.BROTHER, status=SuggestionStatus.CONFIRMED, source=AliasSource.USER)
    db.add(rel)
    db.commit()
    
    tc = ToolCall(tool_call_id="2", name="get_caller_info", arguments={"phone_number": "+12345"})
    res = await gateway.execute_tool(tc, called_by_llm=True)
    assert res.success
    assert res.data["relationship"] == "BROTHER"
    assert res.data["relationship_status"] == "CONFIRMED"

