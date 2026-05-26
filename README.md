# Circle Video Bot — fixed ffmpeg version

Telegram-бот, который принимает обычное видео и возвращает его как Telegram-кружочек.

## Главное исправление

В этой версии бот умеет работать даже если на хостинге нет системного `ffmpeg`.

Он сначала ищет обычный `ffmpeg`, а если его нет — использует встроенный бинарник из Python-пакета:

```txt
imageio-ffmpeg
```

## Переменная окружения

На хостинге добавь:

```env
BOT_TOKEN=твой_токен_от_BotFather
```

## Команда запуска

```bash
python bot.py
```

## Build / install command

Если хостинг просит команду установки:

```bash
pip install -r requirements.txt
```

## Docker

Если хостинг запускает проект через Dockerfile, `ffmpeg` тоже будет установлен автоматически.

```bash
docker build -t circle-video-bot .
docker run -e BOT_TOKEN=твой_токен_от_BotFather circle-video-bot
```

## Важно

У обычного Telegram Bot API есть ограничение на скачивание больших файлов. В коде стоит проверка на 20 МБ.
