from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, TelegramObject

from core.utils import is_message_old, run_db
from db.queries import ensure_user


class UserContextMiddleware(BaseMiddleware):
    """Ensure the user exists and expose user_id/username to handlers."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is not None:
            await run_db(ensure_user, user.id, user.username, user.first_name)
            data["user_id"] = user.id
            data["username"] = user.username
        return await handler(event, data)


class CallbackAgeMiddleware(BaseMiddleware):
    """Reject button presses on messages older than 48 hours."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, CallbackQuery) and event.message is not None:
            if is_message_old(event.message.date):
                await event.answer(
                    "⌛ Время действия кнопки истекло. Используйте /menu для нового запроса.",
                    show_alert=True,
                )
                return None
        return await handler(event, data)
