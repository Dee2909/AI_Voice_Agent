"""
Real-Time Bidirectional Audio Bridge:
Handles live streaming audio between Asterisk/telephony channels and the AI Voice Agent.
Performs continuous VAD utterance detection, STT transcription, Ollama orchestrator reasoning,
Tamil TTS synthesis, and live audio playback with low latency and barge-in cancellation.
"""

import asyncio
import uuid
from collections.abc import Callable
from typing import Any

import structlog
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.call import SpeakerType
from app.services.telephony import TelephonyService
from app.voice.pipeline import get_voice_pipeline
from app.voice.stt import get_stt_provider
from app.voice.tts import get_tts_provider
from app.voice.vad import get_vad_provider

logger = structlog.get_logger(__name__)


class LiveAudioBridgeSession:
    """
    Represents a single active telephone call's real-time audio session.
    """

    def __init__(
        self,
        call_id: uuid.UUID,
        user_id: str,
        caller_phone: str,
        send_audio_callback: Callable[[bytes], Any] | None = None,
        db_session: Session | None = None,
    ) -> None:
        self.call_id = call_id
        self.user_id = user_id
        self.caller_phone = caller_phone
        self.send_audio_callback = send_audio_callback
        self.db = db_session or SessionLocal()
        self._owns_db = db_session is None

        self.is_active = True
        self.is_ai_speaking = False
        self.is_processing_turn = False
        self.is_human_takeover = False

        self.vad = get_vad_provider()
        self.stt = get_stt_provider()
        self.tts = get_tts_provider()
        self.pipeline = get_voice_pipeline()
        self.telephony_svc = TelephonyService(self.db, self.user_id)

        # Audio buffering state
        self._audio_buffer = bytearray()
        self._speech_detected = False
        self._silence_frames = 0
        self._speech_frames = 0
        self._sample_rate = 16000
        self._chunk_size_ms = 20  # 20ms chunks = 640 bytes for 16kHz 16-bit mono

        # Interruption / Barge-in lock
        self._current_turn_task: asyncio.Task[Any] | None = None

    async def handle_incoming_pcm_chunk(self, chunk: bytes) -> None:
        """
        Receives raw 16-bit 16kHz PCM audio chunk from Asterisk/telephony stream.
        """
        if not self.is_active or self.is_human_takeover:
            return

        is_speech = self.vad.is_speech(chunk, self._sample_rate)

        # Barge-in check: If AI is speaking and caller speaks, cancel playback immediately
        if self.is_ai_speaking and is_speech:
            logger.info("barge_in_interruption_detected", call_id=str(self.call_id))
            await self.interrupt_ai_speech()

        if is_speech:
            self._speech_detected = True
            self._speech_frames += 1
            self._silence_frames = 0
            self._audio_buffer.extend(chunk)
        else:
            if self._speech_detected:
                self._silence_frames += 1
                self._audio_buffer.extend(chunk)

                # ~600ms of silence after speech indicates end of utterance (30 frames * 20ms)
                if self._silence_frames >= 30:
                    await self._on_utterance_complete()

    async def _on_utterance_complete(self) -> None:
        """Triggered when caller finishes speaking an utterance."""
        if len(self._audio_buffer) < 3200:  # Ignore clicks/pops < 100ms
            self._reset_audio_state()
            return

        captured_audio = bytes(self._audio_buffer)
        self._reset_audio_state()

        # Launch turn processing task
        self._current_turn_task = asyncio.create_task(self._process_turn(captured_audio))

    async def _process_turn(self, audio_bytes: bytes) -> None:
        """Transcribes speech, runs orchestrator, and streams synthesized Tamil TTS audio."""
        self.is_processing_turn = True
        try:
            # 1. Transcribe speech
            stt_res = self.stt.transcribe(audio_bytes, sample_rate=self._sample_rate)
            transcript_text = stt_res.text.strip()

            if not transcript_text:
                fallback_msg = "Mannikkavum, neenga sonnathu sariyaa kekkala. Innoruthadavai sollunga."
                await self._play_ai_response(fallback_msg, "ta")
                return

            logger.info(
                "caller_speech_transcribed",
                call_id=str(self.call_id),
                text=transcript_text,
                language=stt_res.language,
            )

            # Record turn in database
            self.telephony_svc.record_turn(
                call_id=self.call_id,
                speaker=SpeakerType.CALLER,
                text=transcript_text,
                language=stt_res.language,
            )

            # 2. Run Agent Orchestrator with Ollama
            orchestrator = self.pipeline.orchestrator
            agent_result = await orchestrator.run(
                conversation_id=str(self.call_id),
                user_message=transcript_text,
                call_id=str(self.call_id),
                context={"caller_phone": self.caller_phone},
            )

            response_text = agent_result.get("response", "")
            if not response_text:
                response_text = "Seringa, naan Deenan-kitta note pannikkaren."

            # Record assistant response in database
            self.telephony_svc.record_turn(
                call_id=self.call_id,
                speaker=SpeakerType.ASSISTANT,
                text=response_text,
                language=stt_res.language,
            )

            # 3. Synthesize and stream speech to caller
            await self._play_ai_response(response_text, stt_res.language)

        except asyncio.CancelledError:
            logger.info("turn_processing_cancelled", call_id=str(self.call_id))
        except Exception as e:
            logger.error("turn_processing_error", call_id=str(self.call_id), error=str(e))
            fallback_msg = "Mannikkavum, oru chinna thozhilnutpa kolaru. Ungal message-ai note pannitten."
            await self._play_ai_response(fallback_msg, "ta")
        finally:
            self.is_processing_turn = False

    async def _play_ai_response(self, text: str, language: str = "ta") -> None:
        """Synthesizes response text and transmits audio to caller."""
        if not self.is_active or self.is_human_takeover:
            return

        self.is_ai_speaking = True
        try:
            tts_res = self.tts.synthesize(text, language=language)
            audio_bytes = tts_res.audio_bytes

            if self.send_audio_callback and audio_bytes:
                # Stream audio in chunks
                chunk_size = 1280  # 40ms of 16kHz 16-bit audio
                for i in range(0, len(audio_bytes), chunk_size):
                    if not self.is_ai_speaking or not self.is_active:
                        break
                    chunk = audio_bytes[i : i + chunk_size]
                    if asyncio.iscoroutinefunction(self.send_audio_callback):
                        await self.send_audio_callback(chunk)
                    else:
                        self.send_audio_callback(chunk)
                    await asyncio.sleep(0.035)  # Real-time pacing
        finally:
            self.is_ai_speaking = False

    async def interrupt_ai_speech(self) -> None:
        """Stops ongoing AI audio playback and cancels turn generation for barge-in."""
        self.is_ai_speaking = False
        if self._current_turn_task and not self._current_turn_task.done():
            self._current_turn_task.cancel()

    def _reset_audio_state(self) -> None:
        self._audio_buffer.clear()
        self._speech_detected = False
        self._silence_frames = 0
        self._speech_frames = 0

    async def close(self) -> dict[str, Any]:
        """Finalizes the live session and triggers post-call intelligence."""
        if not self.is_active:
            return {}

        self.is_active = False
        self.is_ai_speaking = False
        if self._current_turn_task and not self._current_turn_task.done():
            self._current_turn_task.cancel()

        # Finalize call and run post-call intelligence
        result = {}
        try:
            result = self.telephony_svc.end_call(self.call_id)
        except Exception as e:
            logger.error("close_session_post_call_failed", call_id=str(self.call_id), error=str(e))
        finally:
            if self._owns_db:
                self.db.close()

        logger.info("live_audio_session_closed", call_id=str(self.call_id))
        return result
