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


def test_incoming_call_and_turn():
    # 1. Start incoming call
    resp = client.post("/api/v1/calls/incoming", json={"caller_phone": "+91 98765 43210"})
    assert resp.status_code == 200
    data = resp.json()
    call_id = data["call_id"]
    assert call_id is not None

    # 2. Process turn
    turn_resp = client.post(
        f"/api/v1/calls/{call_id}/turn",
        json={"speaker": "CALLER", "message": "Vanakkam, is Deenan available?"},
    )
    assert turn_resp.status_code == 200
    turn_data = turn_resp.json()
    assert turn_data["ai_speaking"] is True
    assert turn_data["assistant_response"] is not None


def test_human_takeover_stops_ai_speaking():
    # Start call
    resp = client.post("/api/v1/calls/incoming", json={"caller_phone": "+91 98765 43210"})
    call_id = resp.json()["call_id"]

    # Trigger one-tap human takeover
    takeover_resp = client.post(f"/api/v1/calls/{call_id}/takeover")
    assert takeover_resp.status_code == 200
    takeover_data = takeover_resp.json()
    assert takeover_data["status"] == "HANDOFF"
    assert takeover_data["ai_speaking"] is False

    # Attempt turn while under takeover - AI must stay silent
    turn_resp = client.post(
        f"/api/v1/calls/{call_id}/turn",
        json={"speaker": "CALLER", "message": "Hello? Are you there?"},
    )
    assert turn_resp.status_code == 200
    turn_data = turn_resp.json()
    assert turn_data["status"] == "HANDOFF"
    assert turn_data["ai_speaking"] is False
    assert turn_data["assistant_response"] is None


def test_call_end_and_summary_retrieval():
    # Start call
    resp = client.post("/api/v1/calls/incoming", json={"caller_phone": "+91 98765 43210"})
    call_id = resp.json()["call_id"]

    # Send a turn
    client.post(
        f"/api/v1/calls/{call_id}/turn",
        json={"speaker": "CALLER", "message": "Please ask Deenan to call back regarding invoice."},
    )

    # End call
    end_resp = client.post(f"/api/v1/calls/{call_id}/end")
    assert end_resp.status_code == 200

    # Retrieve summary
    sum_resp = client.get(f"/api/v1/calls/{call_id}/summary")
    assert sum_resp.status_code == 200
    sum_data = sum_resp.json()
    assert "invoice" in sum_data["reason"].lower() or "call back" in sum_data["summary"].lower()

    # Retrieve transcript
    tr_resp = client.get(f"/api/v1/calls/{call_id}/transcript")
    assert tr_resp.status_code == 200
    transcripts = tr_resp.json()
    assert len(transcripts) >= 2
