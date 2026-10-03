"""
Telephony Adapter & Call Session Service: manages call lifecycle, speech events,
and one-tap human takeover (Section 3, 28, 30).
"""

import datetime
import uuid
from typing import Any

import structlog
from sqlalchemy.orm import Session

from app.core.utils import normalize_phone_number
from app.models.call import (
    Call,
    CallDirection,
    CallParticipant,
    CallStatus,
    CallTranscript,
    SpeakerType,
    UrgencyLevel,
)
from app.models.notification import Notification, NotificationType
from app.schemas.policy import PolicyEvaluationRequest
from app.services.contact import ContactIdentityService
from app.services.policy import PolicyEngine
from app.services.post_call import PostCallService

logger = structlog.get_logger(__name__)


class TelephonyService:
    def __init__(self, db: Session, user_id: str) -> None:
        self.db = db
        self.user_id = user_id

    def start_call(
        self,
        caller_phone: str,
        callee_phone: str | None = None,
        direction: CallDirection = CallDirection.INBOUND,
    ) -> dict[str, Any]:
        """Initiates a call, resolves caller identity, and evaluates policy before AI speaks."""
        normalized_caller = normalize_phone_number(caller_phone)

        # 1. Contact Identity lookup
        contact_svc = ContactIdentityService(self.db, self.user_id)
        identity = contact_svc.resolve_identity(normalized_caller)
        contact = contact_svc.get_contact_by_phone(normalized_caller)

        # 2. Create Call record
        call = Call(
            user_id=self.user_id,
            caller_phone=normalized_caller,
            callee_phone=callee_phone,
            contact_id=contact.id if contact else None,
            status=CallStatus.INCOMING,
            direction=direction,
            started_at=datetime.datetime.now(datetime.UTC),
        )
        self.db.add(call)
        self.db.commit()
        self.db.refresh(call)

        # Add participant records
        caller_part = CallParticipant(
            call_id=call.id,
            participant_type=SpeakerType.CALLER,
            phone_number=normalized_caller,
            name=identity.saved_name or identity.real_name or "Unknown",
        )
        assistant_part = CallParticipant(
            call_id=call.id,
            participant_type=SpeakerType.ASSISTANT,
            phone_number="AI_AGENT",
            name="Personal AI Assistant",
        )
        self.db.add_all([caller_part, assistant_part])
        self.db.commit()

        # 3. Policy Evaluation
        engine = PolicyEngine(self.db, self.user_id)
        policy_req = PolicyEvaluationRequest(
            call_id=str(call.id),
            contact_id=contact.id if contact else None,
            relationship=identity.relationship,
            relationship_status=identity.relationship_status,
            urgency="NORMAL",
        )
        policy_decision = engine.evaluate_call(policy_req)

        # Update call status based on policy
        if policy_decision.decision.value == "ANSWER":
            call.status = CallStatus.ACTIVE
        elif policy_decision.decision.value == "SCREEN":
            call.status = CallStatus.SCREENING
        elif policy_decision.decision.value == "REJECT":
            call.status = CallStatus.REJECTED
        else:
            call.status = CallStatus.ACTIVE

        self.db.commit()
        self.db.refresh(call)

        return {
            "call_id": str(call.id),
            "status": call.status.value,
            "policy_decision": policy_decision.decision.value,
            "reason": policy_decision.reason,
            "caller_name": identity.saved_name or identity.real_name or "Unknown",
            "relationship": identity.relationship,
        }

    def record_turn(
        self,
        call_id: uuid.UUID,
        speaker: SpeakerType,
        text: str,
        language: str = "en",
    ) -> CallTranscript:
        """Records a transcript turn."""
        call = self.db.get(Call, call_id)
        if not call:
            raise ValueError(f"Call {call_id} not found")

        transcript = CallTranscript(
            call_id=call_id,
            speaker=speaker,
            text=text,
            language=language,
            timestamp=datetime.datetime.now(datetime.UTC),
        )
        self.db.add(transcript)
        self.db.commit()
        self.db.refresh(transcript)
        return transcript

    def request_human_takeover(self, call_id: uuid.UUID) -> dict[str, Any]:
        """
        One-tap Human Takeover / Handoff.
        Immediately switches call status to HANDOFF, stops AI speaking, and alerts user.
        """
        call = self.db.get(Call, call_id)
        if not call:
            raise ValueError(f"Call {call_id} not found")

        call.status = CallStatus.HANDOFF
        self.db.commit()

        # Add system transcript noting handover
        sys_turn = CallTranscript(
            call_id=call_id,
            speaker=SpeakerType.SYSTEM,
            text="AI stopped speaking: Human takeover initiated by user.",
            language="en",
            timestamp=datetime.datetime.now(datetime.UTC),
        )
        self.db.add(sys_turn)

        # High priority takeover notification
        notif = Notification(
            user_id=self.user_id,
            call_id=call_id,
            title="📞 Human Takeover Active",
            body=f"You have taken over call from {call.caller_phone}. AI is now silent.",
            notification_type=NotificationType.TAKEOVER_REQUEST,
            urgency=UrgencyLevel.IMPORTANT,
            is_read=False,
            extra_data={"call_id": str(call_id), "caller_phone": call.caller_phone},
        )
        self.db.add(notif)
        self.db.commit()

        logger.info("human_takeover_activated", call_id=str(call_id))
        return {
            "call_id": str(call_id),
            "status": CallStatus.HANDOFF.value,
            "ai_speaking": False,
            "message": "AI has stopped speaking. Call joined by human.",
        }

    def end_call(self, call_id: uuid.UUID) -> dict[str, Any]:
        """Ends call and triggers post-call intelligence."""
        call = self.db.get(Call, call_id)
        if not call:
            raise ValueError(f"Call {call_id} not found")

        if call.status != CallStatus.HANDOFF:
            call.status = CallStatus.COMPLETED

        ended = datetime.datetime.now(datetime.UTC)
        started = call.started_at
        if started.tzinfo is None:
            started = started.replace(tzinfo=datetime.UTC)
        call.ended_at = ended
        call.duration_seconds = max(1, int((ended - started).total_seconds()))
        self.db.commit()

        # Run Post-Call Intelligence
        post_call_svc = PostCallService(self.db, self.user_id)
        result = post_call_svc.process_call(call_id)

        return result
