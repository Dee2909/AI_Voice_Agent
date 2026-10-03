"""
Telephony Streaming & Asterisk Event Router:
Provides WebSocket and REST endpoints for real-time bidirectional audio streaming,
barge-in cancellation, and Asterisk ARI Stasis event lifecycle hooks.
"""

import uuid
from typing import Any

import structlog
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user_id
from app.models.call import CallDirection
from app.services.telephony import TelephonyService
from app.voice.audio_bridge import LiveAudioBridgeSession

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/telephony", tags=["telephony"])

# In-memory active bridge sessions
_active_bridge_sessions: dict[str, LiveAudioBridgeSession] = {}


class ARIEventPayload(BaseModel):
    type: str = Field(..., description="ARI Event type e.g. StasisStart, StasisEnd, ChannelHangupRequest")
    channel: dict[str, Any] = Field(default_factory=dict)
    application: str = "ai_call_agent"
    timestamp: str | None = None


@router.post("/asterisk/ari-event")
def handle_asterisk_ari_event(
    event: ARIEventPayload,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """
    Receives Asterisk ARI Stasis application events (StasisStart, StasisEnd, ChannelHangupRequest).
    """
    event_type = event.type
    channel_data = event.channel
    channel_id = channel_data.get("id", str(uuid.uuid4()))
    caller_phone = channel_data.get("caller", {}).get("number", "+910000000000")

    telephony_svc = TelephonyService(db, user_id)

    if event_type == "StasisStart":
        # New call entered Asterisk Stasis application
        call_res = telephony_svc.start_call(caller_phone=caller_phone, direction=CallDirection.INBOUND)
        logger.info("asterisk_stasis_start", channel_id=channel_id, call_id=call_res["call_id"])
        return {
            "status": "connected",
            "call_id": call_res["call_id"],
            "policy_decision": call_res["policy_decision"],
            "ws_stream_url": f"/api/v1/telephony/ws/audio-stream/{call_res['call_id']}",
        }

    elif event_type in ("StasisEnd", "ChannelHangupRequest"):
        # Find and close active bridge session if any
        for cid, sess in list(_active_bridge_sessions.items()):
            if sess.caller_phone == caller_phone:
                _active_bridge_sessions.pop(cid, None)
                break
        logger.info("asterisk_stasis_end", channel_id=channel_id)
        return {"status": "hangup_processed"}

    return {"status": "event_acknowledged", "event_type": event_type}


@router.websocket("/ws/audio-stream/{call_id}")
async def websocket_audio_stream(websocket: WebSocket, call_id: uuid.UUID) -> None:
    """
    Real-time bidirectional WebSocket audio bridge.
    - Receives incoming caller 16-bit 16kHz PCM audio bytes from Asterisk / Simulator.
    - Transmits synthesized AI voice responses back to caller.
    """
    await websocket.accept()
    logger.info("telephony_ws_connected", call_id=str(call_id))

    async def send_audio_to_caller(audio_chunk: bytes) -> None:
        try:
            await websocket.send_bytes(audio_chunk)
        except Exception as e:
            logger.debug("telephony_ws_send_failed", call_id=str(call_id), error=str(e))

    # Create live session
    session = LiveAudioBridgeSession(
        call_id=call_id,
        user_id="user_123",
        caller_phone="+910000000000",
        send_audio_callback=send_audio_to_caller,
    )
    _active_bridge_sessions[str(call_id)] = session

    try:
        while True:
            # Receive binary PCM audio chunk from caller
            data = await websocket.receive_bytes()
            if data:
                await session.handle_incoming_pcm_chunk(data)
    except WebSocketDisconnect:
        logger.info("telephony_ws_disconnected", call_id=str(call_id))
    except Exception as e:
        logger.error("telephony_ws_error", call_id=str(call_id), error=str(e))
    finally:
        _active_bridge_sessions.pop(str(call_id), None)
        await session.close()
