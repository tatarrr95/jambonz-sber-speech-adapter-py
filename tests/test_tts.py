# tests/test_tts.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

import sys
sys.modules["app.generated"] = MagicMock()
sys.modules["app.generated.synthesisv2_pb2"] = MagicMock()
sys.modules["app.generated.synthesisv2_pb2_grpc"] = MagicMock()

import app.tts as tts_module
from app.tts import router

app = FastAPI()
app.include_router(router)
client = TestClient(app)


@pytest.fixture(autouse=True)
def mock_sber_auth():
    """Мокаем sber_auth для всех тестов."""
    mock_auth = AsyncMock()
    mock_auth.get_token.return_value = "test_token"
    tts_module.sber_auth = mock_auth
    yield mock_auth
    tts_module.sber_auth = None


def test_tts_endpoint_returns_audio():
    """TTS endpoint должен возвращать аудио."""
    with patch("app.tts.synthesize_speech", new_callable=AsyncMock) as mock_synth:
        mock_synth.return_value = b"fake_audio_data"

        response = client.post(
            "/tts",
            json={
                "text": "Привет мир",
                "voice": "Nec_24000",
                "language": "ru-RU",
                "type": "text"
            },
            headers={"Authorization": "Bearer test_key"}
        )

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert response.content == b"fake_audio_data"


def test_tts_endpoint_handles_ssml():
    """TTS должен корректно обрабатывать SSML."""
    with patch("app.tts.synthesize_speech", new_callable=AsyncMock) as mock_synth:
        mock_synth.return_value = b"ssml_audio"

        response = client.post(
            "/tts",
            json={
                "text": "<speak>Привет</speak>",
                "voice": "Nec_24000",
                "language": "ru-RU",
                "type": "ssml"
            },
            headers={"Authorization": "Bearer test_key"}
        )

    assert response.status_code == 200


def test_tts_endpoint_returns_502_on_error():
    """TTS должен вернуть 502 при ошибке SaluteSpeech."""
    with patch("app.tts.synthesize_speech", new_callable=AsyncMock) as mock_synth:
        mock_synth.side_effect = Exception("SaluteSpeech unavailable")

        response = client.post(
            "/tts",
            json={
                "text": "Тест",
                "voice": "Nec_24000",
                "language": "ru-RU",
                "type": "text"
            },
            headers={"Authorization": "Bearer test_key"}
        )

    assert response.status_code == 502
