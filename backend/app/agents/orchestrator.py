"""
Agent Orchestrator: coordinates LLM, tool gateway, context, and conversation loop.
"""

import time
import uuid
from typing import Any

import structlog

from app.agents.prompts import CALL_AGENT_SYSTEM_PROMPT
from app.agents.providers.base import LLMProvider
from app.agents.providers.mock import MockLLMProvider
from app.agents.providers.ollama import OllamaProvider
from app.core.config import settings
from app.schemas.agent import AgentStructuredResponse, ResponseType
from app.tools.gateway import ToolGateway
from app.tools.schemas import ToolCall, ToolExecutionResult

logger = structlog.get_logger(__name__)


class AgentOrchestrator:
    def __init__(self, provider: LLMProvider, gateway: ToolGateway) -> None:
        self.provider = provider
        self.gateway = gateway
        self.max_tool_calls = settings.MAX_TOOL_CALLS_PER_TURN

    async def run(
        self,
        conversation_id: str,
        user_message: str,
        call_id: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Main entry point for agent turn processing."""
        start = time.time()
        tool_calls_log: list[dict[str, Any]] = []
        conversation_history: list[str] = []

        current_prompt = self._build_initial_prompt(user_message, call_id, context)
        tool_call_count = 0

        logger.info(
            "agent_turn_start",
            conversation_id=conversation_id,
            call_id=call_id,
        )

        while tool_call_count <= self.max_tool_calls:
            raw = await self.provider.generate_structured(
                prompt=current_prompt,
                system_prompt=CALL_AGENT_SYSTEM_PROMPT,
            )

            # Validate response schema
            try:
                structured = AgentStructuredResponse(**raw)
            except Exception as e:
                logger.error("agent_invalid_llm_response", error=str(e))
                return self._safe_fallback(conversation_id, tool_calls_log, start)

            if structured.response_type in (
                ResponseType.FINAL,
                ResponseType.MESSAGE,
                ResponseType.CLARIFICATION,
                ResponseType.SAFE_FALLBACK,
            ):
                elapsed = time.time() - start
                logger.info(
                    "agent_turn_complete",
                    conversation_id=conversation_id,
                    response_type=structured.response_type,
                    latency_s=round(elapsed, 3),
                )
                return {
                    "conversation_id": conversation_id,
                    "response": structured.message,
                    "tool_calls": tool_calls_log,
                }

            if structured.response_type == ResponseType.TOOL_CALL:
                if tool_call_count >= self.max_tool_calls:
                    logger.warning(
                        "agent_tool_call_limit_reached",
                        conversation_id=conversation_id,
                        limit=self.max_tool_calls,
                    )
                    return self._safe_fallback(conversation_id, tool_calls_log, start)

                if not structured.tool_call:
                    logger.error("agent_tool_call_missing_data", response=raw)
                    return self._safe_fallback(conversation_id, tool_calls_log, start)

                tc_id = str(uuid.uuid4())
                tool_call = ToolCall(
                    tool_call_id=tc_id,
                    name=structured.tool_call.name,
                    arguments=structured.tool_call.arguments,
                )

                result: ToolExecutionResult = await self.gateway.execute_tool(
                    tool_call, called_by_llm=True
                )

                tool_calls_log.append({
                    "tool_call_id": tc_id,
                    "tool_name": result.tool_name,
                    "success": result.success,
                })

                # Feed result back into conversation
                current_prompt = self._build_tool_result_prompt(
                    original_message=user_message,
                    history=conversation_history,
                    tool_name=result.tool_name,
                    # pyrefly: ignore [bad-argument-type]
                    tool_result=result.data if result.success and result.data else {"error": result.error.message if result.error else "unknown"},
                )
                conversation_history.append(
                    f"Tool {result.tool_name}: {'success' if result.success else 'failed'}"
                )
                tool_call_count += 1
                continue

            # Unexpected response type
            logger.warning("agent_unexpected_response_type", response_type=structured.response_type)
            return self._safe_fallback(conversation_id, tool_calls_log, start)

        return self._safe_fallback(conversation_id, tool_calls_log, start)

    def _build_initial_prompt(
        self,
        message: str,
        call_id: str,
        context: dict[str, Any] | None,
    ) -> str:
        ctx_str = ""
        if context:
            ctx_str = f"\nContext: {context}"
        return (
            f"Call ID: {call_id}{ctx_str}\n"
            f"Caller message: {message}\n"
            "Respond using the required JSON schema."
        )

    def _build_tool_result_prompt(
        self,
        original_message: str,
        history: list[str],
        tool_name: str,
        tool_result: dict[str, Any],
    ) -> str:
        history_str = "\n".join(history) if history else "None"
        return (
            f"Original caller message: {original_message}\n"
            f"Previous steps: {history_str}\n"
            f"Tool '{tool_name}' returned: {tool_result}\n"
            "Now generate the next response using the required JSON schema."
        )

    def _safe_fallback(
        self,
        conversation_id: str,
        tool_calls_log: list[dict[str, Any]],
        start: float,
    ) -> dict[str, Any]:
        elapsed = time.time() - start
        logger.warning("agent_safe_fallback", conversation_id=conversation_id, latency_s=round(elapsed, 3))
        return {
            "conversation_id": conversation_id,
            "response": "I'm sorry, I'm unable to process your request right now. Please try again later.",
            "tool_calls": tool_calls_log,
        }


def get_orchestrator() -> AgentOrchestrator:
    """Dependency injection factory."""
    from app.tools.gateway import gateway
    if settings.MOCK_LLM_ENABLED:
        provider: LLMProvider = MockLLMProvider()
    else:
        provider = OllamaProvider()
    return AgentOrchestrator(provider=provider, gateway=gateway)
