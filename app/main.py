"""FastAPI приложение sber-speech-adapter (v2 API)."""
import os

# Используем системный DNS resolver вместо c-ares (решает проблемы с DNS в некоторых сетях)
os.environ.setdefault("GRPC_DNS_RESOLVER", "native")

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from dotenv import load_dotenv

from app.auth import SberAuth
from app import stt, tts, tts_stream

load_dotenv()

log_level = os.getenv("LOG_LEVEL", "info").upper()
logging.basicConfig(
    level=getattr(logging, log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(fastapi_app: FastAPI):
    client_id = os.getenv("SBER_CLIENT_ID")
    client_secret = os.getenv("SBER_CLIENT_SECRET")
    scope = os.getenv("SBER_SCOPE", "SALUTE_SPEECH_PERS")

    if not client_id or not client_secret:
        raise RuntimeError("SBER_CLIENT_ID and SBER_CLIENT_SECRET environment variables are required")

    sber_auth = SberAuth(client_id=client_id, client_secret=client_secret, scope=scope)

    stt.sber_auth = sber_auth
    tts.sber_auth = sber_auth
    tts_stream.sber_auth = sber_auth

    logger.info("sber-speech-adapter (v2) запущен")

    yield

    logger.info("sber-speech-adapter остановлен")


fastapi_app = FastAPI(
    title="sber-speech-adapter",
    description="Адаптер jambonz для SaluteSpeech v2 (Сбер)",
    version="2.0.0",
    lifespan=lifespan,
)

fastapi_app.include_router(stt.router)
fastapi_app.include_router(tts.router)
fastapi_app.include_router(tts_stream.router)


@fastapi_app.get("/health")
async def health():
    return {"status": "ok", "service": "sber-speech-adapter", "api_version": "v2"}


app = fastapi_app


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "3000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
