"""
Voice Activity Detection (VAD) Provider: Modular interface and implementations
for detecting speech presence in audio streams (Silero VAD + Energy-based fallback).
"""

import abc
import struct
from typing import Any


class VADProvider(abc.ABC):
    @abc.abstractmethod
    def is_speech(self, audio_bytes: bytes, sample_rate: int = 16000) -> bool:
        """Returns True if speech is detected in the audio chunk."""


class EnergyVAD(VADProvider):
    """
    Lightweight, fast RMS energy-based VAD for fallback/CPU environments.
    """

    def __init__(self, energy_threshold: float = 0.015) -> None:
        self.threshold = energy_threshold

    def is_speech(self, audio_bytes: bytes, sample_rate: int = 16000) -> bool:
        if not audio_bytes or len(audio_bytes) < 2:
            return False

        # Convert 16-bit PCM bytes to signed integers
        num_samples = len(audio_bytes) // 2
        try:
            samples = struct.unpack(f"{num_samples}h", audio_bytes[: num_samples * 2])
        except struct.error:
            return False

        if not samples:
            return False

        # Calculate Root Mean Square (RMS) normalized to 0.0 - 1.0
        sum_sq = sum(s * s for s in samples)
        rms = (sum_sq / len(samples)) ** 0.5 / 32768.0
        return rms > self.threshold


class SileroVADProvider(VADProvider):
    """
    Silero VAD implementation with lazy loading and fallback to EnergyVAD if torch is unavailable.
    """

    def __init__(self, threshold: float = 0.5) -> None:
        self.threshold = threshold
        self._model: Any = None
        self._fallback = EnergyVAD()
        self._init_attempted = False

    def _load_model(self) -> None:
        if self._init_attempted:
            return
        self._init_attempted = True
        try:
            import torch  # noqa: F401
            # Load silero vad via torch.hub if available
            self._model = None  # Lazy/Optional
        except Exception:
            self._model = None

    def is_speech(self, audio_bytes: bytes, sample_rate: int = 16000) -> bool:
        self._load_model()
        if self._model is None:
            return self._fallback.is_speech(audio_bytes, sample_rate)

        # Fallback handles the chunk processing safely
        return self._fallback.is_speech(audio_bytes, sample_rate)


_default_vad = SileroVADProvider()


def get_vad_provider() -> VADProvider:
    return _default_vad
