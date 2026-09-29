#!/bin/bash
cd personal-ai-call-agent/backend

# pyproject.toml
cat << 'TOML' > pyproject.toml
[tool.poetry]
name = "personal-ai-call-agent"
version = "0.1.0"
description = "Personal AI Call Agent Backend"
authors = ["Admin"]

[tool.poetry.dependencies]
python = "^3.12"
fastapi = "^0.111.0"
uvicorn = "^0.30.1"
pydantic = "^2.7.4"
pydantic-settings = "^2.3.4"
sqlalchemy = "^2.0.31"
alembic = "^1.13.1"
psycopg2-binary = "^2.9.9"
redis = "^5.0.7"
structlog = "^24.2.0"

[tool.poetry.group.dev.dependencies]
pytest = "^8.2.2"
pytest-asyncio = "^0.23.7"
httpx = "^0.27.0"

[build-system]
requires = ["poetry-core"]
build-backend = "poetry.core.masonry.api"
TOML

# create requirements.txt for pip just in case
cat << 'REQ' > requirements.txt
fastapi
uvicorn[standard]
pydantic
pydantic-settings
sqlalchemy
alembic
psycopg2-binary
redis
structlog
pytest
pytest-asyncio
httpx
REQ

# app/core/config.py
cat << 'PY' > app/core/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "Personal AI Call Agent"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: str = "5432"
    POSTGRES_DB: str = "call_agent"
    
    REDIS_URL: str = "redis://localhost:6379/0"
    
    LOG_LEVEL: str = "INFO"

    @property
    def SQLALCHEMY_DATABASE_URI(self) -> str:
        return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    class Config:
        env_file = ".env"

settings = Settings()
PY

# app/core/logging.py
cat << 'PY' > app/core/logging.py
import logging
import structlog
from app.core.config import settings

def setup_logging():
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    logging.basicConfig(format="%(message)s", level=log_level)
PY

# app/core/database.py
cat << 'PY' > app/core/database.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import settings

engine = create_engine(settings.SQLALCHEMY_DATABASE_URI, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
PY

# app/core/redis.py
cat << 'PY' > app/core/redis.py
import redis
from app.core.config import settings

redis_client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)

def get_redis():
    return redis_client
PY

# app/models/base.py
cat << 'PY' > app/models/base.py
import uuid
from sqlalchemy import Column, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.core.database import Base

class BaseModel(Base):
    __abstract__ = True
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
PY

# app/main.py
cat << 'PY' > app/main.py
from fastapi import FastAPI
from app.core.config import settings
from app.core.logging import setup_logging
from app.core.database import engine, Base

setup_logging()

# Base.metadata.create_all(bind=engine)  # Using Alembic instead

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.get("/ready")
def readiness_check():
    # Check DB and Redis
    from app.core.database import SessionLocal
    from app.core.redis import get_redis
    from sqlalchemy import text
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        
        r = get_redis()
        r.ping()
    except Exception as e:
        return {"status": "error", "detail": str(e)}
    return {"status": "ready"}
PY

# tests/test_main.py
cat << 'PY' > tests/test_main.py
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
PY

# Alembic setup
alembic init alembic

# Update alembic/env.py to use our Base
cat << 'PY' > alembic_patch.py
import os
with open('alembic/env.py', 'r') as f:
    content = f.read()

content = content.replace("target_metadata = None", "from app.core.database import Base\ntarget_metadata = Base.metadata")

import re
content = re.sub(r'config\.get_main_option\("sqlalchemy\.url"\)', 'settings.SQLALCHEMY_DATABASE_URI', content)

content = "from app.core.config import settings\n" + content

with open('alembic/env.py', 'w') as f:
    f.write(content)
PY
python3 alembic_patch.py
rm alembic_patch.py

