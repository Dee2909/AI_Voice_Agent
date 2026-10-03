from app.api.policy.delegation import router as delegation_router
from app.api.policy.preferences import router as preferences_router
from app.api.policy.status import router as status_router

__all__ = ["delegation_router", "preferences_router", "status_router"]
