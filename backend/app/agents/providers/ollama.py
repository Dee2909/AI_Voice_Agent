import json
from typing import Any

import httpx
import structlog

from app.agents.providers.base import LLMProvider
from app.core.config import settings

logger = structlog.get_logger(__name__)

class OllamaProvider(LLMProvider):
    def __init__(self) -> None:
        self.base_url = settings.OLLAMA_BASE_URL
        self.model = settings.OLLAMA_MODEL
        self.timeout = settings.OLLAMA_TIMEOUT_SECONDS

    async def generate_structured(self, prompt: str, system_prompt: str) -> dict[str, Any]:
        """Generate a structured JSON response from Ollama."""
        schema = {
            "type": "object",
            "properties": {
                "response_type": {
                    "type": "string",
                    "enum": [
                        "MESSAGE",
                        "TOOL_CALL",
                        "FINAL",
                        "CLARIFICATION",
                        "SAFE_FALLBACK"
                    ]
                },
                "message": {
                    "type": "string"
                },
                "tool_call": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "arguments": {"type": "object"}
                    },
                    "required": ["name", "arguments"]
                }
            },
            "required": [
                "response_type",
                "message"
            ]
        }
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            "format": schema,
            "stream": False,
            "options": {
                "temperature": settings.OLLAMA_TEMPERATURE
            }
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(f"{self.base_url}/api/chat", json=payload)
                response.raise_for_status()
                data = response.json()
                content = data.get("message", {}).get("content", "")
                parsed = json.loads(content)
                return parsed # type: ignore
        except Exception as e:
            logger.error("ollama_generation_failed", error=str(e))
            # Safe fallback on error
            return {
                "response_type": "SAFE_FALLBACK",
                "message": "I'm currently unable to process your request.",
                "tool_call": None
            }
