"""TTS Streaming WebSocket endpoint для jambonz (SaluteSpeech v2 API)."""
import asyncio
import logging
import json
import os

import grpc
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.generated import synthesisv2_pb2, synthesisv2_pb2_grpc
from app.auth import SberAuth

logger = logging.getLogger(__name__)

router = APIRouter()

SALUTE_SPEECH_HOST = "smartspeech.sber.ru:443"

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


@router.websocket("/tts-stream")
async def tts_stream_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint для TTS streaming.

    Протокол jambonz custom TTS streaming:
    1. Провайдер отправляет {"type": "connect", "data": {...}} - подтверждение
    2. jambonz отправляет {"type": "stream", "text": "..."} - текст для синтеза
    3. jambonz отправляет {"type": "flush"} - сгенерировать аудио
    4. Провайдер стримит бинарные аудио chunks
    5. jambonz отправляет {"type": "stop"} - закрыть соединение
    """
    await websocket.accept()
    logger.info("TTS Stream WebSocket подключен")

    text_buffer = []
    voice = "Nec_24000"
    language = "ru-RU"

    # Парсим query params из URL
    query_params = dict(websocket.query_params)
    if "voice" in query_params:
        voice = query_params["voice"]
    if "language" in query_params:
        language = query_params["language"]

    logger.info(f"TTS Stream: voice={voice}, language={language}")

    # ВАЖНО: Отправляем connect message чтобы jambonz начал слать текст
    connect_msg = {
        "type": "connect",
        "data": {
            "sample_rate": 24000,  # Sber Nec голоса используют 24000 Hz
            "base64_encoding": False
        }
    }
    await websocket.send_text(json.dumps(connect_msg))
    logger.info(f"TTS Stream: отправлен connect message: {connect_msg}")

    try:
        while True:
            message = await websocket.receive()
            logger.info(f"TTS Stream RAW message: {message}")

            if message["type"] == "websocket.receive":
                if "bytes" in message:
                    logger.info(f"TTS Stream BINARY message: {len(message['bytes'])} bytes")
                elif "text" in message:
                    logger.info(f"TTS Stream TEXT message: {message['text']}")
                    data = json.loads(message["text"])
                    msg_type = data.get("type")
                    logger.info(f"TTS Stream parsed type: {msg_type}, data: {data}")

                    if msg_type == "stream":
                        # Буферизуем текст
                        text = data.get("text", "")
                        if text:
                            text_buffer.append(text)
                            logger.debug(f"TTS Stream: буферизован текст ({len(text)} символов)")

                    elif msg_type == "flush":
                        # Синтезируем и стримим аудио
                        if text_buffer:
                            full_text = "".join(text_buffer)
                            text_buffer.clear()
                            logger.info(f"TTS Stream flush: синтез {len(full_text)} символов")

                            await synthesize_and_stream(
                                websocket=websocket,
                                text=full_text,
                                voice=voice,
                                language=language,
                            )

                    elif msg_type == "stop":
                        logger.info("TTS Stream: получен stop")
                        break

            elif message["type"] == "websocket.disconnect":
                logger.info("TTS Stream: WebSocket отключён")
                break

    except WebSocketDisconnect:
        logger.info("TTS Stream: клиент отключился")
    except Exception as e:
        logger.error(f"TTS Stream ошибка: {e}")
    finally:
        try:
            await websocket.close()
        except:
            pass
        logger.info("TTS Stream: соединение закрыто")


async def synthesize_and_stream(
    websocket: WebSocket,
    text: str,
    voice: str,
    language: str,
) -> None:
    """Синтезирует речь и стримит аудио chunks в WebSocket."""
    channel = None
    try:
        token = await sber_auth.get_token()
        logger.info("TTS Stream: токен получен, создаём gRPC channel")

        credentials = get_ssl_credentials()
        channel_options = [
            ("grpc.ssl_target_name_override", "smartspeech.sber.ru"),
            ("grpc.default_authority", "smartspeech.sber.ru"),
            ("grpc.dns_resolver", "native"),
        ]
        channel = grpc.aio.secure_channel(SALUTE_SPEECH_HOST, credentials, options=channel_options)
        stub = synthesisv2_pb2_grpc.SmartSpeechStub(channel)
        logger.info("TTS Stream: gRPC channel создан")

        metadata = [("authorization", f"Bearer {token}")]

        async def request_generator():
            logger.debug(f"TTS Stream: отправляем Options (voice={voice})")
            # Используем PCM_S16LE для streaming (без WAV заголовков)
            options = synthesisv2_pb2.Options(
                audio_encoding=synthesisv2_pb2.Options.AudioEncoding.PCM_S16LE,
                language=language,
                voice=voice,
            )
            yield synthesisv2_pb2.SynthesisRequest(options=options)

            logger.info(f"TTS Stream: отправляем Text ({len(text)} символов)")
            # Отправляем Text
            text_msg = synthesisv2_pb2.Text(
                text=text,
                content_type=synthesisv2_pb2.Text.ContentType.TEXT,
            )
            yield synthesisv2_pb2.SynthesisRequest(text=text_msg)
            logger.info("TTS Stream: request_generator завершён")

        logger.info("TTS Stream: вызываем gRPC Synthesize")
        response_stream = stub.Synthesize(request_generator(), metadata=metadata)
        logger.info("TTS Stream: gRPC stream получен, начинаем итерацию")

        chunks_sent = 0
        total_bytes = 0

        async for response in response_stream:
            if response.HasField("audio"):
                audio_chunk = response.audio.audio_chunk
                if audio_chunk:
                    await websocket.send_bytes(audio_chunk)
                    chunks_sent += 1
                    total_bytes += len(audio_chunk)

        await channel.close()
        logger.info(f"TTS Stream: отправлено {chunks_sent} chunks, {total_bytes} bytes")

    except asyncio.CancelledError:
        logger.warning("TTS Stream: синтез отменён (клиент отключился)")
        if channel:
            await channel.close()
        # Не пробрасываем исключение - просто выходим из функции
    except grpc.aio.AioRpcError as e:
        logger.error(f"TTS Stream gRPC ошибка: {e.code()} {e.details()}")
        try:
            error_msg = json.dumps({"type": "error", "error": str(e.details())})
            await websocket.send_text(error_msg)
        except:
            pass
    except Exception as e:
        logger.error(f"TTS Stream ошибка синтеза: {e}")
        try:
            error_msg = json.dumps({"type": "error", "error": str(e)})
            await websocket.send_text(error_msg)
        except:
            pass
