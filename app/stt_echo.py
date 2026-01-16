"""Тестовый STT endpoint - просто эхо для проверки WebSocket соединения."""
import asyncio
import logging
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/stt-test")
async def stt_test_endpoint(websocket: WebSocket):
    """
    Тестовый WebSocket endpoint.
    Просто принимает соединение и отвечает фейковой транскрипцией.
    """
    client = websocket.client
    headers = dict(websocket.headers)
    logger.info(f"STT-TEST: попытка подключения client={client}, headers={headers}")

    await websocket.accept()
    logger.info("STT-TEST: WebSocket подключен!")

    try:
        # Ждём start message
        start_data = await websocket.receive_text()
        start_msg = json.loads(start_data)
        logger.info(f"STT-TEST: получен start message: {start_msg}")

        # Отправляем фейковую транскрипцию через 1 секунду
        await asyncio.sleep(1)

        fake_transcription = {
            "type": "transcription",
            "is_final": True,
            "alternatives": [
                {
                    "transcript": "тестовое сообщение от эхо сервера",
                    "confidence": 0.99
                }
            ],
            "language": "ru-RU",
            "channel": 1
        }
        await websocket.send_text(json.dumps(fake_transcription))
        logger.info("STT-TEST: отправлена фейковая транскрипция")

        # Ждём сообщения (audio chunks или stop)
        while True:
            message = await websocket.receive()

            if message["type"] == "websocket.receive":
                if "text" in message:
                    data = json.loads(message["text"])
                    logger.info(f"STT-TEST: получено text message: {data}")
                    if data.get("type") == "stop":
                        logger.info("STT-TEST: получен stop")
                        break
                elif "bytes" in message:
                    logger.info(f"STT-TEST: получен audio chunk: {len(message['bytes'])} bytes")

            elif message["type"] == "websocket.disconnect":
                logger.info("STT-TEST: WebSocket отключён")
                break

    except WebSocketDisconnect:
        logger.info("STT-TEST: клиент отключился")
    except Exception as e:
        logger.error(f"STT-TEST: ошибка: {e}")
    finally:
        try:
            await websocket.close()
        except:
            pass
        logger.info("STT-TEST: соединение закрыто")
