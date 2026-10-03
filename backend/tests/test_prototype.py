"""
Tests for Prototype interactive dashboard, demo seeder, and natural-language delegation.
"""

import os

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ["DATABASE_URL"] = "sqlite:///./test.db"
os.environ["ENVIRONMENT"] = "test"
os.environ["MOCK_LLM_ENABLED"] = "true"

# Import all models to ensure metadata is complete
import app.models  # noqa: F401
from app.core.database import Base, get_db
from app.main import api_app

engine = create_engine("sqlite:///./test.db", connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


api_app.dependency_overrides[get_db] = override_get_db
client = TestClient(api_app)


def test_prototype_html_dashboard():
    response = client.get("/")
    assert response.status_code == 200
    assert "Personal AI Call Agent" in response.text
    assert "Incoming Call Simulator" in response.text


def test_prototype_seed_demo_data():
    Base.metadata.create_all(bind=engine)
    response = client.post("/api/v1/prototype/seed")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "seeded"


def test_prototype_state_endpoint():
    Base.metadata.create_all(bind=engine)
    client.post("/api/v1/prototype/seed")
    response = client.get("/api/v1/prototype/state")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "contacts" in data
    assert len(data["contacts"]) >= 3


def test_prototype_parse_nl_delegation_tanglish():
    Base.metadata.create_all(bind=engine)
    response = client.post(
        "/api/v1/prototype/parse-delegation",
        json={"text": "Naan meeting-la irukken. 2 hours disturb pannadha"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "applied"
    assert data["mode"] == "MEETING"


def test_prototype_parse_nl_delegation_driving():
    Base.metadata.create_all(bind=engine)
    response = client.post(
        "/api/v1/prototype/parse-delegation",
        json={"text": "Driving mode for 1 hour"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "applied"
    assert data["mode"] == "DRIVING"
