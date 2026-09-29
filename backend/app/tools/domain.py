"""
Domain tool implementations — Phase 3+4 DB-backed implementations.
All tools are registered via the ToolRegistry.

Security contract:
  - llm_allowed=False  → LLM is NEVER permitted to invoke this tool.
  - llm_allowed=True   → LLM may request, but result is still policy-governed.
  - The LLM cannot change a PolicyEngine decision.
"""
from typing import Any

from app.tools.registry import registry
from app.tools.schemas import ToolMetadata


def tool(metadata: ToolMetadata) -> Any:
    def decorator(func: Any) -> Any:
        registry.register(metadata, func)
        return func
    return decorator


# ─────────────────────────────────────────────────────────────────
# Database session helper (test-safe)
# ─────────────────────────────────────────────────────────────────
def _get_db_session() -> Any:
    import os
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    if os.environ.get("ENVIRONMENT") == "test":
        engine = create_engine("sqlite:///./test.db", connect_args={"check_same_thread": False})
        from app.models.base import BaseModel as Base
        Base.metadata.create_all(bind=engine)
        return sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    from app.core.database import SessionLocal
    return SessionLocal()


# ══════════════════════════════════════════════════════════════════
# PHASE 3 — CONTACT IDENTITY TOOLS
# ══════════════════════════════════════════════════════════════════

@tool(ToolMetadata(
    name="get_caller_info",
    description="Get identity information about the caller by phone number.",
    input_schema={
        "type": "object",
        "properties": {"phone_number": {"type": "string"}},
        "required": ["phone_number"],
    },
    sensitive=True, llm_allowed=True, user_confirmation_required=False,
))
async def get_caller_info(arguments: dict[str, Any]) -> dict[str, Any]:
    from app.services.contact import ContactIdentityService
    phone = arguments["phone_number"]
    with _get_db_session() as db:
        svc = ContactIdentityService(db, "user_123")
        res = svc.resolve_identity(phone)
        return res.model_dump()


@tool(ToolMetadata(
    name="get_contact_relationship",
    description="Get relationship info for a specific caller.",
    input_schema={
        "type": "object",
        "properties": {"phone_number": {"type": "string"}},
        "required": ["phone_number"],
    },
    sensitive=True, llm_allowed=True, user_confirmation_required=False,
))
async def get_contact_relationship(arguments: dict[str, Any]) -> dict[str, Any]:
    from app.services.contact import ContactIdentityService
    phone = arguments["phone_number"]
    with _get_db_session() as db:
        svc = ContactIdentityService(db, "user_123")
        res = svc.resolve_identity(phone)
        return {"relationship": res.relationship, "status": res.relationship_status, "confidence": res.confidence}


@tool(ToolMetadata(
    name="search_contacts",
    description="Search contacts by name or alias.",
    input_schema={
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    },
    sensitive=True, llm_allowed=True, user_confirmation_required=False,
))
async def search_contacts(arguments: dict[str, Any]) -> dict[str, Any]:
    from sqlalchemy import select
    from app.models.contact import Contact
    query = arguments["query"].lower()
    with _get_db_session() as db:
        contacts = db.scalars(select(Contact).where(Contact.user_id == "user_123")).all()
        matched = []
        for c in contacts:
            if (c.saved_name and query in c.saved_name.lower()) or \
               (c.real_name and query in c.real_name.lower()):
                matched.append({"id": str(c.id), "phone_number": c.phone_number, "saved_name": c.saved_name})
        return {"contacts": matched}


@tool(ToolMetadata(
    name="create_relationship_suggestion",
    description="Create an UNCONFIRMED relationship suggestion for user review. Never auto-confirms.",
    input_schema={
        "type": "object",
        "properties": {
            "phone_number": {"type": "string"},
            "suggested_name": {"type": "string"},
            "suggested_relationship": {"type": "string"},
            "reason": {"type": "string"},
        },
        "required": ["phone_number", "suggested_relationship"],
    },
    sensitive=True, llm_allowed=True, user_confirmation_required=True,
))
async def create_relationship_suggestion(arguments: dict[str, Any]) -> dict[str, Any]:
    from app.models.contact import Contact, RelationshipType
    from app.core.utils import normalize_phone_number
    from app.services.contact import ContactIdentityService
    phone = arguments["phone_number"]
    with _get_db_session() as db:
        svc = ContactIdentityService(db, "user_123")
        contact = svc.get_contact_by_phone(phone)
        if not contact:
            contact = Contact(user_id="user_123", phone_number=normalize_phone_number(phone))
            db.add(contact)
            db.commit()
            db.refresh(contact)
        rel_enum = RelationshipType(arguments["suggested_relationship"].upper())
        s = svc.suggest_relationship(  # type: ignore[arg-type]
            contact.id, arguments.get("suggested_name", ""), rel_enum, arguments.get("reason", "")
        )
        return {"status": "UNCONFIRMED", "suggestion_id": str(s.id)}


@tool(ToolMetadata(
    name="confirm_relationship",
    description="Confirm a relationship. INTERNAL ONLY — LLM is NOT permitted to call this.",
    input_schema={
        "type": "object",
        "properties": {"contact_id": {"type": "string"}, "relationship": {"type": "string"}},
        "required": ["contact_id", "relationship"],
    },
    sensitive=True, llm_allowed=False, user_confirmation_required=True,
))
async def confirm_relationship(arguments: dict[str, Any]) -> dict[str, Any]:
    return {"status": "CONFIRMED"}


# ══════════════════════════════════════════════════════════════════
# PHASE 4 — POLICY & DELEGATION TOOLS
# ══════════════════════════════════════════════════════════════════

@tool(ToolMetadata(
    name="get_user_status",
    description="Get the user's current availability status (e.g. MEETING, AVAILABLE).",
    input_schema={"type": "object", "properties": {}, "required": []},
    sensitive=False, llm_allowed=True, user_confirmation_required=False,
))
async def get_user_status(arguments: dict[str, Any]) -> dict[str, Any]:
    from app.services.policy import UserStatusService
    with _get_db_session() as db:
        svc = UserStatusService(db, "user_123")
        status = svc.get_current_status()
        if not status:
            return {"status": "AVAILABLE", "active": False}
        return {"status": status.status.value, "source": status.source.value, "active": True}


@tool(ToolMetadata(
    name="get_active_delegation",
    description="Get the active call delegation, if any.",
    input_schema={"type": "object", "properties": {}, "required": []},
    sensitive=False, llm_allowed=True, user_confirmation_required=False,
))
async def get_active_delegation(arguments: dict[str, Any]) -> dict[str, Any]:
    from app.services.policy import DelegationService
    with _get_db_session() as db:
        svc = DelegationService(db, "user_123")
        d = svc.get_active_delegation()
        if not d:
            return {"active": False}
        return {"active": True, "mode": d.mode.value}


@tool(ToolMetadata(
    name="evaluate_call_policy",
    description="Evaluate what to do with a caller. Returns ANSWER/SCREEN/NOTIFY/REJECT. LLM cannot override.",
    input_schema={
        "type": "object",
        "properties": {
            "call_id": {"type": "string"},
            "contact_id": {"type": "string"},
            "relationship": {"type": "string"},
            "relationship_status": {"type": "string"},
            "urgency": {"type": "string"},
        },
        "required": ["call_id", "relationship", "relationship_status"],
    },
    sensitive=False, llm_allowed=True, user_confirmation_required=False,
))
async def evaluate_call_policy(arguments: dict[str, Any]) -> dict[str, Any]:
    import uuid as _uuid
    from app.schemas.policy import PolicyEvaluationRequest
    from app.services.policy import PolicyEngine
    with _get_db_session() as db:
        engine = PolicyEngine(db, "user_123")
        req = PolicyEvaluationRequest(
            call_id=arguments["call_id"],
            contact_id=_uuid.UUID(arguments["contact_id"]) if arguments.get("contact_id") else None,
            relationship=arguments["relationship"],
            relationship_status=arguments["relationship_status"],
            urgency=arguments.get("urgency", "NORMAL"),
        )
        res = engine.evaluate_call(req)
        return res.model_dump()


# LLM-blocked mutating tools — authenticated user calls only
@tool(ToolMetadata(
    name="set_user_status",
    description="Set user availability status. LLM MUST NOT call this — user-initiated only.",
    input_schema={
        "type": "object",
        "properties": {"status": {"type": "string"}, "source": {"type": "string"}},
        "required": ["status"],
    },
    sensitive=True, llm_allowed=False, user_confirmation_required=True,
))
async def set_user_status(arguments: dict[str, Any]) -> dict[str, Any]:
    return {"status": "success"}


@tool(ToolMetadata(
    name="create_delegation",
    description="Create a delegation. LLM MUST NOT call this — user-initiated only.",
    input_schema={
        "type": "object",
        "properties": {"mode": {"type": "string"}},
        "required": ["mode"],
    },
    sensitive=True, llm_allowed=False, user_confirmation_required=True,
))
async def create_delegation(arguments: dict[str, Any]) -> dict[str, Any]:
    return {"status": "success"}


@tool(ToolMetadata(
    name="cancel_delegation",
    description="Cancel active delegation. LLM MUST NOT call this — user-initiated only.",
    input_schema={
        "type": "object",
        "properties": {"delegation_id": {"type": "string"}},
        "required": ["delegation_id"],
    },
    sensitive=True, llm_allowed=False, user_confirmation_required=True,
))
async def cancel_delegation(arguments: dict[str, Any]) -> dict[str, Any]:
    return {"status": "success"}


# ══════════════════════════════════════════════════════════════════
# STUBS — Phase 5+ (call summaries, callbacks, notifications)
# ══════════════════════════════════════════════════════════════════

@tool(ToolMetadata(
    name="save_message",
    description="Save a message from the caller.",
    input_schema={
        "type": "object",
        "properties": {"call_id": {"type": "string"}, "message": {"type": "string"}},
        "required": ["call_id", "message"],
    },
    sensitive=False, llm_allowed=True, user_confirmation_required=False,
))
async def save_message(arguments: dict[str, Any]) -> dict[str, Any]:
    return {"status": "saved"}


@tool(ToolMetadata(
    name="save_call_summary",
    description="Save a post-call summary.",
    input_schema={
        "type": "object",
        "properties": {"call_id": {"type": "string"}, "summary": {"type": "string"}, "urgency": {"type": "string"}},
        "required": ["call_id", "summary"],
    },
    sensitive=False, llm_allowed=True, user_confirmation_required=False,
))
async def save_call_summary(arguments: dict[str, Any]) -> dict[str, Any]:
    return {"status": "saved"}


@tool(ToolMetadata(
    name="create_callback_request",
    description="Request a callback for the caller.",
    input_schema={
        "type": "object",
        "properties": {"contact_id": {"type": "string"}, "reason": {"type": "string"}},
        "required": ["contact_id", "reason"],
    },
    sensitive=False, llm_allowed=True, user_confirmation_required=False,
))
async def create_callback_request(arguments: dict[str, Any]) -> dict[str, Any]:
    return {"status": "PENDING"}


@tool(ToolMetadata(
    name="notify_user",
    description="Send a notification to the user.",
    input_schema={
        "type": "object",
        "properties": {"message": {"type": "string"}, "urgency": {"type": "string"}},
        "required": ["message"],
    },
    sensitive=False, llm_allowed=True, user_confirmation_required=False,
))
async def notify_user(arguments: dict[str, Any]) -> dict[str, Any]:
    return {"status": "notified"}


@tool(ToolMetadata(
    name="mark_potentially_urgent",
    description="Flag a call as potentially urgent for user review.",
    input_schema={
        "type": "object",
        "properties": {"call_id": {"type": "string"}, "reason": {"type": "string"}},
        "required": ["call_id", "reason"],
    },
    sensitive=False, llm_allowed=True, user_confirmation_required=False,
))
async def mark_potentially_urgent(arguments: dict[str, Any]) -> dict[str, Any]:
    return {"status": "marked"}
