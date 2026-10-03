"""
Call Session Manager: Maintains in-memory session states, turn history,
barge-in interruption tracking, and audio playback states for concurrent active calls.
"""

import datetime
import uuid
from typing import Any

from app.telephony.adapter import TelephonyAdapter, get_telephony_adapter


class CallSession:
    def __init__(
        self,
        call_id: uuid.UUID,
        user_id: str,
        caller_phone: str,
        channel_id: str | None = None,
    ) -> None:
        self.call_id = call_id
        self.user_id = user_id
        self.caller_phone = caller_phone
        self.channel_id = channel_id or str(call_id)
        self.created_at = datetime.datetime.now(datetime.UTC)
        self.is_ai_speaking = False
        self.is_human_takeover = False
        self.turns_count = 0
        self.metadata: dict[str, Any] = {}

    def start_speaking(self) -> None:
        self.is_ai_speaking = True

    def stop_speaking(self) -> None:
        self.is_ai_speaking = False


class CallSessionManager:
    def __init__(self, adapter: TelephonyAdapter | None = None) -> None:
        self.adapter = adapter or get_telephony_adapter()
        self._sessions: dict[str, CallSession] = {}

    def create_session(
        self,
        call_id: uuid.UUID,
        user_id: str,
        caller_phone: str,
        channel_id: str | None = None,
    ) -> CallSession:
        sess = CallSession(
            call_id=call_id,
            user_id=user_id,
            caller_phone=caller_phone,
            channel_id=channel_id,
        )
        self._sessions[str(call_id)] = sess
        return sess

    def get_session(self, call_id: uuid.UUID | str) -> CallSession | None:
        return self._sessions.get(str(call_id))

    def end_session(self, call_id: uuid.UUID | str) -> CallSession | None:
        return self._sessions.pop(str(call_id), None)

    async def handle_barge_in(self, call_id: uuid.UUID | str) -> bool:
        """Interrupts ongoing AI speech if caller interrupts."""
        sess = self.get_session(call_id)
        if not sess or not sess.is_ai_speaking:
            return False

        sess.stop_speaking()
        await self.adapter.stop_playback(sess.channel_id)
        return True


_session_manager = CallSessionManager()


def get_call_session_manager() -> CallSessionManager:
    return _session_manager
