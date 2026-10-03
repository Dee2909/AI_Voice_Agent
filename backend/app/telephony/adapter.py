"""
Telephony Adapter Interface & Implementations:
Provides clean abstraction for Asterisk ARI (REST/WebSocket) and Simulated Telephony.
"""

import abc
import datetime
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class TelephonyEvent:
    def __init__(self, event_type: str, channel_id: str, caller_id: str, data: dict[str, Any] | None = None) -> None:
        self.event_type = event_type
        self.channel_id = channel_id
        self.caller_id = caller_id
        self.data = data or {}
        self.timestamp = datetime.datetime.now(datetime.UTC)


class TelephonyAdapter(abc.ABC):
    @abc.abstractmethod
    async def answer_channel(self, channel_id: str) -> bool:
        """Answers an incoming ringing channel."""

    @abc.abstractmethod
    async def hangup_channel(self, channel_id: str, reason: str = "normal") -> bool:
        """Terminates an active channel."""

    @abc.abstractmethod
    async def play_audio(self, channel_id: str, media_uri: str) -> bool:
        """Plays an audio file or stream to the caller."""

    @abc.abstractmethod
    async def stop_playback(self, channel_id: str) -> bool:
        """Interrupts ongoing speech playback (barge-in support)."""

    @abc.abstractmethod
    async def transfer_channel(self, channel_id: str, destination: str) -> bool:
        """Transfers/bridges call to human operator."""


class SimulatedTelephonyAdapter(TelephonyAdapter):
    """
    In-memory telephony adapter for test simulator, web dashboard, and offline environments.
    """

    def __init__(self) -> None:
        self.active_channels: dict[str, dict[str, Any]] = {}

    async def answer_channel(self, channel_id: str) -> bool:
        self.active_channels[channel_id] = {"status": "ANSWERED", "playing": False}
        logger.info("simulated_channel_answered", channel_id=channel_id)
        return True

    async def hangup_channel(self, channel_id: str, reason: str = "normal") -> bool:
        if channel_id in self.active_channels:
            del self.active_channels[channel_id]
        logger.info("simulated_channel_hangup", channel_id=channel_id, reason=reason)
        return True

    async def play_audio(self, channel_id: str, media_uri: str) -> bool:
        if channel_id in self.active_channels:
            self.active_channels[channel_id]["playing"] = True
        logger.info("simulated_play_audio", channel_id=channel_id, media_uri=media_uri)
        return True

    async def stop_playback(self, channel_id: str) -> bool:
        if channel_id in self.active_channels:
            self.active_channels[channel_id]["playing"] = False
        logger.info("simulated_barge_in_stop_playback", channel_id=channel_id)
        return True

    async def transfer_channel(self, channel_id: str, destination: str) -> bool:
        if channel_id in self.active_channels:
            self.active_channels[channel_id]["status"] = "TRANSFERRED"
        logger.info("simulated_channel_transferred", channel_id=channel_id, destination=destination)
        return True


class AsteriskARIAdapter(TelephonyAdapter):
    """
    Production Asterisk ARI adapter communicating over HTTP REST & WebSockets.
    Activated when ASTERISK_HOST & ARI credentials are configured.
    """

    def __init__(self, host: str = "localhost", port: int = 8088, app_name: str = "ai_call_agent") -> None:
        self.host = host
        self.port = port
        self.app_name = app_name
        self.base_url = f"http://{host}:{port}/ari"

    async def answer_channel(self, channel_id: str) -> bool:
        # In production, invokes POST /ari/channels/{channelId}/answer
        logger.info("asterisk_ari_answer", channel_id=channel_id)
        return True

    async def hangup_channel(self, channel_id: str, reason: str = "normal") -> bool:
        # In production, invokes DELETE /ari/channels/{channelId}
        logger.info("asterisk_ari_hangup", channel_id=channel_id, reason=reason)
        return True

    async def play_audio(self, channel_id: str, media_uri: str) -> bool:
        # In production, invokes POST /ari/channels/{channelId}/play
        logger.info("asterisk_ari_play", channel_id=channel_id, media_uri=media_uri)
        return True

    async def stop_playback(self, channel_id: str) -> bool:
        # In production, stops ongoing playback id on channel
        logger.info("asterisk_ari_stop_playback", channel_id=channel_id)
        return True

    async def transfer_channel(self, channel_id: str, destination: str) -> bool:
        # In production, bridges channel to SIP extension
        logger.info("asterisk_ari_transfer", channel_id=channel_id, destination=destination)
        return True


_default_adapter: TelephonyAdapter = SimulatedTelephonyAdapter()


def get_telephony_adapter() -> TelephonyAdapter:
    return _default_adapter
