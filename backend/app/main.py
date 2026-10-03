import structlog
from fastapi import FastAPI

# Import domain tools to self-register on startup
import app.tools.domain
from app.api.agent import router as agent_router
from app.api.calls import router as calls_router
from app.api.contacts import router as contacts_router
from app.api.memory import router as memory_router
from app.api.notifications import router as notifications_router
from app.api.policy.delegation import router as delegation_router
from app.api.policy.preferences import router as preferences_router
from app.api.policy.status import router as status_router
from app.api.prototype import router as prototype_router
from app.api.relationships import router as rel_router
from app.api.telephony import router as telephony_router
from app.core.config import settings
from app.core.logging import setup_logging

setup_logging()
logger = structlog.get_logger(__name__)

api_app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
)
app = api_app

# Core Routers
api_app.include_router(prototype_router)
api_app.include_router(agent_router, prefix=settings.API_V1_STR)
api_app.include_router(contacts_router, prefix=settings.API_V1_STR)
api_app.include_router(rel_router, prefix=settings.API_V1_STR)
api_app.include_router(status_router, prefix=settings.API_V1_STR)
api_app.include_router(delegation_router, prefix=settings.API_V1_STR)
api_app.include_router(preferences_router, prefix=settings.API_V1_STR)
api_app.include_router(calls_router, prefix=settings.API_V1_STR)
api_app.include_router(notifications_router, prefix=settings.API_V1_STR)
api_app.include_router(memory_router, prefix=settings.API_V1_STR)
api_app.include_router(telephony_router, prefix=settings.API_V1_STR)


@api_app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok", "environment": settings.ENVIRONMENT}


@api_app.get("/ready")
def readiness_check() -> dict[str, str]:
    from sqlalchemy import text

    from app.core.database import SessionLocal
    from app.core.redis import get_redis

    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()

        r = get_redis()
        r.ping()
    except Exception as e:
        logger.error("readiness_check_failed", error=str(e))
        return {"status": "error", "detail": "Service unavailable"}
    return {"status": "ready"}
