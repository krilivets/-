# Circle Video Bot — FALLBACK FIX

Исправленная версия Telegram-бота, который принимает обычное видео и возвращает его как Telegram-кружочек.

## Что исправлено

Если Telegram выдаёт ошибку:

```txt
Bad Request: VOICE_MESSAGES_FORBIDDEN
```

бот больше не ломается. Он делает так:

1. Сначала пытается отправить настоящий `video_note`, то есть кружочек.
2. Если Telegram запрещает кружочки/voice-video messages, бот отправляет результат как обычное квадратное видео.

## Почему бывает VOICE_MESSAGES_FORBIDDEN

Это ограничение Telegram со стороны чата/аккаунта/приватности. В таком случае бот не может насильно отправить настоящий кружочек.

## Переменные окружения

Обязательно:

```env
BOT_TOKEN=твой_токен_от_BotFather
```

Рекомендуемые быстрые настройки:

```env
VIDEO_NOTE_SIZE=360
VIDEO_NOTE_FPS=20
VIDEO_NOTE_CRF=35
VIDEO_NOTE_PRESET=ultrafast
MAX_DURATION=60
ENABLE_AUDIO=0
```

Если хочешь со звуком:

```env
ENABLE_AUDIO=1
```

Со звуком будет медленнее.

## Build command

```bash
pip install -r requirements.txt
```

## Start command

```bash
python bot.py
```

## Docker

```bash
docker build -t circle-video-bot-fallback .
docker run -e BOT_TOKEN=твой_токен circle-video-bot-fallback
```
