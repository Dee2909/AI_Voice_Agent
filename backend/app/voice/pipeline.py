"""
Voice Pipeline Coordinator: Integrates VAD, STT, Agent Orchestrator, and TTS
into a seamless real-time conversation turn processor.
"""

from typing import Any

from app.agents.orchestrator import get_orchestrator
from app.voice.stt import get_stt_provider
from app.voice.tts import get_tts_provider
from app.voice.vad import get_vad_provider


class VoicePipeline:
    def __init__(self) -> None:
        self.vad = get_vad_provider()
        self.stt = get_stt_provider()
        self.tts = get_tts_provider()
        self.orchestrator = get_orchestrator()

    async def process_audio_turn(
        self,
        audio_bytes: bytes,
        conversation_id: str,
        call_id: str,
        context: dict[str, Any] | None = None,
        language: str = "en",
    ) -> dict[str, Any]:
        """
        Executes a complete audio turn:
        1. VAD check (is speech present?)
        2. STT transcription (speech -> text)
        3. Agent orchestrator (text -> AI response + tool calling)
        4. TTS synthesis (response text -> audio bytes)
        """
        # 1. VAD
        has_speech = self.vad.is_speech(audio_bytes)
        if not has_speech and len(audio_bytes) > 0:
            # If silence/noise only
            return {
                "has_speech": False,
                "transcript": "",
                "response_text": "",
                "audio_bytes": None,
            }

        # 2. STT
        stt_res = self.stt.transcribe(audio_bytes, language=language)
        transcript_text = stt_res.text

        if not transcript_text.strip():
            return {
                "has_speech": True,
                "transcript": "",
                "response_text": "",
                "audio_bytes": None,
            }

        # 3. Agent Orchestrator
        agent_res = await self.orchestrator.run(
            conversation_id=conversation_id,
            user_message=transcript_text,
            call_id=call_id,
            context=context or {},
        )
        response_text = agent_res.get("response", "")

        # 4. TTS
        tts_res = self.tts.synthesize(response_text, language=stt_res.language)

        return {
            "has_speech": True,
            "transcript": transcript_text,
            "language": stt_res.language,
            "confidence": stt_res.confidence,
            "response_text": response_text,
            "tool_calls": agent_res.get("tool_calls", []),
            "audio_bytes": tts_res.audio_bytes,
            "audio_format": tts_res.format,
        }


_default_pipeline = VoicePipeline()


def get_voice_pipeline() -> VoicePipeline:
    return _default_pipeline
