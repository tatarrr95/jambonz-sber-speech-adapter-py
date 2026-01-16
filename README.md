# sber-speech-adapter-py

Адаптер для интеграции jambonz с SaluteSpeech v2 (Сбер) для STT и TTS.

## Быстрый старт

1. Получите Client ID и Client Secret в [SaluteSpeech Studio](https://developers.sber.ru/studio/)
2. Соберите и запустите:

```bash
docker build -t sber-speech-adapter .
docker run -p 3000:3000 \
  -e SBER_CLIENT_ID=ваш_client_id \
  -e SBER_CLIENT_SECRET=ваш_client_secret \
  sber-speech-adapter
```

## Деплой на Dokploy

1. Создайте новое приложение → Docker
2. Укажите Git репозиторий с этим проектом
3. Добавьте переменные окружения:
   - `SBER_CLIENT_ID`
   - `SBER_CLIENT_SECRET`
4. Деплой

## Endpoints

| Endpoint | Протокол | Назначение |
|----------|----------|------------|
| `/stt` | WebSocket | Распознавание речи (v2 API) |
| `/tts` | HTTP POST | Синтез речи (v2 bidirectional streaming) |
| `/health` | HTTP GET | Health check |

## Настройка в jambonz

### STT (Custom Speech → Add)
- Name: `SaluteSpeech`
- Use for STT: ✓
- URL: `wss://ваш-домен/stt`

### TTS (Custom Speech → Add)
- Name: `SaluteSpeech`
- Use for TTS: ✓
- URL: `https://ваш-домен/tts`

## Переменные окружения

| Переменная | Обязательно | Описание |
|------------|-------------|----------|
| `SBER_CLIENT_ID` | Да | Client ID из SaluteSpeech Studio |
| `SBER_CLIENT_SECRET` | Да | Client Secret из SaluteSpeech Studio |
| `SBER_SCOPE` | Нет | Scope API (default: `SALUTE_SPEECH_PERS`) |
| `PORT` | Нет | Порт сервера (default: `3000`) |
| `LOG_LEVEL` | Нет | Уровень логов (default: `info`) |

## Разработка

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
./build_protos.sh
pytest -v
python -m app.main
```

## API версия

Использует **SaluteSpeech v2 API** с улучшенной поддержкой:
- Bidirectional streaming для TTS
- Расширенные опции нормализации для STT
- VAD (Voice Activity Detection)

## Лицензия

MIT
