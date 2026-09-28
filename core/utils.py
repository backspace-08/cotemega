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


def _is_animated(path: Path) -> bool:
    return path.suffix.lower() in ANIMATED_EXTENSIONS


async def send_character_card(
    bot: Bot,
    chat_id: int,
    image_path: Path,
    caption: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    image_path = Path(image_path)
    file = FSInputFile(image_path)
    if _is_animated(image_path):
        await bot.send_animation(chat_id, animation=file, caption=caption, reply_markup=reply_markup)
    else:
        await bot.send_photo(chat_id, photo=file, caption=caption, reply_markup=reply_markup)


async def edit_character_card(
    bot: Bot,
    chat_id: int,
    message_id: int,
    image_path: Path,
    caption: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    image_path = Path(image_path)
    file = FSInputFile(image_path)
    if _is_animated(image_path):
        media = InputMediaAnimation(media=file, caption=caption)
    else:
        media = InputMediaPhoto(media=file, caption=caption)
    try:
        await bot.edit_message_media(
            chat_id=chat_id,
            message_id=message_id,
            media=media,
            reply_markup=reply_markup,
        )
    except TelegramBadRequest as e:
        if not _is_ignorable_edit_error(e):
            raise


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


async def show_main_menu(bot: Bot, chat_id: int, user_id: int) -> None:
    from db.queries import get_user_data

    data = await run_db(get_user_data, user_id)
    points = data.points if data else 0
    name = (data.first_name or data.username) if data else None
    await bot.send_message(
        chat_id,
        f"🥷Имя: {escape(name or 'Игрок')}\n💠 Очки: {points}",
        reply_markup=main_menu_kb(),
    )
