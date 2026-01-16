# tests/test_stt.py
import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

import sys
sys.modules["app.generated"] = MagicMock()
sys.modules["app.generated.recognitionv2_pb2"] = MagicMock()
sys.modules["app.generated.recognitionv2_pb2_grpc"] = MagicMock()


def test_stt_start_message_parsed():
    """STT должен корректно парсить start message от jambonz."""
    from app.stt import parse_start_message

    start_msg = {
        "type": "start",
        "language": "ru-RU",
        "format": "raw",
        "encoding": "LINEAR16",
        "interimResults": True,
        "sampleRateHz": 8000,
        "options": {
            "hints": ["привет", "пока"],
            "hintsBoost": 1.5
        }
    }

    options = parse_start_message(start_msg)

    assert options["language"] == "ru-RU"
    assert options["sample_rate"] == 8000
    assert options["enable_partial_results"] == True
    assert options["hints"] == ["привет", "пока"]


def test_stt_transcription_message_format():
    """STT должен форматировать ответ в формате jambonz."""
    from app.stt import format_transcription

    result = format_transcription(
        text="привет мир",
        is_final=True,
        confidence=0.95,
        language="ru-RU"
    )

    assert result["type"] == "transcription"
    assert result["is_final"] == True
    assert result["alternatives"][0]["transcript"] == "привет мир"
    assert result["alternatives"][0]["confidence"] == 0.95


def test_stt_interim_message_format():
    """STT должен форматировать промежуточный результат."""
    from app.stt import format_transcription

    result = format_transcription(
        text="приве",
        is_final=False,
        confidence=0.8,
        language="ru-RU"
    )

    assert result["type"] == "transcription"
    assert result["is_final"] == False
