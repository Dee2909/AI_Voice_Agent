"""
Tests for Real-Time Bidirectional Audio Bridge, Telephony Adapter, VAD, STT, TTS,
Barge-in handling, and Asterisk Webhook / WebSocket integration.
"""

import os
import struct

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ["DATABASE_URL"] = "sqlite:///./test.db"
os.environ["ENVIRONMENT"] = "test"
os.environ["MOCK_LLM_ENABLED"] = "true"

import app.models  # noqa: F401
from app.core.database import Base, get_db
from app.main import api_app
from app.models.call import Call
from app.voice.audio_bridge import LiveAudioBridgeSession
from app.voice.stt import FasterWhisperSTT
from app.voice.tts import IndicTTSProvider
from app.voice.vad import SileroVADProvider

engine = create_engine("sqlite:///./test.db", connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


api_app.dependency_overrides[get_db] = override_get_db
client = TestClient(api_app)


def test_vad_silence_and_speech():
    vad = SileroVADProvider()
    # 20ms of 16kHz 16-bit mono PCM is 320 samples = 640 bytes
    silent_frame = b"\x00" * 640
    assert not vad.is_speech(silent_frame)

    # Synthetic noisy/loud sine wave frame
    loud_frame = bytearray()
    for i in range(320):
        val = 10000 * (1 if (i % 20) < 10 else -1)
        loud_frame.extend(struct.pack("<h", val))
    assert vad.is_speech(bytes(loud_frame))


def test_stt_transcription():
    stt = FasterWhisperSTT(model_size="base", compute_type="int8")
    # Empty audio or short tone
    transcription = stt.transcribe(b"\x00" * 3200, language="en")
    assert transcription is not None
    assert isinstance(transcription.text, str)


def test_tts_generation():
    tts = IndicTTSProvider()
    result = tts.synthesize("Vanakkam, eppadi irukkeenga?", language="ta")
    assert result.audio_bytes is not None
    assert len(result.audio_bytes) > 0
    assert result.sample_rate == 16000


@pytest.mark.asyncio
async def test_live_audio_bridge_session_turn():
    db = TestingSessionLocal()
    try:
        # Create a test call record
        call = Call(
            user_id="default-user-id",
            caller_phone="+919876543210",
            status="ACTIVE",
        )
        db.add(call)
        db.commit()
        db.refresh(call)
        call_id = call.id

        received_chunks = []

        async def send_callback(chunk: bytes):
            received_chunks.append(chunk)

        session = LiveAudioBridgeSession(
            call_id=call_id,
            user_id="default-user-id",
            caller_phone="+919876543210",
            send_audio_callback=send_callback,
            db_session=db,
        )

        # Trigger an AI response
        await session._play_ai_response("Vanakkam Deenan, eppadi irukkeenga?", "ta")
        assert len(received_chunks) > 0

        # Test barge-in interruption
        session.is_ai_speaking = True
        await session.interrupt_ai_speech()
        assert session.is_ai_speaking is False

        # Close session
        result = await session.close()
        assert result.get("status") == "ended" or session.is_active is False
    finally:
        db.close()


def test_asterisk_ari_event_webhook():
    Base.metadata.create_all(bind=engine)
    # 1. StasisStart event
    start_payload = {
        "type": "StasisStart",
        "channel": {
            "id": "chan-asterisk-001",
            "caller": {"number": "+919876543211", "name": "Mom"},
        },
    }
    response = client.post("/api/v1/telephony/asterisk/ari-event", json=start_payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "connected"
    assert "call_id" in data

    # 2. StasisEnd event
    end_payload = {
        "type": "StasisEnd",
        "channel": {
            "id": "chan-asterisk-001",
            "caller": {"number": "+919876543211", "name": "Mom"},
        },
    }
    response2 = client.post("/api/v1/telephony/asterisk/ari-event", json=end_payload)
    assert response2.status_code == 200
    assert response2.json()["status"] == "hangup_processed"


def test_websocket_audio_stream_lifecycle():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        call = Call(
            user_id="default-user-id",
            caller_phone="+919876543212",
            status="INCOMING",
        )
        db.add(call)
        db.commit()
        db.refresh(call)
        call_id = call.id
    finally:
        db.close()

    with client.websocket_connect(f"/api/v1/telephony/ws/audio-stream/{call_id}") as ws:
        # Send 20ms of audio frame (640 bytes)
        ws.send_bytes(b"\x00" * 640)
        # Close connection normally
        ws.close()
