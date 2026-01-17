"""TTS endpoint для jambonz (SaluteSpeech v2 API)."""
import logging
import os
from io import BytesIO

import grpc
from fastapi import APIRouter, Response, HTTPException
from pydantic import BaseModel

from app.generated import synthesisv2_pb2, synthesisv2_pb2_grpc
from app.auth import SberAuth

logger = logging.getLogger(__name__)

router = APIRouter()

SALUTE_SPEECH_HOST = "smartspeech.sber.ru:443"

# Путь к сертификатам Минцифры РФ
CERTS_DIR = os.path.join(os.path.dirname(__file__), "..", "certs")
CA_CERT_PATH = os.path.join(CERTS_DIR, "russian-trusted-chain.pem")

sber_auth: SberAuth | None = None


def get_ssl_credentials():
    """Создаёт SSL credentials с сертификатами Минцифры РФ."""
    root_certs = None
    if os.path.exists(CA_CERT_PATH):
        with open(CA_CERT_PATH, "rb") as f:
            root_certs = f.read()
    return grpc.ssl_channel_credentials(root_certificates=root_certs)


class TTSRequest(BaseModel):
    """Запрос синтеза речи от jambonz."""
    text: str
    voice: str = "Nec_24000"
    language: str = "ru-RU"
    type: str = "text"


async def synthesize_speech(
    text: str,
    voice: str,
    language: str,
    content_type: str,
    token: str,
) -> bytes:
    """Синтезирует речь через SaluteSpeech gRPC v2 API (bidirectional streaming)."""

    # Определяем тип контента
    if content_type == "ssml":
        proto_content_type = synthesisv2_pb2.Text.ContentType.SSML
    else:
        proto_content_type = synthesisv2_pb2.Text.ContentType.TEXT

    # Подключаемся к SaluteSpeech с сертификатами Минцифры
    credentials = get_ssl_credentials()
    channel_options = [
        ("grpc.ssl_target_name_override", "smartspeech.sber.ru"),
        ("grpc.default_authority", "smartspeech.sber.ru"),
        ("grpc.dns_resolver", "native"),
    ]
    channel = grpc.aio.secure_channel(SALUTE_SPEECH_HOST, credentials, options=channel_options)
    stub = synthesisv2_pb2_grpc.SmartSpeechStub(channel)

    # Метаданные с токеном
    metadata = [("authorization", f"Bearer {token}")]

    # Генератор запросов для bidirectional streaming
    async def request_generator():
        # Сначала отправляем Options
        options = synthesisv2_pb2.Options(
            audio_encoding=synthesisv2_pb2.Options.AudioEncoding.WAV,
            language=language,
            voice=voice,
        )
        yield synthesisv2_pb2.SynthesisRequest(options=options)

        # Затем отправляем Text
        text_msg = synthesisv2_pb2.Text(
            text=text,
            content_type=proto_content_type,
        )
        yield synthesisv2_pb2.SynthesisRequest(text=text_msg)

    # Собираем аудио из стрима
    audio_buffer = BytesIO()

    response_stream = stub.Synthesize(request_generator(), metadata=metadata)

    async for response in response_stream:
        # v2 использует oneof response
        if response.HasField("audio"):
            audio_buffer.write(response.audio.audio_chunk)

    await channel.close()

    return audio_buffer.getvalue()


@router.post("/tts")
async def tts_endpoint(tts_request: TTSRequest) -> Response:
    """HTTP POST endpoint для TTS."""
    try:
        token = await sber_auth.get_token()

        audio_data = await synthesize_speech(
            text=tts_request.text,
            voice=tts_request.voice,
            language=tts_request.language,
            content_type=tts_request.type,
            token=token,
        )

        logger.info(f"TTS успешно: {len(audio_data)} bytes")

        return Response(
            content=audio_data,
            media_type="audio/wav",
        )

    except Exception as e:
        logger.error(f"TTS ошибка: {e}")
        raise HTTPException(status_code=502, detail={"error": str(e)})
