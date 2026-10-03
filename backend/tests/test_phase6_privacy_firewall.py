import os

os.environ["DATABASE_URL"] = "sqlite:///./test.db"
os.environ["ENVIRONMENT"] = "test"

from app.models.security import ContactPermission
from app.security.privacy_firewall import PrivacyFirewall


def test_redact_secrets():
    text_with_key = "My API key is sk-1234567890abcdef1234567890 and password is password=SecretPass123"
    sanitized = PrivacyFirewall.redact_secrets(text_with_key)
    assert "sk-1234567890abcdef1234567890" not in sanitized
    assert "[REDACTED_SECRET]" in sanitized


def test_filter_context_location_and_schedule():
    context = {
        "user_name": "Deenan",
        "current_location": "Chennai T-Nagar GPS: 13.0418, 80.2341",
        "meeting_schedule": "Product sync with investors at 4 PM",
        "greeting_language": "Tamil",
    }

    # Default permission: cannot disclose location or schedule
    perm = ContactPermission(
        can_disclose_location=False,
        can_disclose_schedule=False,
    )

    sanitized = PrivacyFirewall.sanitize_context(
        context=context,
        relationship_type="FRIEND",
        permission=perm,
    )

    assert "current_location" not in sanitized
    assert "meeting_schedule" not in sanitized
    assert sanitized["user_name"] == "Deenan"
    assert sanitized["greeting_language"] == "Tamil"


def test_unknown_caller_context_minimization():
    context = {
        "user_name": "Deenan",
        "caller_phone": "+919876543210",
        "time_of_day": "morning",
        "private_note": "User is feeling tired",
    }

    sanitized = PrivacyFirewall.sanitize_context(
        context=context,
        relationship_type="UNKNOWN",
        permission=None,
    )

    assert "caller_phone" in sanitized
    assert "time_of_day" in sanitized
    assert "user_name" not in sanitized
    assert "private_note" not in sanitized
