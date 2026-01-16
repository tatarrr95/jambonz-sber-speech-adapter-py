# tests/test_main.py
import pytest
from unittest.mock import MagicMock, patch
import sys

sys.modules["app.generated"] = MagicMock()
sys.modules["app.generated.synthesisv2_pb2"] = MagicMock()
sys.modules["app.generated.synthesisv2_pb2_grpc"] = MagicMock()
sys.modules["app.generated.recognitionv2_pb2"] = MagicMock()
sys.modules["app.generated.recognitionv2_pb2_grpc"] = MagicMock()

from fastapi.testclient import TestClient


def test_health_endpoint():
    """Health endpoint должен возвращать 200 OK."""
    with patch.dict("os.environ", {"SBER_CLIENT_ID": "test_id", "SBER_CLIENT_SECRET": "test_secret", "SBER_SCOPE": "SALUTE_SPEECH_PERS"}):
        from app.main import app
        client = TestClient(app)

        response = client.get("/health")

        assert response.status_code == 200
        assert response.json()["status"] == "ok"


def test_routes_registered():
    """Роуты /tts и /stt должны быть зарегистрированы."""
    with patch.dict("os.environ", {"SBER_CLIENT_ID": "test_id", "SBER_CLIENT_SECRET": "test_secret", "SBER_SCOPE": "SALUTE_SPEECH_PERS"}):
        from app.main import app

        routes = [route.path for route in app.routes]

        assert "/tts" in routes
        assert "/stt" in routes
        assert "/health" in routes
