import asyncio
import os
import shutil
import tempfile
from pathlib import Path

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ChatAction, ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message, FSInputFile


# ============================================================
#  НАСТРОЙКА
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "PASTE_YOUR_BOT_TOKEN_HERE")

if not BOT_TOKEN or BOT_TOKEN == "PASTE_YOUR_BOT_TOKEN_HERE":
    raise RuntimeError(
        "Ты не указал токен бота.\n"
        "Для хостинга добавь переменную окружения BOT_TOKEN с токеном от @BotFather."
    )


# ============================================================
#  ULTRA FAST НАСТРОЙКИ
# ============================================================
# Эти настройки специально сделаны для слабого хостинга.

VIDEO_NOTE_SIZE = int(os.getenv("VIDEO_NOTE_SIZE", "360"))
VIDEO_NOTE_FPS = int(os.getenv("VIDEO_NOTE_FPS", "20"))
VIDEO_NOTE_CRF = os.getenv("VIDEO_NOTE_CRF", "35")
VIDEO_NOTE_PRESET = os.getenv("VIDEO_NOTE_PRESET", "ultrafast")
MAX_DURATION = int(os.getenv("MAX_DURATION", "60"))

# 0 = без звука, максимально быстро.
# 1 = со звуком, но медленнее.
ENABLE_AUDIO = os.getenv("ENABLE_AUDIO", "0") == "1"

# Таймауты, чтобы бот не зависал навсегда.
DOWNLOAD_TIMEOUT = int(os.getenv("DOWNLOAD_TIMEOUT", "120"))
FFMPEG_TIMEOUT = int(os.getenv("FFMPEG_TIMEOUT", "180"))
SEND_TIMEOUT = int(os.getenv("SEND_TIMEOUT", "120"))

# Ограничение файла. Для обычного Telegram Bot API лучше не поднимать выше 20 МБ.
MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "20"))


router = Router()


SUPPORTED_EXTENSIONS = {
    ".mp4",
    ".mov",
    ".mkv",
    ".webm",
    ".avi",
    ".mpeg",
    ".mpg",
    ".m4v",
}


# ============================================================
#  ПОИСК FFMPEG
# ============================================================

def get_ffmpeg_path() -> str:
    """
    Сначала ищем системный ffmpeg.
    Если его нет — берём встроенный ffmpeg из imageio-ffmpeg.
    """

    system_ffmpeg = shutil.which("ffmpeg")

    if system_ffmpeg:
        return system_ffmpeg

    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as e:
        raise FileNotFoundError(
            "Не найден ffmpeg. Проверь, что imageio-ffmpeg установлен из requirements.txt."
        ) from e


# ============================================================
#  ПОЛУЧЕНИЕ ВИДЕО ИЗ СООБЩЕНИЯ
# ============================================================

def get_file_info(message: Message):
    """
    Достаёт file_id из разных типов сообщений:
    - обычное видео;
    - видеофайл как документ;
    - GIF/анимация;
    - уже готовый кружочек.
    """

    if message.video:
        return {
            "file_id": message.video.file_id,
            "file_size": message.video.file_size,
            "filename": "video.mp4",
            "duration": message.video.duration,
        }

    if message.video_note:
        return {
            "file_id": message.video_note.file_id,
            "file_size": message.video_note.file_size,
            "filename": "video_note.mp4",
            "duration": message.video_note.duration,
        }

    if message.animation:
        return {
            "file_id": message.animation.file_id,
            "file_size": message.animation.file_size,
            "filename": "animation.mp4",
            "duration": message.animation.duration,
        }

    if message.document:
        filename = message.document.file_name or "document_video.mp4"
        suffix = Path(filename).suffix.lower()
        mime_type = message.document.mime_type or ""

        is_video_by_mime = mime_type.startswith("video/")
        is_video_by_ext = suffix in SUPPORTED_EXTENSIONS

        if not is_video_by_mime and not is_video_by_ext:
            return None

        return {
            "file_id": message.document.file_id,
            "file_size": message.document.file_size,
            "filename": filename,
            "duration": None,
        }

    return None


# ============================================================
#  БЫСТРАЯ КОНВЕРТАЦИЯ
# ============================================================

async def run_ffmpeg_ultra_fast(input_path: Path, output_path: Path):
    """
    Супербыстрая конвертация:
    - 360x360;
    - 20 FPS;
    - ultrafast;
    - CRF 35;
    - по умолчанию без звука;
    - -nostdin, чтобы ffmpeg не зависал на хостинге.
    """

    ffmpeg_path = get_ffmpeg_path()

    size = VIDEO_NOTE_SIZE
    fps = VIDEO_NOTE_FPS

    vf_filter = (
        f"scale={size}:{size}:force_original_aspect_ratio=increase,"
        f"crop={size}:{size},"
        f"setsar=1,"
        f"fps={fps}"
    )

    command = [
        ffmpeg_path,
        "-y",
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",

        "-i",
        str(input_path),

        "-t",
        str(MAX_DURATION),

        "-map",
        "0:v:0",

        "-vf",
        vf_filter,

        "-c:v",
        "libx264",
        "-preset",
        VIDEO_NOTE_PRESET,
        "-tune",
        "fastdecode",
        "-crf",
        VIDEO_NOTE_CRF,
        "-pix_fmt",
        "yuv420p",
        "-threads",
        "0",
    ]

    if ENABLE_AUDIO:
        command += [
            "-map",
            "0:a?",
            "-c:a",
            "aac",
            "-b:a",
            "48k",
            "-ac",
            "1",
        ]
    else:
        command += ["-an"]

    command += [
        "-sn",
        "-dn",
        str(output_path),
    ]

    process = await asyncio.create_subprocess_exec(
        *command,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=FFMPEG_TIMEOUT,
        )
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        raise TimeoutError(
            f"FFmpeg слишком долго обрабатывал видео и был остановлен. "
            f"Таймаут: {FFMPEG_TIMEOUT} сек."
        )

    if process.returncode != 0:
        error_text = stderr.decode(errors="ignore")
        raise RuntimeError(error_text)


# ============================================================
#  /START
# ============================================================

@router.message(CommandStart())
async def start_handler(message: Message):
    await message.answer(
        "👋 Привет!\n\n"
        "Кинь мне любое видео: MP4, MOV, WebM или просто видеофайл документом.\n"
        "Я сделаю из него Telegram-кружочек 🔥\n\n"
        "⚡ Сейчас включён быстрый режим."
    )


# ============================================================
#  ОБРАБОТКА ВИДЕО
# ============================================================

@router.message(F.video | F.document | F.video_note | F.animation)
async def video_handler(message: Message, bot: Bot):
    info = get_file_info(message)

    if not info:
        await message.answer(
            "❌ Это не похоже на видео.\n\n"
            "Кинь MP4, MOV, WebM или другой видеофайл."
        )
        return

    file_size = info.get("file_size")
    max_size_bytes = MAX_FILE_SIZE_MB * 1024 * 1024

    if file_size and file_size > max_size_bytes:
        await message.answer(
            f"⚠️ Видео больше {MAX_FILE_SIZE_MB} МБ.\n\n"
            "Обычный Telegram Bot API может не дать скачать такой файл.\n"
            "Лучше отправь видео поменьше или сожми его."
        )
        return

    status_message = await message.answer("📥 Скачиваю видео...")

    temp_dir = Path(tempfile.mkdtemp(prefix="tg_circle_ultra_"))

    try:
        suffix = Path(info["filename"]).suffix.lower()
        if not suffix:
            suffix = ".mp4"

        input_path = temp_dir / f"input{suffix}"
        output_path = temp_dir / "circle.mp4"

        await bot.send_chat_action(message.chat.id, ChatAction.UPLOAD_VIDEO_NOTE)

        await asyncio.wait_for(
            bot.download(info["file_id"], destination=input_path),
            timeout=DOWNLOAD_TIMEOUT,
        )

        if not input_path.exists() or input_path.stat().st_size == 0:
            raise RuntimeError("Видео не скачалось или файл пустой.")

        await status_message.edit_text("⚙️ Конвертирую в кружочек...")

        await run_ffmpeg_ultra_fast(input_path, output_path)

        if not output_path.exists() or output_path.stat().st_size == 0:
            raise RuntimeError("FFmpeg не создал итоговый файл.")

        await status_message.edit_text("📤 Отправляю кружочек...")

        duration = info.get("duration")
        if duration:
            duration = min(int(duration), MAX_DURATION)
        else:
            duration = MAX_DURATION

        video_note = FSInputFile(output_path, filename="circle.mp4")

        await asyncio.wait_for(
            bot.send_video_note(
                chat_id=message.chat.id,
                video_note=video_note,
                duration=duration,
                length=VIDEO_NOTE_SIZE,
                reply_to_message_id=message.message_id,
            ),
            timeout=SEND_TIMEOUT,
        )

        await status_message.delete()

    except asyncio.TimeoutError:
        await status_message.edit_text(
            "❌ Бот слишком долго обрабатывал видео и остановил задачу.\n\n"
            "Попробуй отправить видео покороче или меньше по размеру."
        )

    except TimeoutError as e:
        await status_message.edit_text(
            "❌ Конвертация заняла слишком много времени.\n\n"
            f"<code>{str(e)}</code>\n\n"
            "Попробуй видео поменьше или поставь на хостинге:\n"
            "<code>VIDEO_NOTE_SIZE=320</code>\n"
            "<code>VIDEO_NOTE_FPS=18</code>"
        )

    except FileNotFoundError:
        await status_message.edit_text(
            "❌ Не найден ffmpeg.\n\n"
            "Проверь, что в requirements.txt есть:\n"
            "<code>imageio-ffmpeg==0.5.1</code>\n\n"
            "После этого сделай redeploy."
        )

    except Exception as e:
        error_text = str(e)
        if len(error_text) > 1500:
            error_text = error_text[:1500] + "..."

        await status_message.edit_text(
            "❌ Не получилось сделать кружочек.\n\n"
            f"Ошибка:\n<code>{error_text}</code>"
        )

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# ============================================================
#  ВСЕ ОСТАЛЬНЫЕ СООБЩЕНИЯ
# ============================================================

@router.message()
async def other_handler(message: Message):
    await message.answer("Кинь мне видео, и я сделаю из него кружочек 😉")


# ============================================================
#  ЗАПУСК БОТА
# ============================================================

async def main():
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dp = Dispatcher()
    dp.include_router(router)

    print("Бот запущен в ULTRA FAST FIX режиме...")
    print(f"VIDEO_NOTE_SIZE={VIDEO_NOTE_SIZE}")
    print(f"VIDEO_NOTE_FPS={VIDEO_NOTE_FPS}")
    print(f"VIDEO_NOTE_CRF={VIDEO_NOTE_CRF}")
    print(f"VIDEO_NOTE_PRESET={VIDEO_NOTE_PRESET}")
    print(f"MAX_DURATION={MAX_DURATION}")
    print(f"ENABLE_AUDIO={ENABLE_AUDIO}")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
