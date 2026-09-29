from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ResponseType(str, Enum):
    MESSAGE = "MESSAGE"
    TOOL_CALL = "TOOL_CALL"
    FINAL = "FINAL"
    CLARIFICATION = "CLARIFICATION"
    SAFE_FALLBACK = "SAFE_FALLBACK"

class ToolCallRequest(BaseModel):
    name: str
    arguments: dict[str, Any]

class AgentStructuredResponse(BaseModel):
    response_type: ResponseType
    message: str
    tool_call: ToolCallRequest | None = None

class AgentMessageRequest(BaseModel):
    conversation_id: str
    message: str
    call_id: str | None = None

class AgentMessageResponse(BaseModel):
    conversation_id: str
    response: str
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
