"""Async UI helpers and small shared utilities."""
import asyncio
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path
from typing import Any, Callable

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (
    FSInputFile,
    InlineKeyboardMarkup,
    InputMediaAnimation,
    InputMediaPhoto,
)

from config import ANIMATED_EXTENSIONS
from core.keyboards import main_menu_kb
from core.logger import logger

MAX_MESSAGE_AGE = timedelta(hours=48)

_IGNORABLE_EDIT_ERRORS = (
    "message is not modified",
    "canceled by new edit message request",
    "message can't be edited",
    "message to edit not found",
)


def _is_ignorable_edit_error(error: TelegramBadRequest) -> bool:
    text = str(error).lower()
    return any(marker in text for marker in _IGNORABLE_EDIT_ERRORS)


async def run_db(func: Callable[..., Any], *args, **kwargs) -> Any:
    """Run a synchronous DB/service function without blocking the event loop."""
    return await asyncio.to_thread(func, *args, **kwargs)


def is_message_old(message_date: datetime | None) -> bool:
    if not message_date:
        return False
    if message_date.tzinfo is None:
        message_date = message_date.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - message_date > MAX_MESSAGE_AGE


async def safe_delete_message(bot: Bot, chat_id: int, message_id: int) -> bool:
    try:
        await bot.delete_message(chat_id, message_id)
        return True
    except TelegramBadRequest as e:
        if "message to delete not found" not in str(e):
            logger.error(f"Ошибка удаления сообщения: {e}")
        return False
    except Exception as e:  # noqa: BLE001
        logger.error(f"Ошибка удаления сообщения: {e}")
        return False


def _is_remote(image) -> bool:
    return str(image).lower().startswith(("http://", "https://"))


def _is_animated(image) -> bool:
    path = str(image).split("?", 1)[0]
    return Path(path).suffix.lower() in ANIMATED_EXTENSIONS


def _media_source(image):
    """Telegram accepts either a URL or an FSInputFile for photo/animation."""
    return str(image) if _is_remote(image) else FSInputFile(Path(image))


async def send_character_card(
    bot: Bot,
    chat_id: int,
    image_path,
    caption: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    media = _media_source(image_path)
    try:
        if _is_animated(image_path):
            await bot.send_animation(chat_id, animation=media, caption=caption, reply_markup=reply_markup)
        else:
            await bot.send_photo(chat_id, photo=media, caption=caption, reply_markup=reply_markup)
    except TelegramBadRequest as e:
        logger.error(f"card image unavailable ({e}); sending text fallback")
        await bot.send_message(chat_id, caption, reply_markup=reply_markup)


async def edit_character_card(
    bot: Bot,
    chat_id: int,
    message_id: int,
    image_path,
    caption: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    media_source = _media_source(image_path)
    if _is_animated(image_path):
        media = InputMediaAnimation(media=media_source, caption=caption)
    else:
        media = InputMediaPhoto(media=media_source, caption=caption)
    try:
        await bot.edit_message_media(
            chat_id=chat_id,
            message_id=message_id,
            media=media,
            reply_markup=reply_markup,
        )
    except TelegramBadRequest as e:
        if _is_ignorable_edit_error(e):
            return
        # Missing/broken image (or the target message isn't media): resend the
        # card from scratch; send_character_card falls back to text if needed.
        logger.error(f"card edit failed ({e}); resending")
        await safe_delete_message(bot, chat_id, message_id)
        await send_character_card(bot, chat_id, image_path, caption, reply_markup)


async def safe_edit_text(
    bot: Bot,
    chat_id: int,
    message_id: int,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    """edit_message_text that ignores harmless races/identical edits."""
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=reply_markup,
        )
    except TelegramBadRequest as e:
        if not _is_ignorable_edit_error(e):
            raise


async def show_main_menu(bot: Bot, chat_id: int, user_id: int, lang: str = "ru") -> None:
    from db.queries import get_user_data
    from core.i18n import t

    data = await run_db(get_user_data, user_id)
    points = data.points if data else 0
    shards = data.shards if data else 0
    name = (data.first_name or data.username) if data else None
    await bot.send_message(
        chat_id,
        t(
            lang,
            "🥷Имя: {name}\n💠 Очки: {points}\n🔮 Осколки: {shards}",
            name=escape(name or t(lang, "Игрок")),
            points=points,
            shards=shards,
        ),
        reply_markup=main_menu_kb(lang),
    )
