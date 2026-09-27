from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

from core.callbacks import MenuCB, NoopCB
from core.logger import logger
from core.texts import character_caption
from core.utils import run_db, safe_delete_message, send_character_card, show_main_menu
from db.queries import is_user_has_characters
from services.gacha import give_first_character

router = Router()


@router.callback_query(NoopCB.filter())
async def ignore_page_counter(callback: CallbackQuery) -> None:
    await callback.answer()


@router.message(CommandStart())
async def cmd_start(message: Message, bot: Bot, user_id: int) -> None:
    try:
        if not await run_db(is_user_has_characters, user_id):
            result = await run_db(give_first_character, user_id)
            if result.card is not None:
                caption = character_caption(
                    result.card, title="Это ваш первый персонаж:", points=result.points
                )
                await send_character_card(bot, message.chat.id, result.card.image_path, caption)
        else:
            await message.answer("Вы уже получили первого персонажа")
        await show_main_menu(bot, message.chat.id, user_id)
    except Exception as e:  # noqa: BLE001
        logger.error(f"Ошибка при обработке команды /start: {e}")
        await message.answer("Произошла ошибка. Пожалуйста, попробуйте еще раз.")


@router.message(Command("menu"))
async def cmd_menu(message: Message, bot: Bot, user_id: int) -> None:
    try:
        await show_main_menu(bot, message.chat.id, user_id)
    except Exception as e:  # noqa: BLE001
        logger.error(f"Ошибка при обработке команды /menu: {e}")
        await message.answer("Произошла ошибка. Пожалуйста, попробуйте еще раз.")


@router.callback_query(MenuCB.filter(F.action == "main"))
async def go_to_main_menu(callback: CallbackQuery, bot: Bot, user_id: int) -> None:
    await safe_delete_message(bot, callback.message.chat.id, callback.message.message_id)
    await show_main_menu(bot, callback.message.chat.id, user_id)
    await callback.answer()
