"""TTS Streaming WebSocket endpoint для jambonz (SaluteSpeech v2 API).

Инкрементальный стриминг: каждое stream-сообщение от jambonz сразу
синтезируется отдельным gRPC вызовом. Аудио стримится в jambonz
по мере генерации, не дожидаясь flush.
"""
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

    Протокол (jambonz → адаптер):
    - stream: текст → сразу синтезируется отдельным gRPC вызовом
    - flush: финализация turn (ожидание завершения текущего синтеза)
    - stop: завершить сессию
    """
    await websocket.accept()
    logger.info("TTS Stream WebSocket подключен")

    voice = "Nec_24000"
    language = "ru-RU"

    # Парсим query params из URL
    query_params = dict(websocket.query_params)
    if "voice" in query_params:
        # jambonz добавляет метаданные через ';' (например Ost_8000;callSid=...,env=dev)
        # Sber API принимает только чистое имя голоса
        voice = query_params["voice"].split(";")[0]
    if "language" in query_params:
        language = query_params["language"]

    # Конвертируем формат языка: ru_RU -> ru-RU (jambonz использует _, Sber использует -)
    language = language.replace("_", "-")

    logger.info(f"TTS Stream: voice={voice}, language={language}")

    # Отправляем connect message чтобы jambonz начал слать текст
    connect_msg = {
        "type": "connect",
        "data": {
            "sample_rate": 8000,
            "base64_encoding": False,
        },
    }
    await websocket.send_text(json.dumps(connect_msg))

    # Очередь задач синтеза — выполняются последовательно
    synth_queue: asyncio.Queue[str | None] = asyncio.Queue()
    worker_task = None

    async def _synth_worker():
        """Последовательно синтезирует тексты из очереди."""
        while True:
            text = await synth_queue.get()
            if text is None:
                break
            try:
                await synthesize_and_stream(
                    websocket=websocket,
                    text=text,
                    voice=voice,
                    language=language,
                )
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"TTS Stream: ошибка синтеза: {e}")

    try:
        worker_task = asyncio.create_task(_synth_worker())

        while True:
            message = await websocket.receive()

            if message["type"] == "websocket.receive":
                if "text" in message:
                    data = json.loads(message["text"])
                    msg_type = data.get("type")

                    if msg_type == "stream":
                        text = data.get("text", "")
                        if text.strip():
                            logger.info(f"TTS Stream: stream → синтез ({len(text)} символов)")
                            await synth_queue.put(text)

                    elif msg_type == "flush":
                        logger.info("TTS Stream: flush")

                    elif msg_type == "clear":
                        logger.info("TTS Stream: clear (barge-in)")
                        # Очищаем очередь
                        while not synth_queue.empty():
                            try:
                                synth_queue.get_nowait()
                            except asyncio.QueueEmpty:
                                break

                    elif msg_type == "stop":
                        logger.info("TTS Stream: stop")
                        break

            elif message["type"] == "websocket.disconnect":
                logger.info("TTS Stream: WebSocket отключён")
                break

    except WebSocketDisconnect:
        logger.info("TTS Stream: клиент отключился")
    except Exception as e:
        logger.error(f"TTS Stream ошибка: {e}")
    finally:
        if worker_task and not worker_task.done():
            await synth_queue.put(None)
            worker_task.cancel()
            try:
                await worker_task
            except (asyncio.CancelledError, Exception):
                pass

        try:
            await websocket.close()
        except Exception:
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

        credentials = get_ssl_credentials()
        channel_options = [
            ("grpc.ssl_target_name_override", "smartspeech.sber.ru"),
            ("grpc.default_authority", "smartspeech.sber.ru"),
            ("grpc.dns_resolver", "native"),
        ]
        channel = grpc.aio.secure_channel(SALUTE_SPEECH_HOST, credentials, options=channel_options)
        stub = synthesisv2_pb2_grpc.SmartSpeechStub(channel)

        metadata = [("authorization", f"Bearer {token}")]

        async def request_generator():
            options = synthesisv2_pb2.Options(
                audio_encoding=synthesisv2_pb2.Options.AudioEncoding.PCM_S16LE,
                language=language,
                voice=voice,
            )
            yield synthesisv2_pb2.SynthesisRequest(options=options)

            text_msg = synthesisv2_pb2.Text(
                text=text,
                content_type=synthesisv2_pb2.Text.ContentType.TEXT,
            )
            yield synthesisv2_pb2.SynthesisRequest(text=text_msg)

        response_stream = stub.Synthesize(request_generator(), metadata=metadata)

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
        channel = None
        logger.info(f"TTS Stream: отправлено {chunks_sent} chunks, {total_bytes} bytes")

    except asyncio.CancelledError:
        logger.warning("TTS Stream: синтез отменён")
    except grpc.aio.AioRpcError as e:
        logger.error(f"TTS Stream gRPC ошибка: {e.code()} {e.details()}")
        try:
            error_msg = json.dumps({"type": "error", "error": str(e.details())})
            await websocket.send_text(error_msg)
        except Exception:
            pass
    except Exception as e:
        logger.error(f"TTS Stream ошибка синтеза: {e}")
        try:
            error_msg = json.dumps({"type": "error", "error": str(e)})
            await websocket.send_text(error_msg)
        except Exception:
            pass
    finally:
        if channel:
            await channel.close()
