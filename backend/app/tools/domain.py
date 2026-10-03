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


def _safe_uuid(val: Any) -> Any:
    if val is None:
        return None
    import uuid as _uuid
    if isinstance(val, _uuid.UUID):
        return val
    try:
        return _uuid.UUID(str(val))
    except (ValueError, AttributeError):
        return _uuid.uuid5(_uuid.NAMESPACE_DNS, str(val))



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
    from app.core.utils import normalize_phone_number
    from app.models.contact import Contact, RelationshipType
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
# PHASE 5+ — CONTEXT, MEMORY, SUMMARIES, CALLBACKS, NOTIFICATIONS & TELEPHONY
# ══════════════════════════════════════════════════════════════════

@tool(ToolMetadata(
    name="get_contact_context",
    description="Retrieve permission-filtered reusable memory facts for a contact.",
    input_schema={
        "type": "object",
        "properties": {
            "contact_id": {"type": "string"},
            "relationship": {"type": "string"},
        },
        "required": ["contact_id"],
    },
    sensitive=True, llm_allowed=True, user_confirmation_required=False,
))
async def get_contact_context(arguments: dict[str, Any]) -> dict[str, Any]:
    from app.services.memory import MemoryService
    contact_id_str = arguments["contact_id"]
    contact_uuid = _safe_uuid(contact_id_str)
    rel = arguments.get("relationship", "UNKNOWN")
    with _get_db_session() as db:
        mem_svc = MemoryService(db, "user_123")
        facts = mem_svc.get_contact_context(contact_uuid, relationship=rel)
        return {"contact_id": contact_id_str, "context": facts}


@tool(ToolMetadata(
    name="save_message",
    description="Save a message from the caller into call transcript and follow-up action.",
    input_schema={
        "type": "object",
        "properties": {"call_id": {"type": "string"}, "message": {"type": "string"}},
        "required": ["call_id", "message"],
    },
    sensitive=False, llm_allowed=True, user_confirmation_required=False,
))
async def save_message(arguments: dict[str, Any]) -> dict[str, Any]:
    from app.models.call import (
        ActionStatus,
        ActionType,
        CallAction,
        CallTranscript,
        SpeakerType,
    )
    call_id = _safe_uuid(arguments["call_id"])
    msg = arguments["message"]
    with _get_db_session() as db:
        transcript = CallTranscript(
            call_id=call_id,
            speaker=SpeakerType.CALLER,
            text=msg,
            language="en",
        )
        action = CallAction(
            call_id=call_id,
            action_type=ActionType.TASK,
            description=f"Message taken: {msg}",
            status=ActionStatus.PENDING,
        )
        db.add_all([transcript, action])
        db.commit()
        return {"status": "saved", "call_id": str(call_id)}


@tool(ToolMetadata(
    name="save_call_summary",
    description="Persist post-call summary, reason, and urgency in the database.",
    input_schema={
        "type": "object",
        "properties": {
            "call_id": {"type": "string"},
            "summary": {"type": "string"},
            "reason": {"type": "string"},
            "urgency": {"type": "string"},
        },
        "required": ["call_id", "summary"],
    },
    sensitive=False, llm_allowed=True, user_confirmation_required=False,
))
async def save_call_summary(arguments: dict[str, Any]) -> dict[str, Any]:
    from app.models.call import CallSummary, UrgencyLevel
    call_id = _safe_uuid(arguments["call_id"])
    summary_text = arguments["summary"]
    reason = arguments.get("reason", "Inquiry")
    urgency_str = arguments.get("urgency", "NORMAL").upper()
    urgency = UrgencyLevel(urgency_str) if urgency_str in UrgencyLevel.__members__ else UrgencyLevel.NORMAL

    with _get_db_session() as db:
        existing = db.query(CallSummary).filter(CallSummary.call_id == call_id).first()
        if existing:
            existing.summary_text = summary_text
            existing.reason = reason
            existing.urgency_level = urgency
        else:
            new_summary = CallSummary(
                call_id=call_id,
                summary_text=summary_text,
                reason=reason,
                urgency_level=urgency,
            )
            db.add(new_summary)
        db.commit()
        return {"status": "saved", "call_id": str(call_id)}


@tool(ToolMetadata(
    name="create_callback_request",
    description="Create a callback follow-up task and alert the user.",
    input_schema={
        "type": "object",
        "properties": {
            "contact_id": {"type": "string"},
            "call_id": {"type": "string"},
            "phone_number": {"type": "string"},
            "reason": {"type": "string"},
            "preferred_time": {"type": "string"},
        },
        "required": ["reason"],
    },
    sensitive=False, llm_allowed=True, user_confirmation_required=False,
))
async def create_callback_request(arguments: dict[str, Any]) -> dict[str, Any]:
    from app.models.call import ActionStatus, Callback, UrgencyLevel
    from app.models.notification import Notification, NotificationType

    reason = arguments["reason"]
    preferred_time = arguments.get("preferred_time")
    contact_id = _safe_uuid(arguments.get("contact_id"))
    call_id = _safe_uuid(arguments.get("call_id"))
    phone = arguments.get("phone_number", "Unknown")

    with _get_db_session() as db:
        cb = Callback(
            user_id="user_123",
            contact_id=contact_id,
            call_id=call_id,
            phone_number=phone,
            reason=reason,
            preferred_time=preferred_time,
            status=ActionStatus.PENDING,
        )
        db.add(cb)
        notif = Notification(
            user_id="user_123",
            call_id=call_id,
            title=f"📞 Callback Requested: {phone}",
            body=f"Reason: {reason}" + (f" (Time: {preferred_time})" if preferred_time else ""),
            notification_type=NotificationType.CALLBACK_REQUEST,
            urgency=UrgencyLevel.IMPORTANT,
        )
        db.add(notif)
        db.commit()
        db.refresh(cb)
        return {"status": "PENDING", "callback_id": str(cb.id)}


@tool(ToolMetadata(
    name="schedule_callback",
    description="Create scheduled callback action. Explicit user permission required.",
    input_schema={
        "type": "object",
        "properties": {
            "phone_number": {"type": "string"},
            "reason": {"type": "string"},
            "preferred_time": {"type": "string"},
        },
        "required": ["phone_number", "reason"],
    },
    sensitive=True, llm_allowed=False, user_confirmation_required=True,
))
async def schedule_callback(arguments: dict[str, Any]) -> dict[str, Any]:
    return await create_callback_request(arguments)


@tool(ToolMetadata(
    name="notify_user",
    description="Send a notification to the user.",
    input_schema={
        "type": "object",
        "properties": {
            "message": {"type": "string"},
            "urgency": {"type": "string"},
            "call_id": {"type": "string"},
        },
        "required": ["message"],
    },
    sensitive=False, llm_allowed=True, user_confirmation_required=False,
))
async def notify_user(arguments: dict[str, Any]) -> dict[str, Any]:
    from app.models.call import UrgencyLevel
    from app.models.notification import Notification, NotificationType

    msg = arguments["message"]
    urgency_str = arguments.get("urgency", "NORMAL").upper()
    urgency = UrgencyLevel(urgency_str) if urgency_str in UrgencyLevel.__members__ else UrgencyLevel.NORMAL
    call_id = _safe_uuid(arguments.get("call_id"))

    with _get_db_session() as db:
        notif = Notification(
            user_id="user_123",
            call_id=call_id,
            title="Assistant Alert",
            body=msg,
            notification_type=NotificationType.POLICY_ALERT if urgency == UrgencyLevel.NORMAL else NotificationType.URGENT_CALL,
            urgency=urgency,
        )
        db.add(notif)
        db.commit()
        return {"status": "notified", "notification_id": str(notif.id)}


@tool(ToolMetadata(
    name="mark_potentially_urgent",
    description="Flag a call as potentially urgent, record urgency event, and dispatch alert.",
    input_schema={
        "type": "object",
        "properties": {"call_id": {"type": "string"}, "reason": {"type": "string"}},
        "required": ["call_id", "reason"],
    },
    sensitive=False, llm_allowed=True, user_confirmation_required=False,
))
async def mark_potentially_urgent(arguments: dict[str, Any]) -> dict[str, Any]:
    from app.models.call import UrgencyEvent, UrgencyLevel
    from app.models.notification import Notification, NotificationType

    call_id = _safe_uuid(arguments["call_id"])
    reason = arguments["reason"]

    with _get_db_session() as db:
        event = UrgencyEvent(
            call_id=call_id,
            urgency_level=UrgencyLevel.POTENTIALLY_URGENT,
            reason=reason,
            alert_dispatched=True,
            reviewed_by_user=False,
        )
        db.add(event)
        notif = Notification(
            user_id="user_123",
            call_id=call_id,
            title="⚠️ Potentially Urgent Call Event",
            body=f"Call {call_id} flagged: {reason}",
            notification_type=NotificationType.URGENT_CALL,
            urgency=UrgencyLevel.POTENTIALLY_URGENT,
        )
        db.add(notif)
        db.commit()
        return {"status": "marked", "urgency_event_id": str(event.id)}


@tool(ToolMetadata(
    name="request_human_handoff",
    description="Initiate one-tap human takeover. AI immediately ceases speaking and call transfers.",
    input_schema={
        "type": "object",
        "properties": {"call_id": {"type": "string"}, "reason": {"type": "string"}},
        "required": ["call_id"],
    },
    sensitive=False, llm_allowed=True, user_confirmation_required=False,
))
async def request_human_handoff(arguments: dict[str, Any]) -> dict[str, Any]:
    from app.services.telephony import TelephonyService
    call_id = _safe_uuid(arguments["call_id"])
    with _get_db_session() as db:
        svc = TelephonyService(db, "user_123")
        res = svc.request_human_takeover(call_id)
        return res


@tool(ToolMetadata(
    name="end_call",
    description="Terminate call and initiate post-call intelligence processing.",
    input_schema={
        "type": "object",
        "properties": {"call_id": {"type": "string"}},
        "required": ["call_id"],
    },
    sensitive=False, llm_allowed=True, user_confirmation_required=False,
))
async def end_call(arguments: dict[str, Any]) -> dict[str, Any]:
    from app.services.telephony import TelephonyService
    call_id = _safe_uuid(arguments["call_id"])
    with _get_db_session() as db:
        svc = TelephonyService(db, "user_123")
        res = svc.end_call(call_id)
        return {"status": "ended", "result": res}


