"""
Privacy Firewall: Enforces deterministic data protection before context reaches the LLM.
Implements Section 6 & Section 22 of the system architecture.
"""

import re
from typing import Any

from sqlalchemy.orm import Session

from app.models.security import (
    AuditLog,
    ContactPermission,
)

API_KEY_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{20,}", re.IGNORECASE),
    re.compile(r"(?:api[_-]?key|secret|token|password|auth_token)\s*[:=]\s*['\"]?([A-Za-z0-9_\-\.]{8,})['\"]?", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9_\-\.]{20,}", re.IGNORECASE),
    re.compile(r"\b(?:\d[ -]*?){13,16}\b"),  # credit card numbers
]

LOCATION_PATTERNS = [
    re.compile(r"\b(?:latitude|longitude|gps|exact location|coordinates)\s*[:=]\s*[^,\n]+", re.IGNORECASE),
]


class PrivacyFirewall:
    @staticmethod
    def redact_secrets(text: str) -> str:
        """Removes API keys, tokens, passwords, and sensitive credentials from text."""
        if not text:
            return ""

        sanitized = text
        for pattern in API_KEY_PATTERNS:
            sanitized = pattern.sub("[REDACTED_SECRET]", sanitized)

        return sanitized

    @classmethod
    def sanitize_context(
        cls,
        context: dict[str, Any],
        relationship_type: str = "UNKNOWN",
        permission: ContactPermission | None = None,
        db: Session | None = None,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Enforces privacy rules on the context sent to the LLM.
        - Redacts credentials & API keys.
        - Redacts location unless permitted.
        - Redacts schedule unless permitted.
        - Minimizes context for UNKNOWN callers.
        """
        sanitized: dict[str, Any] = {}
        redactions_occurred = False

        can_location = permission.can_disclose_location if permission else False
        can_schedule = permission.can_disclose_schedule if permission else False

        for k, v in context.items():
            key_lower = k.lower()

            # Location filtering
            if any(loc_term in key_lower for loc_term in ("location", "gps", "coordinates", "address")) and not can_location:
                redactions_occurred = True
                continue

            # Schedule/Calendar filtering
            if any(sched_term in key_lower for sched_term in ("schedule", "calendar", "meetings")) and not can_schedule:
                redactions_occurred = True
                continue

            # Financial filtering
            if any(fin_term in key_lower for fin_term in ("bank", "account", "card", "salary", "balance")):
                redactions_occurred = True
                continue

            # Recursively redact secrets from string or nested objects
            sanitized[k] = cls._recursive_sanitize(v)

        # UNKNOWN caller restriction: remove any non-basic metadata
        if relationship_type == "UNKNOWN":
            allowed_unknown_keys = {"caller_phone", "time_of_day", "greeting_language", "user_status_mode"}
            sanitized = {k: v for k, v in sanitized.items() if k in allowed_unknown_keys}

        if redactions_occurred and db and user_id:
            audit = AuditLog(
                user_id=user_id,
                event_type="PRIVACY_FIREWALL_FILTER_APPLIED",
                details={"relationship_type": relationship_type, "redacted": True},
            )
            db.add(audit)
            db.commit()

        return sanitized

    @classmethod
    def _recursive_sanitize(cls, val: Any) -> Any:
        if isinstance(val, str):
            return cls.redact_secrets(val)
        if isinstance(val, dict):
            return {k: cls._recursive_sanitize(v) for k, v in val.items()}
        if isinstance(val, list):
            return [cls._recursive_sanitize(item) for item in val]
        return val

    @classmethod
    def validate_llm_response(cls, response_text: str) -> str:
        """Sanitizes outgoing LLM text so no secrets or internal prompts leak to caller."""
        return cls.redact_secrets(response_text)
