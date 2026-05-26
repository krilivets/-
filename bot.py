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
    Если его нет — берём встроенный ffmpeg из пакета imageio-ffmpeg.
    Это удобно для хостингов, где нельзя вручную поставить ffmpeg.
    """

    system_ffmpeg = shutil.which("ffmpeg")

    if system_ffmpeg:
        return system_ffmpeg

    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as e:
        raise FileNotFoundError(
            "Не найден ffmpeg. Установи imageio-ffmpeg через requirements.txt "
            "или запускай проект через Dockerfile."
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
#  КОНВЕРТАЦИЯ В КРУЖОЧЕК
# ============================================================

async def run_ffmpeg(input_path: Path, output_path: Path):
    """
    Делает квадратное видео 640x640.
    Telegram сам отображает его круглым, когда мы отправляем через send_video_note.
    """

    ffmpeg_path = get_ffmpeg_path()

    command = [
        ffmpeg_path,
        "-y",
        "-i",
        str(input_path),

        # Telegram-кружочки короткие, поэтому режем до 60 секунд.
        "-t",
        "60",

        # Берём первое видео и аудио, если оно есть.
        "-map",
        "0:v:0",
        "-map",
        "0:a?",

        # Делаем квадрат 640x640 без растягивания.
        "-vf",
        "scale=640:640:force_original_aspect_ratio=increase,"
        "crop=640:640,"
        "setsar=1,"
        "fps=30",

        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "26",
        "-pix_fmt",
        "yuv420p",

        "-c:a",
        "aac",
        "-b:a",
        "96k",
        "-ac",
        "1",

        "-movflags",
        "+faststart",

        str(output_path),
    ]

    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await process.communicate()

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
        "Я сделаю из него Telegram-кружочек и отправлю обратно 🔥"
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

    # На обычном Telegram Bot API есть ограничение на скачивание больших файлов.
    if file_size and file_size > 20 * 1024 * 1024:
        await message.answer(
            "⚠️ Видео больше 20 МБ.\n\n"
            "Обычный Telegram Bot API может не дать скачать такой файл.\n"
            "Попробуй отправить видео поменьше или сожми его."
        )
        return

    status_message = await message.answer("🎬 Принял видео. Делаю кружочек...")

    temp_dir = Path(tempfile.mkdtemp(prefix="tg_circle_"))

    try:
        suffix = Path(info["filename"]).suffix.lower()

        if not suffix:
            suffix = ".mp4"

        input_path = temp_dir / f"input{suffix}"
        output_path = temp_dir / "circle.mp4"

        await bot.send_chat_action(message.chat.id, ChatAction.UPLOAD_VIDEO_NOTE)

        await bot.download(
            info["file_id"],
            destination=input_path,
        )

        await run_ffmpeg(input_path, output_path)

        if not output_path.exists() or output_path.stat().st_size == 0:
            raise RuntimeError("FFmpeg не создал итоговый файл.")

        duration = info.get("duration")

        if duration:
            duration = min(int(duration), 60)
        else:
            duration = 60

        video_note = FSInputFile(output_path, filename="circle.mp4")

        await bot.send_video_note(
            chat_id=message.chat.id,
            video_note=video_note,
            duration=duration,
            length=640,
            reply_to_message_id=message.message_id,
        )

        await status_message.delete()

    except FileNotFoundError:
        await status_message.edit_text(
            "❌ Не найден ffmpeg.\n\n"
            "Проверь, что в requirements.txt есть строка:\n"
            "<code>imageio-ffmpeg==0.5.1</code>\n\n"
            "После этого перезалей проект на хостинг и сделай redeploy."
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

    print("Бот запущен...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
