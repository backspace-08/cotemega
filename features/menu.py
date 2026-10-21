from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

from core.callbacks import LangCB, MenuCB, NoopCB
from core.i18n import SUPPORTED, t
from core.keyboards import language_kb
from core.logger import logger
from core.texts import character_caption
from core.utils import run_db, safe_delete_message, send_character_card, show_main_menu
from db.queries import is_user_has_characters, set_user_language
from services.gacha import give_first_character

router = Router()


async def _offer_language(message: Message, back: str = "start") -> None:
    """Language picker: Russian welcome followed by the English one."""
    text = f"{t('ru', '@welcome')}\n\n{t('en', '@welcome')}"
    await message.answer(text, reply_markup=language_kb(None, back=back))


async def _start_flow(bot: Bot, chat_id: int, user_id: int, lang: str) -> None:
    """First-character gift (once) followed by the main menu."""
    if not await run_db(is_user_has_characters, user_id):
        result = await run_db(give_first_character, user_id)
        if result.card is not None:
            caption = character_caption(
                result.card,
                lang,
                title=t(lang, "Это ваш первый персонаж:"),
                points=result.points,
            )
            await send_character_card(bot, chat_id, result.card.image_path, caption)
    else:
        await bot.send_message(chat_id, t(lang, "Вы уже получили первого персонажа"))
    await show_main_menu(bot, chat_id, user_id, lang)


@router.callback_query(NoopCB.filter())
async def ignore_page_counter(callback: CallbackQuery) -> None:
    await callback.answer()


@router.message(CommandStart())
async def cmd_start(message: Message, bot: Bot, user_id: int, lang: str, lang_set: bool) -> None:
    try:
        if not lang_set:
            await _offer_language(message, back="start")
            return
        await _start_flow(bot, message.chat.id, user_id, lang)
    except Exception as e:  # noqa: BLE001
        logger.error(f"Ошибка при обработке команды /start: {e}")
        await message.answer(t(lang, "Произошла ошибка. Пожалуйста, попробуйте еще раз."))


@router.message(Command("language", "lang"))
async def cmd_language(message: Message, user_id: int, lang: str) -> None:
    await message.answer(
        t(lang, "Выберите язык / Choose your language:"),
        reply_markup=language_kb(lang, back="menu"),
    )


@router.callback_query(LangCB.filter())
async def choose_language(
    callback: CallbackQuery, callback_data: LangCB, bot: Bot, user_id: int, lang: str
) -> None:
    code = callback_data.code
    if code not in SUPPORTED:
        await callback.answer(t(lang, "❌ Неизвестный язык"), show_alert=True)
        return

    await run_db(set_user_language, user_id, code)
    chat_id = callback.message.chat.id

    if callback_data.back == "profile":
        from features.profile import show_profile

        await callback.answer(
            t(code, "Язык изменён на русский 🇷🇺" if code == "ru" else "Язык изменён на английский 🇺🇸")
        )
        await show_profile(callback, bot, user_id, code)
        return

    await safe_delete_message(bot, chat_id, callback.message.message_id)
    await callback.answer(
        t(code, "Язык изменён на русский 🇷🇺" if code == "ru" else "Язык изменён на английский 🇺🇸")
    )

    if callback_data.back == "start":
        await _start_flow(bot, chat_id, user_id, code)
    else:
        await show_main_menu(bot, chat_id, user_id, code)


@router.message(Command("menu"))
async def cmd_menu(message: Message, bot: Bot, user_id: int, lang: str, lang_set: bool) -> None:
    try:
        if not lang_set:
            await _offer_language(message, back="start")
            return
        await show_main_menu(bot, message.chat.id, user_id, lang)
    except Exception as e:  # noqa: BLE001
        logger.error(f"Ошибка при обработке команды /menu: {e}")
        await message.answer(t(lang, "Произошла ошибка. Пожалуйста, попробуйте еще раз."))


@router.callback_query(MenuCB.filter(F.action == "main"))
async def go_to_main_menu(callback: CallbackQuery, bot: Bot, user_id: int, lang: str) -> None:
    await safe_delete_message(bot, callback.message.chat.id, callback.message.message_id)
    await show_main_menu(bot, callback.message.chat.id, user_id, lang)
    await callback.answer()
