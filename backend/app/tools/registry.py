from collections.abc import Awaitable, Callable
from typing import Any

from app.tools.schemas import ToolMetadata

ToolFunction = Callable[..., Awaitable[dict[str, Any]]]

class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolFunction] = {}
        self._metadata: dict[str, ToolMetadata] = {}

    def register(self, metadata: ToolMetadata, func: ToolFunction) -> None:
        self._tools[metadata.name] = func
        self._metadata[metadata.name] = metadata

    def get_tool(self, name: str) -> ToolFunction | None:
        return self._tools.get(name)

    def get_metadata(self, name: str) -> ToolMetadata | None:
        return self._metadata.get(name)
        
    def list_metadata(self) -> list[ToolMetadata]:
        return list(self._metadata.values())

registry = ToolRegistry()
