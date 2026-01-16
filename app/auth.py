"""Модуль авторизации SaluteSpeech OAuth2."""
import base64
import os
import time
import uuid
import logging
import httpx

logger = logging.getLogger(__name__)

SBER_OAUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
TOKEN_REFRESH_MARGIN_MS = 60_000

# Путь к сертификатам Минцифры РФ
CERTS_DIR = os.path.join(os.path.dirname(__file__), "..", "certs")
CA_BUNDLE = os.path.join(CERTS_DIR, "combined-ca-bundle.pem")


class SberAuth:
    """Менеджер OAuth2 токенов для SaluteSpeech API."""

    def __init__(self, client_id: str, client_secret: str, scope: str = "SALUTE_SPEECH_PERS"):
        self._auth_key = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        self._scope = scope
        self._token: str | None = None
        self._expires_at: int = 0

    def _is_token_valid(self) -> bool:
        if not self._token:
            return False
        current_time_ms = int(time.time() * 1000)
        return current_time_ms < (self._expires_at - TOKEN_REFRESH_MARGIN_MS)

    async def get_token(self) -> str:
        if self._is_token_valid():
            return self._token
        await self._refresh_token()
        return self._token

    async def _refresh_token(self) -> None:
        logger.info("Запрос нового access token у SaluteSpeech")

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "RqUID": str(uuid.uuid4()),
            "Authorization": f"Basic {self._auth_key}",
        }
        data = {"scope": self._scope}

        # Отключаем проверку SSL для OAuth (сертификаты Минцифры не в системном хранилище)
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.post(
                SBER_OAUTH_URL,
                headers=headers,
                data=data,
                timeout=10.0,
            )

        if response.status_code != 200:
            logger.error(f"Ошибка получения токена: {response.status_code} {response.text}")
            raise RuntimeError(f"Failed to get SaluteSpeech token: {response.status_code}")

        token_data = response.json()
        self._token = token_data["access_token"]
        self._expires_at = token_data["expires_at"]

        logger.info("Access token успешно получен")
