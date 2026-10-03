"""
Calls API: endpoints for call lifecycle, turn simulation/processing,
transcripts, summaries, and human takeover.
"""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.orchestrator import get_orchestrator
from app.core.database import get_db
from app.core.security import get_current_user_id
from app.models.call import (
    Call,
    CallDirection,
    CallStatus,
    CallSummary,
    CallTranscript,
    SpeakerType,
)
from app.services.telephony import TelephonyService

router = APIRouter(prefix="/calls", tags=["calls"])


class IncomingCallRequest(BaseModel):
    caller_phone: str = Field(..., description="E.164 normalized or raw phone number")
    callee_phone: str | None = None
    direction: CallDirection = CallDirection.INBOUND


class CallTurnRequest(BaseModel):
    speaker: SpeakerType = SpeakerType.CALLER
    message: str = Field(..., description="Transcript of what the speaker said")
    language: str = "en"


@router.post("/incoming")
def start_incoming_call(
    call_in: IncomingCallRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    svc = TelephonyService(db, user_id)
    return svc.start_call(
        caller_phone=call_in.caller_phone,
        callee_phone=call_in.callee_phone,
        direction=call_in.direction,
    )


@router.post("/{call_id}/turn")
async def process_call_turn(
    call_id: uuid.UUID,
    turn_in: CallTurnRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    call = db.get(Call, call_id)
    if not call or call.user_id != user_id:
        raise HTTPException(status_code=404, detail="Call not found")

    if call.status == CallStatus.HANDOFF:
        return {
            "call_id": str(call_id),
            "status": "HANDOFF",
            "assistant_response": None,
            "ai_speaking": False,
            "message": "Human takeover active. AI is silent.",
        }

    svc = TelephonyService(db, user_id)

    # 1. Record caller turn
    svc.record_turn(
        call_id=call_id,
        speaker=turn_in.speaker,
        text=turn_in.message,
        language=turn_in.language,
    )

    # 2. Run agent orchestrator
    orchestrator = get_orchestrator()
    agent_result = await orchestrator.run(
        conversation_id=str(call_id),
        user_message=turn_in.message,
        call_id=str(call_id),
        context={"caller_phone": call.caller_phone, "status": call.status.value},
    )

    response_text = agent_result.get("response", "")

    # 3. Record assistant response in transcript
    svc.record_turn(
        call_id=call_id,
        speaker=SpeakerType.ASSISTANT,
        text=response_text,
        language=turn_in.language,
    )

    return {
        "call_id": str(call_id),
        "status": call.status.value,
        "assistant_response": response_text,
        "ai_speaking": True,
        "tool_calls": agent_result.get("tool_calls", []),
    }


@router.post("/{call_id}/takeover")
def request_human_takeover(
    call_id: uuid.UUID,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    svc = TelephonyService(db, user_id)
    try:
        return svc.request_human_takeover(call_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{call_id}/end")
def end_call(
    call_id: uuid.UUID,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    svc = TelephonyService(db, user_id)
    try:
        return svc.end_call(call_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{call_id}")
def get_call_detail(
    call_id: uuid.UUID,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    call = db.get(Call, call_id)
    if not call or call.user_id != user_id:
        raise HTTPException(status_code=404, detail="Call not found")

    return {
        "call_id": str(call.id),
        "caller_phone": call.caller_phone,
        "status": call.status.value,
        "direction": call.direction.value,
        "duration_seconds": call.duration_seconds,
        "started_at": call.started_at.isoformat() if call.started_at else None,
        "ended_at": call.ended_at.isoformat() if call.ended_at else None,
    }


@router.get("/{call_id}/transcript")
def get_call_transcript(
    call_id: uuid.UUID,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> list[dict[str, Any]]:
    call = db.get(Call, call_id)
    if not call or call.user_id != user_id:
        raise HTTPException(status_code=404, detail="Call not found")

    transcripts = db.scalars(
        select(CallTranscript)
        .where(CallTranscript.call_id == call_id)
        .order_by(CallTranscript.timestamp)
    ).all()

    return [
        {
            "id": str(t.id),
            "speaker": t.speaker.value,
            "text": t.text,
            "language": t.language,
            "timestamp": t.timestamp.isoformat(),
        }
        for t in transcripts
    ]


@router.get("/{call_id}/summary")
def get_call_summary(
    call_id: uuid.UUID,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    call = db.get(Call, call_id)
    if not call or call.user_id != user_id:
        raise HTTPException(status_code=404, detail="Call not found")

    summary = db.scalars(
        select(CallSummary).where(CallSummary.call_id == call_id)
    ).first()

    if not summary:
        raise HTTPException(status_code=404, detail="Summary not found for this call")

    return {
        "call_id": str(summary.call_id),
        "summary": summary.summary_text,
        "intent": summary.intent,
        "reason": summary.reason,
        "urgency": summary.urgency_level.value,
        "relationship_type": summary.relationship_type,
    }
