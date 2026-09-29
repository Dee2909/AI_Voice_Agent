from typing import Any

import structlog
from jsonschema import ValidationError, validate

from app.tools.registry import registry
from app.tools.schemas import ToolCall, ToolError, ToolExecutionResult

logger = structlog.get_logger(__name__)

class ToolGateway:
    def __init__(self) -> None:
        pass

    async def execute_tool(self, tool_call: ToolCall, called_by_llm: bool = True) -> ToolExecutionResult:
        logger.info("tool_gateway_execute_request", tool_name=tool_call.name, tool_call_id=tool_call.tool_call_id)
        
        metadata = registry.get_metadata(tool_call.name)
        if not metadata:
            return ToolExecutionResult(
                success=False,
                tool_call_id=tool_call.tool_call_id,
                tool_name=tool_call.name,
                error=ToolError(code="TOOL_NOT_FOUND", message="Requested tool is unavailable.")
            )

        # Policy / Authentication check
        if called_by_llm and not metadata.llm_allowed:
            return ToolExecutionResult(
                success=False,
                tool_call_id=tool_call.tool_call_id,
                tool_name=tool_call.name,
                error=ToolError(code="ACTION_NOT_AUTHORIZED", message="LLM is not allowed to execute this tool.")
            )
            
        # Schema Validation
        try:
            validate(instance=tool_call.arguments, schema=metadata.input_schema)
        except ValidationError as e:
            return ToolExecutionResult(
                success=False,
                tool_call_id=tool_call.tool_call_id,
                tool_name=tool_call.name,
                error=ToolError(code="INVALID_ARGUMENTS", message=f"Arguments failed schema validation: {e.message!s}")
            )

        # Execute
        func = registry.get_tool(tool_call.name)
        if not func:
            return ToolExecutionResult(
                success=False,
                tool_call_id=tool_call.tool_call_id,
                tool_name=tool_call.name,
                error=ToolError(code="INTERNAL_ERROR", message="Tool implementation missing.")
            )

        try:
            result = await func(tool_call.arguments)
            # Basic Sanitization placeholder - remove obvious secrets if any returned by tool
            sanitized = self._sanitize_result(result)
            return ToolExecutionResult(
                success=True,
                tool_call_id=tool_call.tool_call_id,
                tool_name=tool_call.name,
                data=sanitized
            )
        except Exception as e:
            logger.error("tool_execution_failed", tool_name=tool_call.name, error=str(e))
            return ToolExecutionResult(
                success=False,
                tool_call_id=tool_call.tool_call_id,
                tool_name=tool_call.name,
                error=ToolError(code="EXECUTION_ERROR", message="The tool failed to execute due to an internal error.")
            )

    def _sanitize_result(self, data: dict[str, Any]) -> dict[str, Any]:
        # Filter logic to remove passwords, tokens etc.
        sanitized = data.copy()
        keys_to_remove = ["password", "token", "secret", "api_key"]
        for key in keys_to_remove:
            if key in sanitized:
                del sanitized[key]
        return sanitized

gateway = ToolGateway()
