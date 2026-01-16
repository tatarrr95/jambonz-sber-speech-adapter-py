# tests/test_integration.py
"""
Интеграционные тесты.
Запускать: SBER_CLIENT_ID=xxx SBER_CLIENT_SECRET=yyy pytest tests/test_integration.py -v
"""
import os
import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("SBER_CLIENT_ID") or not os.getenv("SBER_CLIENT_SECRET"),
    reason="SBER_CLIENT_ID and SBER_CLIENT_SECRET not set"
)


@pytest.mark.asyncio
async def test_auth_gets_real_token():
    """Проверяет получение реального токена от Sber."""
    from app.auth import SberAuth

    auth = SberAuth(
        client_id=os.getenv("SBER_CLIENT_ID"),
        client_secret=os.getenv("SBER_CLIENT_SECRET"),
        scope=os.getenv("SBER_SCOPE", "SALUTE_SPEECH_PERS"),
    )

    token = await auth.get_token()

    assert token is not None
    assert len(token) > 100


@pytest.mark.asyncio
async def test_tts_synthesizes_audio():
    """Проверяет синтез реального аудио через v2 API."""
    from app.auth import SberAuth
    from app.tts import synthesize_speech

    auth = SberAuth(
        client_id=os.getenv("SBER_CLIENT_ID"),
        client_secret=os.getenv("SBER_CLIENT_SECRET"),
        scope=os.getenv("SBER_SCOPE", "SALUTE_SPEECH_PERS"),
    )
    token = await auth.get_token()

    audio = await synthesize_speech(
        text="Привет, это тест",
        voice="Nec_24000",
        language="ru-RU",
        content_type="text",
        token=token,
    )

    assert len(audio) > 1000
    assert audio[:4] == b"RIFF"  # WAV header
