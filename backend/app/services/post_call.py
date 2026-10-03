"""
Post-Call Intelligence Service: processes completed calls, extracts summaries,
detects urgency, generates actions/callbacks, suggests relationships, and notifies the user.
Implements Sections 16, 18, 19 of the architecture specification.
"""

import datetime
import re
import uuid
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.call import (
    ActionStatus,
    ActionType,
    Call,
    CallAction,
    Callback,
    CallStatus,
    CallSummary,
    CallTranscript,
    UrgencyEvent,
    UrgencyLevel,
)
from app.models.contact import (
    AliasSource,
    Contact,
    ContactAlias,
    RelationshipSuggestion,
    RelationshipType,
    SuggestionStatus,
)
from app.models.notification import Notification, NotificationType

logger = structlog.get_logger(__name__)

# Keywords for urgency classification (English and Tamil/Tanglish)
EMERGENCY_KEYWORDS = [
    "emergency", "hospital", "doctor", "accident", "ambulance",
    "maruthuvamanai", "icu"
]

POTENTIALLY_URGENT_KEYWORDS = [
    "production server down", "server down", "outage", "system down",
    "critical bug", "sev 1", "sev 2", "client escalat", "threat", "breach",
    "flight cancelled", "police", "urgent", "avasiyam", "danger"
]

IMPORTANT_KEYWORDS = [
    "deadline", "asap", "as soon as possible", "important", "mukkiyam",
    "today itself", "approval needed", "sign off"
]

CALLBACK_PATTERNS = [
    re.compile(r"call (?:me )?back(?:\s+(?:at|around|by)\s+([0-9:\sAPMapm]+))?", re.IGNORECASE),
    re.compile(r"thirumba call panna sollunga", re.IGNORECASE),
    re.compile(r"call panna sollunga", re.IGNORECASE),
    re.compile(r"reach out", re.IGNORECASE),
]

SELF_IDENTIFY_PATTERNS = [
    re.compile(r"naan\s+([a-zA-Z]+)(?:\s+pesuren|\s+dhaan)", re.IGNORECASE),
    re.compile(r"this is\s+([a-zA-Z]+)", re.IGNORECASE),
    re.compile(r"i am\s+([a-zA-Z]+)", re.IGNORECASE),
    re.compile(r"ennoda peru\s+([a-zA-Z]+)", re.IGNORECASE),
]


class PostCallService:
    def __init__(self, db: Session, user_id: str) -> None:
        self.db = db
        self.user_id = user_id

    def process_call(self, call_id: uuid.UUID) -> dict[str, Any]:
        """Analyzes a call and creates summaries, actions, urgency events, and notifications."""
        call = self.db.get(Call, call_id)
        if not call:
            raise ValueError(f"Call with id {call_id} not found")

        # Gather transcripts
        transcripts = self.db.scalars(
            select(CallTranscript)
            .where(CallTranscript.call_id == call_id)
            .order_by(CallTranscript.timestamp)
        ).all()

        full_text = " ".join([t.text for t in transcripts]).lower()

        # 1. Classify Urgency
        urgency = self._classify_urgency(full_text)

        # 2. Extract Intent and Reason
        intent, reason = self._extract_intent_and_reason(transcripts)

        # 3. Create Summary
        summary_text = self._generate_summary(call, transcripts, reason)

        # 4. Save CallSummary (Idempotent: update if existing, else add)
        existing_summary = self.db.scalars(
            select(CallSummary).where(CallSummary.call_id == call.id)
        ).first()

        if existing_summary:
            summary = existing_summary
        else:
            summary = CallSummary(
                call_id=call.id,
                caller_phone=call.caller_phone,
                summary_text=summary_text,
                intent=intent,
                reason=reason,
                urgency_level=urgency,
                relationship_type="UNKNOWN",
                relationship_confidence=1.0,
                extra_metadata={"turns_count": len(transcripts)},
            )
            self.db.add(summary)

        # 5. Extract Actions & Callbacks
        extracted_actions = self._extract_actions(call, transcripts)
        for act in extracted_actions:
            self.db.add(act)

        # 6. Extract Callback Requests
        self._extract_callbacks(call, transcripts)

        # 7. Record UrgencyEvent if urgent
        if urgency in (UrgencyLevel.POTENTIALLY_URGENT, UrgencyLevel.EMERGENCY_CLAIM):
            urg_event = UrgencyEvent(
                call_id=call.id,
                urgency_level=urgency,
                reason=f"Detected urgent keywords in call from {call.caller_phone}: {reason}",
                alert_dispatched=True,
                reviewed_by_user=False,
            )
            self.db.add(urg_event)

        # 8. Check for self-identified name/relationship suggestion
        suggestion_created = self._extract_relationship_suggestion(call, full_text)

        # 9. Generate Notification for User
        self._create_notification(call, urgency, summary_text, reason)

        # Mark call as completed if not already
        if call.status != CallStatus.HANDOFF:
            call.status = CallStatus.COMPLETED
            if not call.ended_at:
                ended = datetime.datetime.now(datetime.UTC)
                started = call.started_at
                if started.tzinfo is None:
                    started = started.replace(tzinfo=datetime.UTC)
                call.ended_at = ended
                call.duration_seconds = max(1, int((ended - started).total_seconds()))

        self.db.commit()
        self.db.refresh(summary)

        logger.info(
            "post_call_processed",
            call_id=str(call_id),
            urgency=urgency.value,
            intent=intent,
            actions_count=len(extracted_actions),
        )

        return {
            "call_id": str(call.id),
            "summary": summary_text,
            "intent": intent,
            "reason": reason,
            "urgency": urgency.value,
            "actions_count": len(extracted_actions),
            "suggestion_created": suggestion_created,
        }

    def _classify_urgency(self, text: str) -> UrgencyLevel:
        for kw in EMERGENCY_KEYWORDS:
            if kw in text:
                return UrgencyLevel.EMERGENCY_CLAIM

        for kw in POTENTIALLY_URGENT_KEYWORDS:
            if kw in text:
                return UrgencyLevel.POTENTIALLY_URGENT

        for kw in IMPORTANT_KEYWORDS:
            if kw in text:
                return UrgencyLevel.IMPORTANT

        return UrgencyLevel.NORMAL

    def _extract_intent_and_reason(self, transcripts: list[CallTranscript]) -> tuple[str, str]:
        if not transcripts:
            return "Missed / No audio", "No conversation recorded"

        caller_messages = [t.text for t in transcripts if t.speaker.value == "CALLER"]
        if not caller_messages:
            return "Outgoing message only", "Caller did not respond"

        combined = " ".join(caller_messages)
        intent = "Inquiry / Message"
        if any(term in combined.lower() for term in ("server", "bug", "deployment", "issue", "down")):
            intent = "Technical / Infrastructure Alert"
        elif any(term in combined.lower() for term in ("meeting", "schedule", "catch up", "lunch", "dinner")):
            intent = "Scheduling / Meeting Request"
        elif any(term in combined.lower() for term in ("hospital", "accident", "emergency")):
            intent = "Urgent Personal Matter"

        # Extract primary reason snippet
        first_meaningful = caller_messages[0]
        reason = first_meaningful[:120] + ("..." if len(first_meaningful) > 120 else "")
        return intent, reason

    def _generate_summary(self, call: Call, transcripts: list[CallTranscript], reason: str) -> str:
        caller_label = call.caller_phone
        duration = f"{call.duration_seconds}s" if call.duration_seconds else "brief"
        turns = len(transcripts)
        return (
            f"Call from {caller_label} ({duration}, {turns} turns). "
            f"Reason: {reason}"
        )

    def _extract_actions(self, call: Call, transcripts: list[CallTranscript]) -> list[CallAction]:
        actions: list[CallAction] = []
        for t in transcripts:
            if t.speaker.value == "CALLER":
                text = t.text
                for pattern in CALLBACK_PATTERNS:
                    match = pattern.search(text)
                    if match:
                        time_pref = match.group(1) if match.groups() else None
                        desc = f"Call back {call.caller_phone}" + (f" around {time_pref}" if time_pref else "")
                        actions.append(
                            CallAction(
                                call_id=call.id,
                                action_type=ActionType.CALLBACK,
                                description=desc,
                                status=ActionStatus.PENDING,
                            )
                        )
                        break
        return actions

    def _extract_callbacks(self, call: Call, transcripts: list[CallTranscript]) -> None:
        for t in transcripts:
            if t.speaker.value == "CALLER":
                for pattern in CALLBACK_PATTERNS:
                    match = pattern.search(t.text)
                    if match:
                        pref = match.group(1).strip() if (match.groups() and match.group(1)) else None
                        cb = Callback(
                            user_id=self.user_id,
                            contact_id=call.contact_id,
                            call_id=call.id,
                            phone_number=call.caller_phone,
                            reason=t.text,
                            preferred_time=pref,
                            status=ActionStatus.PENDING,
                        )
                        self.db.add(cb)
                        return

    def _extract_relationship_suggestion(self, call: Call, text: str) -> bool:
        """Finds if caller self-identified (e.g. 'Naan Karthik pesuren' or 'This is Arun')."""
        if not call.contact_id:
            return False

        for pattern in SELF_IDENTIFY_PATTERNS:
            match = pattern.search(text)
            if match:
                suggested_name = match.group(1).capitalize()
                contact = self.db.get(Contact, call.contact_id)
                if contact and contact.saved_name and contact.saved_name.lower() != suggested_name.lower():
                    # Create suggestion instead of silently overwriting
                    sugg = RelationshipSuggestion(
                        contact_id=contact.id,
                        suggested_name=suggested_name,
                        suggested_relationship=RelationshipType.FRIEND,
                        confidence=0.85,
                        reason=f"Caller self-identified as '{suggested_name}' during call",
                        status=SuggestionStatus.SUGGESTED,
                    )
                    self.db.add(sugg)

                    # Add suggested alias
                    alias = ContactAlias(
                        contact_id=contact.id,
                        alias=suggested_name,
                        alias_type="SELF_IDENTIFIED",
                        source=AliasSource.CALLER_IDENTIFICATION,
                        status=SuggestionStatus.SUGGESTED,
                    )
                    self.db.add(alias)
                    return True
        return False

    def _create_notification(self, call: Call, urgency: UrgencyLevel, summary: str, reason: str) -> None:
        title = f"Call received: {call.caller_phone}"
        ntype = NotificationType.SUMMARY

        if urgency == UrgencyLevel.EMERGENCY_CLAIM:
            title = f"🚨 EMERGENCY CLAIM: Call from {call.caller_phone}"
            ntype = NotificationType.URGENT_CALL
        elif urgency == UrgencyLevel.POTENTIALLY_URGENT:
            title = f"⚠️ Potentially Urgent: Call from {call.caller_phone}"
            ntype = NotificationType.URGENT_CALL

        notif = Notification(
            user_id=self.user_id,
            call_id=call.id,
            title=title,
            body=f"{summary} | Urgency: {urgency.value}",
            notification_type=ntype,
            urgency=urgency,
            is_read=False,
            extra_data={"caller_phone": call.caller_phone, "reason": reason},
        )
        self.db.add(notif)
