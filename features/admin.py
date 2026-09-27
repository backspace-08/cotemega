import asyncio
import random

from aiogram import Bot, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from config import (
    ADMIN_ID,
    CFR_MAX_ACTIVE,
    CFR_MAX_CONCURRENCY,
    FULL_RESET_PHRASE,
    START_SPINS,
)
from core.callbacks import AdminShardsCB
from core.keyboards import admin_shards_kb
from core.logger import logger
from core.texts import character_caption
from core.utils import run_db, safe_delete_message, send_character_card
from features.arena import cfr_player
from features.arena.metrics import stats as cfr_stats
from features.arena.results import bot_winrate_line
from db.queries import (
    get_all_user_ids,
    get_character_by_id,
    get_user_id_by_username,
    get_username,
    grant_character,
    reset_all_progress,
    update_currency,
)

router = Router()


class AdminForm(StatesGroup):
    get_id_username = State()
    shards_user_id = State()
    shards_manual_amount = State()
    shards_description = State()
    give_char_id = State()
    all_currency_amount = State()
    full_reset_confirm = State()


def is_admin(event: Message | CallbackQuery) -> bool:
    return event.from_user is not None and event.from_user.id == ADMIN_ID


async def _quit_if_requested(message: Message, state: FSMContext) -> bool:
    if (message.text or "").strip().lower() == "quit":
        await message.answer("Выход из команды")
        await state.clear()
        return True
    return False


async def _username_or_id(user_id: int) -> str:
    return await run_db(get_username, user_id) or str(user_id)


# ──────────────────────────────────────────────
# /get_id
# ──────────────────────────────────────────────

@router.message(Command("get_id"), is_admin)
async def get_id_start(message: Message, state: FSMContext) -> None:
    await state.set_state(AdminForm.get_id_username)
    await message.answer("Введите @ пользователя:")


@router.message(StateFilter(AdminForm.get_id_username), is_admin)
async def get_id_process(message: Message, state: FSMContext) -> None:
    if await _quit_if_requested(message, state):
        return
    username = (message.text or "").strip().lstrip("@")
    user_id = await run_db(get_user_id_by_username, username)
    await state.clear()
    await message.answer(f"{user_id}" if user_id else "❌ Пользователь не найден")


# ──────────────────────────────────────────────
# /give_shards
# ──────────────────────────────────────────────

@router.message(Command("give_shards"), is_admin)
async def give_shards_start(message: Message, state: FSMContext) -> None:
    await state.set_state(AdminForm.shards_user_id)
    await message.answer("Введите ID пользователя:")


@router.message(StateFilter(AdminForm.shards_user_id), is_admin)
async def give_shards_user(message: Message, state: FSMContext) -> None:
    if await _quit_if_requested(message, state):
        return
    try:
        user_id = int((message.text or "").strip())
    except ValueError:
        await message.answer("❌ ID должен быть числом")
        return
    username = await _username_or_id(user_id)
    await state.update_data(user_id=user_id)
    await state.set_state(None)
    await message.answer(
        f"Выберите количество осколков для @{username} (id {user_id}):",
        reply_markup=admin_shards_kb(user_id),
    )


@router.callback_query(AdminShardsCB.filter(), is_admin)
async def give_shards_amount(
    callback: CallbackQuery, callback_data: AdminShardsCB, state: FSMContext, bot: Bot
) -> None:
    user_id = callback_data.user_id
    username = await _username_or_id(user_id)
    await safe_delete_message(bot, callback.message.chat.id, callback.message.message_id)

    if callback_data.amount == "hand":
        await state.update_data(user_id=user_id)
        await state.set_state(AdminForm.shards_manual_amount)
        await bot.send_message(ADMIN_ID, f"Введите количество осколков для @{username} (id {user_id})")
        await callback.answer()
        return

    await state.update_data(user_id=user_id, shards=callback_data.amount)
    await state.set_state(AdminForm.shards_description)
    await bot.send_message(
        ADMIN_ID,
        f"Введите описание для @{username} (id {user_id}). Если описания нет, введите «нет».\n"
        f"Базовое описание: На ваш аккаунт поступило {callback_data.amount} 🔮",
    )
    await callback.answer()


@router.message(StateFilter(AdminForm.shards_manual_amount), is_admin)
async def give_shards_manual(message: Message, state: FSMContext) -> None:
    if await _quit_if_requested(message, state):
        return
    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer("❌ Введите целое число")
        return
    data = await state.get_data()
    user_id = data["user_id"]
    username = await _username_or_id(user_id)
    await state.update_data(shards=text)
    await state.set_state(AdminForm.shards_description)
    await message.answer(
        f"Введите описание для @{username} (id {user_id}). Если описания нет, введите «нет».\n"
        f"Базовое описание: На ваш аккаунт поступило {text} 🔮"
    )


@router.message(StateFilter(AdminForm.shards_description), is_admin)
async def give_shards_finish(message: Message, state: FSMContext, bot: Bot) -> None:
    if await _quit_if_requested(message, state):
        return
    data = await state.get_data()
    user_id = int(data["user_id"])
    shards = int(data["shards"])
    description = (message.text or "").strip()
    if description.lower() in ("нет", "none"):
        description = ""

    await run_db(update_currency, user_id, "shards", shards)
    await state.clear()

    try:
        text = f"На ваш аккаунт поступило {shards} 🔮 {description}".strip()
        await bot.send_message(user_id, text)
    except Exception as e:  # noqa: BLE001
        logger.error(f"Не удалось уведомить {user_id}: {e}")

    username = await _username_or_id(user_id)
    await message.answer(
        f"На аккаунт @{username} (ID {user_id}) поступило {shards} 🔮 с описанием {description}"
    )


# ──────────────────────────────────────────────
# /give_char
# ──────────────────────────────────────────────

@router.message(Command("give_char"), is_admin)
async def give_char_start(message: Message, state: FSMContext) -> None:
    await state.set_state(AdminForm.give_char_id)
    await message.answer("Введите ID персонажа из БД:")


@router.message(StateFilter(AdminForm.give_char_id), is_admin)
async def give_char_process(message: Message, state: FSMContext, bot: Bot) -> None:
    if await _quit_if_requested(message, state):
        return
    try:
        char_id = int((message.text or "").strip())
    except ValueError:
        await message.answer("❌ ID должен быть числом")
        return

    card = await run_db(get_character_by_id, char_id)
    if card is None:
        await message.answer("❌ Персонаж с таким ID не найден")
        return

    await state.clear()
    await send_character_card(
        bot, message.chat.id, card.image_path, character_caption(card, title="🎴 Выдан персонаж:")
    )
    await run_db(grant_character, message.from_user.id, char_id)


# ──────────────────────────────────────────────
# /admin_commands
# ──────────────────────────────────────────────

ADMIN_COMMANDS_TEXT = (
    "<b>🛠 Админ-команды</b>\n"
    "/admin_commands — этот список\n"
    "/get_id — узнать ID по @username\n"
    "/give_shards — выдать осколки одному игроку (кнопки или вручную + описание)\n"
    "/give_char — выдать себе персонажа по ID из БД\n"
    "/give_all — выдать валюту ВСЕМ (например «500» = осколки, «500 spins», «500 super_spins»)\n"
    "/full_reset — полная отчистка прогресса всех игроков (с подтверждением)\n"
    "/season_end — закрыть сезон арены: награды + soft reset + новый сезон\n"
    "/cfr_stats — нагрузка CFR, рейтинг и винрейт бота\n"
    "/cfr_bench [N] — бенч параллельных решений и памяти\n"
    "/cfr_selftest — проверка CFR против случайной политики"
)


@router.message(Command("admin_commands"), is_admin)
async def admin_commands(message: Message) -> None:
    await message.answer(ADMIN_COMMANDS_TEXT)


# ──────────────────────────────────────────────
# /give_all
# ──────────────────────────────────────────────

@router.message(Command("give_all"), is_admin)
async def give_all_start(message: Message, state: FSMContext) -> None:
    await state.set_state(AdminForm.all_currency_amount)
    await message.answer(
        "Введите сумму и валюту:\n"
        "«500» — осколки (по умолчанию)\n"
        "«500 spins» — крутки\n"
        "«500 super_spins» — супер-крутки"
    )


@router.message(StateFilter(AdminForm.all_currency_amount), is_admin)
async def give_all_amount(message: Message, state: FSMContext, bot: Bot) -> None:
    if await _quit_if_requested(message, state):
        return
    parts = (message.text or "").split()
    currency = parts[1] if len(parts) > 1 else "shards"
    if currency not in ("shards", "spins", "super_spins"):
        await message.answer("❌ Валюта: shards / spins / super_spins")
        return
    try:
        amount = int(parts[0])
    except (ValueError, IndexError):
        await message.answer("❌ Введите целое число, например «500 spins»")
        return

    await state.clear()
    icon = {"shards": "🔮", "spins": "🎴", "super_spins": "🧧"}[currency]
    user_ids = await run_db(get_all_user_ids)
    sent = 0
    for uid in user_ids:
        try:
            await run_db(update_currency, uid, currency, amount)
            await bot.send_message(uid, f"🎁 Вам начислено {amount} {icon}")
            sent += 1
            await asyncio.sleep(0.05)
        except Exception as e:  # noqa: BLE001
            logger.error(f"give_all: не удалось начислить {uid}: {e}")
    await message.answer(f"✅ Начислено {amount} {icon} всем ({sent}/{len(user_ids)})")


# ──────────────────────────────────────────────
# /full_reset
# ──────────────────────────────────────────────

@router.message(Command("full_reset"), is_admin)
async def full_reset_start(message: Message, state: FSMContext) -> None:
    await state.set_state(AdminForm.full_reset_confirm)
    await message.answer(
        "⚠️ <b>Полная отчистка</b> удалит у ВСЕХ:\n"
        "очки, рейтинг, осколки, крутки, персонажей, инвентарь, колоды и стату арены.\n"
        f"Аккаунты останутся. Круток будет {START_SPINS}.\n\n"
        f"Напишите <b>{FULL_RESET_PHRASE}</b> для подтверждения или /quit для отмены."
    )


@router.message(StateFilter(AdminForm.full_reset_confirm), is_admin)
async def full_reset_confirm(message: Message, state: FSMContext) -> None:
    if await _quit_if_requested(message, state):
        return
    if (message.text or "").strip() != FULL_RESET_PHRASE:
        await state.clear()
        await message.answer("❌ Отменено: фраза подтверждения не совпала")
        return
    await state.clear()
    count = await run_db(reset_all_progress)
    await message.answer(f"✅ Полная отчистка выполнена. Аккаунтов обнулено: {count}")


# ──────────────────────────────────────────────
# /cfr_stats
# ──────────────────────────────────────────────

@router.message(Command("cfr_stats"), is_admin)
async def show_cfr_stats(message: Message) -> None:
    limits = (
        f"\nЛимиты: решений одновременно ≤ {CFR_MAX_CONCURRENCY or '∞'}, "
        f"активных PvE ≤ {CFR_MAX_ACTIVE or '∞'}"
    )
    bot_line = await run_db(bot_winrate_line)
    await message.answer(cfr_stats.report(active_matches=cfr_player.active_count()) + bot_line + limits)


@router.message(Command("cfr_bench"), is_admin)
async def run_cfr_bench(message: Message) -> None:
    if not cfr_player.CFR_AVAILABLE:
        await message.answer("🤖 CFR недоступен (нет _cote_cfr/таблицы)")
        return
    parts = (message.text or "").split()
    n = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else cfr_stats_cores()
    await message.answer(f"⏱ Бенч: {n} параллельных решений...")
    from features.arena.bench import run_bench

    result = await asyncio.to_thread(run_bench, n)
    if result is None:
        await message.answer("🤖 CFR недоступен")
        return
    await message.answer(
        f"⏱ <b>CFR bench</b> ({result['bots']} ботов, ядер {result['cores']}, турн 7)\n"
        f"Последовательно: {result['seq_per_move_ms']:.0f}мс/ход (итого {result['seq_total_ms']:.0f}мс)\n"
        f"Параллельно: {result['conc_per_move_ms']:.0f}мс/ход (итого {result['conc_wall_ms']:.0f}мс)\n"
        f"Ускорение: ×{result['speedup']:.2f} (≈1 → GIL держит, ≈ядра → параллельно)\n"
        f"Память: бот {result['mem_per_bot_mb']:.1f}МБ, пик на решение "
        f"{result['mem_per_solve_peak_mb']:.1f}МБ\n"
        f"RSS: база {result['base_rss_mb']:.0f}МБ → пик {result['peak_rss_mb']:.0f}МБ"
    )


def cfr_stats_cores() -> int:
    from os import cpu_count

    return cpu_count() or 4


@router.message(Command("cfr_selftest"), is_admin)
async def run_cfr_selftest(message: Message) -> None:
    if not cfr_player.CFR_AVAILABLE:
        await message.answer("🤖 CFR недоступен (нет _cote_cfr/таблицы)")
        return
    await message.answer("🤖 Self-test: CFR против random, 5 игр...")
    from features.arena.selftest import run_games

    result = await asyncio.to_thread(run_games, 5, random.randrange(1 << 30))
    await message.answer(
        f"CFR vs random: {result['wins']}/{result['games']} побед, "
        f"в среднем {result['avg_turns']:.0f} ходов"
    )


# ──────────────────────────────────────────────
# /season_end — force close the current season
# ──────────────────────────────────────────────

@router.message(Command("season_end"), is_admin)
async def season_end(message: Message, bot: Bot) -> None:
    from features.arena.seasons import run_season_close

    await message.answer("🏁 Закрываю сезон: награды, soft-reset, новый сезон...")
    try:
        result = await run_season_close(bot)
        await message.answer(f"✅ Сезон закрыт. Награждено игроков: {result['count']}")
    except Exception as e:  # noqa: BLE001
        await message.answer(f"❌ Ошибка: {e}")
