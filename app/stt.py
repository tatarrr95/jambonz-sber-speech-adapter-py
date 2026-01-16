"""STT WebSocket endpoint для jambonz (SaluteSpeech v2 API)."""
import asyncio
import logging
import json
import os
from typing import Any

import grpc
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.generated import recognitionv2_pb2, recognitionv2_pb2_grpc
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


def parse_start_message(msg: dict[str, Any]) -> dict[str, Any]:
    """Парсит start message от jambonz в параметры для SaluteSpeech."""
    options = msg.get("options", {})

    return {
        "language": msg.get("language", "ru-RU"),
        "sample_rate": msg.get("sampleRateHz", 8000),
        "enable_partial_results": msg.get("interimResults", True),
        "hints": options.get("hints", []),
    }


def format_transcription(
    text: str,
    is_final: bool,
    confidence: float = 1.0,
    language: str = "ru-RU",
) -> dict[str, Any]:
    """Форматирует результат распознавания в формат jambonz."""
    return {
        "type": "transcription",
        "is_final": is_final,
        "alternatives": [
            {
                "transcript": text,
                "confidence": confidence,
            }
        ],
        "language": language,
        "channel": 1,
    }


def format_error(error: str) -> dict[str, Any]:
    """Форматирует сообщение об ошибке для jambonz."""
    return {
        "type": "error",
        "error": error,
    }


def build_recognition_options(options: dict[str, Any]) -> recognitionv2_pb2.RecognitionOptions:
    """Строит RecognitionOptions для gRPC v2."""
    hints = None
    if options.get("hints"):
        hints = recognitionv2_pb2.Hints(words=options["hints"])

    # v2 использует OptionalBool для некоторых полей
    enable_partial = recognitionv2_pb2.OptionalBool(enable=options.get("enable_partial_results", True))
    enable_multi = recognitionv2_pb2.OptionalBool(enable=True)

    # Включаем нормализацию
    normalization = recognitionv2_pb2.NormalizationOptions(
        enable=recognitionv2_pb2.OptionalBool(enable=True),
        punctuation=recognitionv2_pb2.OptionalBool(enable=True),
        capitalization=recognitionv2_pb2.OptionalBool(enable=True),
    )

    return recognitionv2_pb2.RecognitionOptions(
        audio_encoding=recognitionv2_pb2.RecognitionOptions.AudioEncoding.PCM_S16LE,
        sample_rate=options.get("sample_rate", 8000),
        channels_count=1,
        language=options.get("language", "ru-RU"),
        hypotheses_count=1,
        enable_partial_results=enable_partial,
        enable_multi_utterance=enable_multi,
        hints=hints,
        normalization_options=normalization,
    )


@router.websocket("/stt")
async def stt_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint для STT (v2 API).

    Протокол:
    1. jambonz подключается
    2. jambonz отправляет JSON {type: "start", ...}
    3. jambonz отправляет binary audio chunks
    4. Адаптер отправляет JSON {type: "transcription", ...}
    5. jambonz отправляет JSON {type: "stop"}
    6. Адаптер закрывает соединение
    """
    await websocket.accept()
    logger.info("STT WebSocket подключен")

    grpc_channel = None
    request_queue: asyncio.Queue = asyncio.Queue()

    try:
        token = await sber_auth.get_token()

        start_data = await websocket.receive_text()
        start_msg = json.loads(start_data)

        if start_msg.get("type") != "start":
            await websocket.send_text(json.dumps(format_error("Expected start message")))
            await websocket.close()
            return

        options = parse_start_message(start_msg)
        logger.info(f"STT start: language={options['language']}, sample_rate={options['sample_rate']}")

        credentials = get_ssl_credentials()
        channel_options = [
            ("grpc.ssl_target_name_override", "smartspeech.sber.ru"),
            ("grpc.default_authority", "smartspeech.sber.ru"),
            ("grpc.dns_resolver", "native"),
        ]
        grpc_channel = grpc.aio.secure_channel(SALUTE_SPEECH_HOST, credentials, options=channel_options)
        stub = recognitionv2_pb2_grpc.SmartSpeechStub(grpc_channel)
        metadata = [("authorization", f"Bearer {token}")]

        async def request_generator():
            yield recognitionv2_pb2.RecognitionRequest(
                options=build_recognition_options(options)
            )

            while True:
                chunk = await request_queue.get()
                if chunk is None:
                    break
                yield recognitionv2_pb2.RecognitionRequest(audio_chunk=chunk)

        response_stream = stub.Recognize(request_generator(), metadata=metadata)

        async def read_grpc_responses():
            try:
                async for response in response_stream:
                    # v2 использует oneof response
                    if response.HasField("transcription"):
                        transcription = response.transcription
                        if transcription.results:
                            hypothesis = transcription.results[0]
                            text = hypothesis.normalized_text or hypothesis.text
                            is_final = transcription.eou

                            msg = format_transcription(
                                text=text,
                                is_final=is_final,
                                language=options["language"],
                            )
                            await websocket.send_text(json.dumps(msg))
                            logger.debug(f"STT result: final={is_final}, text={text[:50] if text else ''}...")
            except grpc.aio.AioRpcError as e:
                logger.error(f"gRPC error: {e.code()} {e.details()}")
                await websocket.send_text(json.dumps(format_error(str(e.details()))))

        grpc_task = asyncio.create_task(read_grpc_responses())

        while True:
            message = await websocket.receive()

            if message["type"] == "websocket.receive":
                if "text" in message:
                    data = json.loads(message["text"])
                    if data.get("type") == "stop":
                        logger.info("STT stop received")
                        await request_queue.put(None)
                        break
                elif "bytes" in message:
                    await request_queue.put(message["bytes"])

            elif message["type"] == "websocket.disconnect":
                logger.info("WebSocket disconnected")
                await request_queue.put(None)
                break

        await grpc_task

    except WebSocketDisconnect:
        logger.info("STT WebSocket отключён клиентом")
        await request_queue.put(None)

    except Exception as e:
        logger.error(f"STT ошибка: {e}")
        try:
            await websocket.send_text(json.dumps(format_error(str(e))))
        except:
            pass

    finally:
        if grpc_channel:
            await grpc_channel.close()
        try:
            await websocket.close()
        except:
            pass
        logger.info("STT WebSocket закрыт")
