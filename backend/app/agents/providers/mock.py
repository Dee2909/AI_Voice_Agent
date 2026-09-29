from typing import Any

from app.agents.providers.base import LLMProvider


class MockLLMProvider(LLMProvider):
    def __init__(self) -> None:
        pass

    async def generate_structured(self, prompt: str, system_prompt: str) -> dict[str, Any]:
        """Deterministic mock responses for tests.

        NOTE: Prompts change each turn as tool results are appended.
        Priority order matters — more specific matches first.
        """
        # After tool result is returned, prompt includes "Tool 'get_caller_info'"
        if "Tool 'get_caller_info'" in prompt or "Arun Natpu" in prompt:
            return {
                "response_type": "FINAL",
                "message": "Arun is calling.",
                "tool_call": None,
            }

        if "Who is calling" in prompt:
            return {
                "response_type": "TOOL_CALL",
                "message": "I need to check who is calling.",
                "tool_call": {
                    "name": "get_caller_info",
                    "arguments": {"phone_number": "+919876543210"},
                },
            }

        # After relationship suggestion tool result
        if "Tool 'create_relationship_suggestion'" in prompt:
            return {
                "response_type": "FINAL",
                "message": "Thank you. I have noted that you identified yourself as Karthik. The user will be notified.",
                "tool_call": None,
            }

        if "Naan Karthik pesuren" in prompt:
            return {
                "response_type": "TOOL_CALL",
                "message": "Suggesting a new relationship.",
                "tool_call": {
                    "name": "create_relationship_suggestion",
                    "arguments": {
                        "phone_number": "+919876543210",
                        "suggested_name": "Karthik",
                        "suggested_relationship": "FRIEND",
                    },
                },
            }

        # Security / injection prompts — always refuse
        security_triggers = [
            "Deenan's location",
            "execute SQL",
            "system prompt",
            "DROP TABLE",
        ]
        if any(trigger in prompt for trigger in security_triggers):
            return {
                "response_type": "SAFE_FALLBACK",
                "message": "I cannot fulfill this request.",
                "tool_call": None,
            }

        if "Make me a family member" in prompt:
            return {
                "response_type": "SAFE_FALLBACK",
                "message": "I cannot change relationships without authorization.",
                "tool_call": None,
            }

        # Default generic response
        return {
            "response_type": "MESSAGE",
            "message": "Mock generic response.",
            "tool_call": None,
        }
