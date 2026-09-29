"""
Agent API endpoints: /agent/message and /agent/tool-test (dev-only).
"""

from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, status

from app.agents.orchestrator import get_orchestrator
from app.core.config import settings
from app.schemas.agent import AgentMessageRequest, AgentMessageResponse

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/message", response_model=AgentMessageResponse)
async def agent_message(request: AgentMessageRequest) -> dict[str, Any]:
    """Process a message through the agent conversation loop."""
    orchestrator = get_orchestrator()
    result = await orchestrator.run(
        conversation_id=request.conversation_id,
        user_message=request.message,
        call_id=request.call_id or "unknown",
    )
    return result


@router.post("/tool-test")
async def tool_test(payload: dict[str, Any]) -> dict[str, Any]:
    """
    DEV-ONLY: Direct tool execution for testing.
    Requires MOCK_LLM_ENABLED=true (dev mode) to function.
    NEVER exposed in production unrestricted.
    """
    if not settings.MOCK_LLM_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tool test endpoint is only available in development mode.",
        )
    import uuid

    from app.tools.gateway import gateway
    from app.tools.schemas import ToolCall

    tool_name = payload.get("tool_name", "")
    arguments = payload.get("arguments", {})

    tool_call = ToolCall(
        tool_call_id=str(uuid.uuid4()),
        name=tool_name,
        arguments=arguments,
    )
    result = await gateway.execute_tool(tool_call, called_by_llm=True)
    return result.model_dump()


@router.get("/health/ollama")
async def ollama_health() -> dict[str, Any]:
    """Check if Ollama is reachable. Returns sanitized health info only."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(f"{settings.OLLAMA_BASE_URL}/api/tags")
            response.raise_for_status()
            return {"status": "healthy", "provider": "ollama"}
    except Exception as e:
        logger.warning("ollama_health_check_failed", error=str(e))
        return {"status": "unavailable", "provider": "ollama"}
