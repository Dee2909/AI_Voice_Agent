from abc import ABC, abstractmethod
from typing import Any


class LLMProvider(ABC):
    @abstractmethod
    async def generate_structured(self, prompt: str, system_prompt: str) -> dict[str, Any]:
        """Generate a structured JSON response based on the required schema."""
