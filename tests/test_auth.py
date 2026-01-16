# tests/test_auth.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.auth import SberAuth


@pytest.fixture
def auth():
    return SberAuth(
        auth_key="test_auth_key_base64",
        scope="SALUTE_SPEECH_PERS"
    )


@pytest.mark.asyncio
async def test_get_token_fetches_new_token_when_none(auth):
    """Первый вызов get_token должен запросить новый токен."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "access_token": "test_token_123",
        "expires_at": 9999999999999
    }

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None

    with patch("httpx.AsyncClient", return_value=mock_client):
        token = await auth.get_token()

    assert token == "test_token_123"


@pytest.mark.asyncio
async def test_get_token_returns_cached_token(auth):
    """Повторный вызов должен вернуть кэшированный токен без запроса."""
    auth._token = "cached_token"
    auth._expires_at = 9999999999999

    token = await auth.get_token()

    assert token == "cached_token"


@pytest.mark.asyncio
async def test_get_token_refreshes_expired_token(auth):
    """Если токен истёк, должен запросить новый."""
    auth._token = "old_token"
    auth._expires_at = 0

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "access_token": "new_token_456",
        "expires_at": 9999999999999
    }

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None

    with patch("httpx.AsyncClient", return_value=mock_client):
        token = await auth.get_token()

    assert token == "new_token_456"
