from typing import Any

from pydantic import BaseModel


class ToolMetadata(BaseModel):
    name: str
    description: str
    input_schema: dict[str, Any]
    sensitive: bool
    llm_allowed: bool
    user_confirmation_required: bool

class ToolCall(BaseModel):
    tool_call_id: str
    name: str
    arguments: dict[str, Any]

class ToolError(BaseModel):
    code: str
    message: str

class ToolExecutionResult(BaseModel):
    success: bool
    tool_call_id: str
    tool_name: str
    data: dict[str, Any] | None = None
    error: ToolError | None = None
