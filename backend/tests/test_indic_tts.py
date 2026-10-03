"""
Tests for AI4Bharat Indic-TTS Integration (Tamil & English only).
"""

import os
from unittest.mock import MagicMock, patch

from app.voice.tts import IndicTTSProvider, normalize_indic_language

os.environ["DATABASE_URL"] = "sqlite:///./test.db"
os.environ["ENVIRONMENT"] = "test"


def test_normalize_indic_language_tamil_and_english():
    # Tamil variations
    assert normalize_indic_language("ta") == "ta"
    assert normalize_indic_language("Tamil") == "ta"
    assert normalize_indic_language("TAMIL") == "ta"
    assert normalize_indic_language("tanglish") == "ta"
    assert normalize_indic_language("tam") == "ta"

    # English variations
    assert normalize_indic_language("en") == "en"
    assert normalize_indic_language("English") == "en"
    assert normalize_indic_language("en-IN") == "en"
    assert normalize_indic_language("indian_english") == "en"

    # Unsupported language defaults to Tamil
    assert normalize_indic_language("fr") == "ta"
    assert normalize_indic_language(None) == "ta"


def test_indic_tts_synthesize_tamil():
    provider = IndicTTSProvider(voice_gender="female")
    result = provider.synthesize("Vanakkam, naan Ungal AI assistant.", language="ta")
    assert result.audio_bytes is not None
    assert len(result.audio_bytes) > 44  # WAV header is 44 bytes
    assert result.sample_rate == 16000
    assert result.format == "wav"
    # Verify WAV RIFF header
    assert result.audio_bytes[:4] == b"RIFF"
    assert result.audio_bytes[8:12] == b"WAVE"


def test_indic_tts_synthesize_english():
    provider = IndicTTSProvider(voice_gender="male")
    result = provider.synthesize("Hello, Dr. Deenan is currently in a meeting.", language="en")
    assert result.audio_bytes is not None
    assert len(result.audio_bytes) > 44
    assert result.sample_rate == 16000
    assert result.format == "wav"
    assert result.audio_bytes[:4] == b"RIFF"


def test_indic_tts_empty_text():
    provider = IndicTTSProvider()
    result = provider.synthesize("", language="ta")
    assert result.audio_bytes == b""


def test_indic_tts_remote_server_call():
    provider = IndicTTSProvider(server_url="http://localhost:8001")
    fake_response = MagicMock()
    fake_response.status = 200
    fake_response.read.return_value = b'{"audio": "UklGRi4AAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA="}'

    with patch("urllib.request.urlopen", return_value=fake_response):
        result = provider.synthesize("Vanakkam", language="ta")
        assert result.audio_bytes.startswith(b"RIFF")
