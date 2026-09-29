"""Arena aiogram router: menu, about, leagues, queue and battle."""

import asyncio
import random
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from config import (
    ARENA_CALIBRATION_MATCHES,
    ARENA_TURN_TIMEOUT,
    ARENA_WARN_BEFORE,
    CFR_MAX_ACTIVE,
)
from core.callbacks import ArenaCB, BattleCB, MenuCB
from core.logger import logger
from core.utils import (
    run_db,
    safe_delete_message,
    safe_edit_text,
    send_character_card,
    show_main_menu,
)
from db.queries import (
    count_ranked_users,
    get_all_character_bases,
    get_arena_deck_ids,
    get_bot_stats,
    get_rating,
    get_user_character,
    get_user_data,
    get_user_rank,
)
from features.arena import cfr_player
from features.arena.adapter import card_to_meta
from features.arena.engine import GameState
from features.arena.leagues import UNRANKED, league_for_rank, league_table_text, position_text
from features.arena.pve import build_bot_deck
from features.arena.results import (
    bot_winrate_line,
    human_pve_line,
    record_pve_result,
    record_pvp_result,
)
from features.arena.seasons import season_status
from features.arena.keyboards import (
    arena_menu_kb,
    back_to_arena_kb,
    battle_kb,
    bot_menu_kb,
    queue_kb,
    switch_kb,
)
from features.arena.matchmaking import (
    is_queued,
    join_queue,
    leave_queue,
    pop_search_message,
    set_search_message,
)
from services.locks import user_lock
from features.arena.render import (
    action_captions,
    main_deck_block,
    promotion_caption,
    switch_caption,
    teams_message,
    turn_status,
    vs_start_message,
)
from features.arena.service import (
    build_record,
    is_turn_over,
    resolve_turn,
    side_of,
    switch_targets,
)
from features.arena.store import MatchRecord, MatchStore

router = Router()

_timers: dict[str, asyncio.Task] = {}
BOT_ID = 0


def _is_human(record: MatchRecord, user_id: int) -> bool:
    return not (record.vs_bot and user_id == BOT_ID)

ABOUT_TEXT = (
    "<b>❤️ Здоровье</b> — очки жизни персонажа\n"
    "<b>💪 Урон</b> — сила атаки\n\n"
    "<b>Типы персонажей:</b> 🎭 💢 🎯 ⭐\n"
    "🎭 Манипуляторы\n"
    "💢 Силовики\n"
    "🎯 Тактики\n"
    "⭐ Идеалисты\n"
    "Круг силы: 🎭>💢>🎯>⭐>🎭\n"
    "Бьёшь по слабому типу — урон ×1.3, по сильному — ×0.7.\n\n"
    "<b>Как проходит ход</b>\n"
    "⏺ На ход дают очки действий, и потратить нужно <b>все</b>.\n"
    "Одно действие — это что-то одно:\n"
    "🔥 Атака — удар по активному персонажу врага\n"
    "🛡 Защита — щит на следующий ход врага\n"
    "🔸 Бонус — копит действия на <b>твой</b> следующий ход\n"
    "🔁 Смена — поставить другого персонажа\n"
    "ℹ Команды — показать обе колоды\n\n"
    "<b>Сколько очков</b>\n"
    "Первым ходит один игрок с 1 очком, второй — с 2.\n"
    "Дальше: раунды 2–4 — 2 очка, 5–6 — 3, потом 4.\n"
    "🔸 Бонус добавляет до +4 к следующему ходу, но всего не больше 8.\n\n"
    "<b>Атака</b>\n"
    "Бьют только активного врага. Все удары хода летят разом: если враг погиб, "
    "следующий не получает урон в этот же ход.\n\n"
    "<b>Защита</b>\n"
    "🛡 Щиты встречают атаки врага в его следующий ход, гасят их 1 к 1 и сгорают.\n\n"
    "<b>Смена</b>\n"
    "🔁 1 раз за ход и стоит 1 очко. Новый персонаж выходит <b>до</b> твоих атак.\n"
    "Если активный погиб — следующий выходит бесплатно.\n\n"
    "<b>Скрытое</b>\n"
    "Ты знаешь лишь сумму щитов и бонусов врага, но не знаешь, что из чего. "
    "Всё раскрывается, когда срабатывает.\n\n"
    "<b>Игра</b>\n"
    "📁 Колода — 3 персонажа. Бой идёт, пока у одной стороны не кончатся персонажи.\n"
    f"⏳ На ход — {ARENA_TURN_TIMEOUT} секунд.\n"
    "🏆 Цель — выбить всех персонажей противника.\n\n"
    "<b>Лиги и награды:</b>\n"
    "В меню «🔱 Лиги»"
)

# ──────────────────────────────────────────────
# MENU / STATIC
# ──────────────────────────────────────────────

@router.callback_query(MenuCB.filter(F.action == "arena"))
async def open_arena(callback: CallbackQuery, bot: Bot, user_id: int) -> None:
    await show_arena_menu(callback, bot, user_id)


async def _deck_slots(user_id: int) -> list:
    slots = []
    for char_id in await run_db(get_arena_deck_ids, user_id):
        if char_id is None:
            slots.append(None)
            continue
        card = await run_db(get_user_character, user_id, char_id)
        slots.append(
            {
                "type": card.type,
                "name": card.translation,
                "hp": card.health,
                "atk": card.attack,
                "level": card.level,
            }
            if card
            else None
        )
    return slots


async def _player_rating_line(user_id: int) -> str:
    rating, _rd, _vol, matches = await run_db(get_rating, user_id)
    if matches < ARENA_CALIBRATION_MATCHES:
        return f"🎯 Калибровка {matches}/{ARENA_CALIBRATION_MATCHES}"
    total = await run_db(count_ranked_users)
    rank = await run_db(get_user_rank, user_id)
    league = league_for_rank(rank, total)
    return f"⚔️ Ваш рейтинг: {round(rating)} {league.emoji} ({position_text(rank, total)})"


@router.callback_query(ArenaCB.filter(F.action == "menu"))
async def show_arena_menu(callback: CallbackQuery, bot: Bot, user_id: int) -> None:
    slots = await _deck_slots(user_id)
    rating_line = await _player_rating_line(user_id)
    await safe_delete_message(bot, callback.message.chat.id, callback.message.message_id)
    await bot.send_message(
        callback.message.chat.id,
        f"{main_deck_block(slots)}\n\n{rating_line}",
        reply_markup=arena_menu_kb(show_pve=cfr_player.CFR_AVAILABLE),
    )
    await callback.answer()


@router.callback_query(ArenaCB.filter(F.action == "bot"))
async def show_bot_menu(callback: CallbackQuery, bot: Bot, user_id: int) -> None:
    slots = await _deck_slots(user_id)
    bot_stats = await run_db(get_bot_stats)
    bot_line = await run_db(bot_winrate_line, bot_stats)
    data = await run_db(get_user_data, user_id)
    human_line = human_pve_line(data.pve_wins, data.pve_losses) if data else ""
    await safe_delete_message(bot, callback.message.chat.id, callback.message.message_id)
    await bot.send_message(
        callback.message.chat.id,
        f"{main_deck_block(slots)}\n\n{bot_line}\n{human_line}",
        reply_markup=bot_menu_kb(),
    )
    await callback.answer()


@router.callback_query(ArenaCB.filter(F.action == "about"))
async def show_about(callback: CallbackQuery, bot: Bot) -> None:
    await safe_delete_message(bot, callback.message.chat.id, callback.message.message_id)
    await bot.send_message(callback.message.chat.id, ABOUT_TEXT, reply_markup=back_to_arena_kb())
    await callback.answer()


@router.callback_query(ArenaCB.filter(F.action == "leagues"))
async def show_leagues(callback: CallbackQuery, bot: Bot, user_id: int) -> None:
    rating, _rd, _vol, matches = await run_db(get_rating, user_id)
    status = await season_status()

    if matches < ARENA_CALIBRATION_MATCHES:
        current = f"{UNRANKED.title} (калибровка {matches}/{ARENA_CALIBRATION_MATCHES})"
        rating_line = ""
    else:
        total = await run_db(count_ranked_users)
        rank = await run_db(get_user_rank, user_id)
        league = league_for_rank(rank, total)
        current = f"{league.title} ({position_text(rank, total)})"
        rating_line = f"Рейтинг - {round(rating)}\n"

    text = (
        "🔱 <b>Лиги</b>\n"
        f"{league_table_text()}\n\n"
        "Лига считается по месту среди отранжированных игроков (10+ матчей за сезон).\n"
        "За неактивность (3+ дня без боёв) рейтинг каждый день снижается.\n\n"
        f"Ваша лига - {current}\n"
        f"{rating_line}"
        f"До конца сезона: {status['days_left']} дн."
    )
    await safe_delete_message(bot, callback.message.chat.id, callback.message.message_id)
    await bot.send_message(callback.message.chat.id, text, reply_markup=back_to_arena_kb())
    await callback.answer()


# ──────────────────────────────────────────────
# QUEUE
# ──────────────────────────────────────────────

async def _load_deck_cards(user_id: int) -> list[dict] | None:
    ids = await run_db(get_arena_deck_ids, user_id)
    if any(cid is None for cid in ids):
        return None
    cards = []
    for char_id in ids:
        card = await run_db(get_user_character, user_id, char_id)
        if card is None:
            return None
        cards.append(card_to_meta(card))
    return cards


async def _load_deck_cards_raw(user_id: int) -> list | None:
    """Return the three CharacterCards (with levels), or None if incomplete."""
    ids = await run_db(get_arena_deck_ids, user_id)
    if any(cid is None for cid in ids):
        return None
    cards = []
    for char_id in ids:
        card = await run_db(get_user_character, user_id, char_id)
        if card is None:
            return None
        cards.append(card)
    return cards


async def _display_name(user_id: int) -> str:
    data = await run_db(get_user_data, user_id)
    if not data:
        return str(user_id)
    return data.first_name or data.username or str(user_id)


async def _start_match(bot: Bot, user1: int, user2: int) -> bool:
    cards1 = await _load_deck_cards(user1)
    cards2 = await _load_deck_cards(user2)
    if cards1 is None or cards2 is None:
        for uid in (user1, user2):
            await bot.send_message(uid, "❌ Колода не готова. Выберите 3 карточки")
        return False

    name1 = await _display_name(user1)
    name2 = await _display_name(user2)
    first_mover = random.choice([user1, user2])
    match_id = f"{min(user1, user2)}:{max(user1, user2)}"
    record = build_record(match_id, user1, user2, name1, name2, cards1, cards2, first_mover)

    store = MatchStore()
    await store.save(record)

    for uid in (user1, user2):
        search_msg = await pop_search_message(uid)
        if search_msg:
            await safe_delete_message(bot, uid, search_msg)

    text = vs_start_message(record)
    for uid in (user1, user2):
        first_text = "вы" if uid == first_mover else "противник"
        await bot.send_message(uid, f"{text}\nПервый ход - {first_text}")

    await _send_turn_prompt(bot, record, store)
    return True


async def enter_pvp(bot: Bot, user_id: int, chat_id: int, source_message_id: int | None = None) -> None:
    store = MatchStore()
    async with user_lock(user_id):
        if await store.load_for_user(user_id) is not None:
            await bot.send_message(chat_id, "❌ Вы уже находитесь в битве!")
            return
        if await is_queued(user_id):
            await bot.send_message(chat_id, "❌ Вы уже в поиске противника")
            return
        if any(cid is None for cid in await run_db(get_arena_deck_ids, user_id)):
            await bot.send_message(chat_id, "❌ Ваша колода не готова. Выберите 3 карточки")
            return
        if source_message_id:
            await safe_delete_message(bot, chat_id, source_message_id)
        opponent = await join_queue(user_id)
        if opponent is None:
            msg = await bot.send_message(
                user_id,
                "⏳ Если поиск слишком долгий, попробуйте перезайти в него\nИщем соперника...",
                reply_markup=queue_kb(),
            )
            await set_search_message(user_id, msg.message_id)
            return

    await _start_match(bot, user_id, opponent)


@router.callback_query(ArenaCB.filter(F.action == "queue"))
async def enter_queue(callback: CallbackQuery, bot: Bot, user_id: int) -> None:
    await callback.answer()
    await enter_pvp(bot, user_id, callback.message.chat.id, callback.message.message_id)


@router.message(Command("fight"))
async def cmd_fight(message: Message, bot: Bot, user_id: int) -> None:
    await enter_pvp(bot, user_id, message.chat.id)


@router.callback_query(ArenaCB.filter(F.action == "leave"))
async def leave_queue_handler(callback: CallbackQuery, bot: Bot, user_id: int) -> None:
    await leave_queue(user_id)
    await safe_delete_message(bot, callback.message.chat.id, callback.message.message_id)
    await bot.send_message(callback.message.chat.id, "Вы вышли из поиска противника")
    await callback.answer()


# ──────────────────────────────────────────────
# PvE (CFR)
# ──────────────────────────────────────────────

async def enter_pve(bot: Bot, user_id: int, chat_id: int, source_message_id: int | None = None) -> None:
    store = MatchStore()
    async with user_lock(user_id):
        if await store.load_for_user(user_id) is not None:
            await bot.send_message(chat_id, "❌ Вы уже находитесь в битве!")
            return
        if not cfr_player.CFR_AVAILABLE:
            await bot.send_message(chat_id, "🤖 PvE временно недоступно")
            return
        if CFR_MAX_ACTIVE and cfr_player.active_count() >= CFR_MAX_ACTIVE:
            await bot.send_message(chat_id, "⏳ Сервер занят, попробуйте позже")
            return

        cards = await _load_deck_cards_raw(user_id)
        if cards is None:
            await bot.send_message(chat_id, "❌ Ваша колода не готова. Выберите 3 карточки")
            return

        pool = await run_db(get_all_character_bases)
        bot_meta = await run_db(build_bot_deck, cards, pool)
        human_meta = [card_to_meta(c) for c in cards]

        name = await _display_name(user_id)
        first_mover = random.choice([user_id, BOT_ID])
        match_id = f"pve:{user_id}"
        record = build_record(match_id, user_id, BOT_ID, name, "🤖 Бот", human_meta, bot_meta, first_mover)
        record.vs_bot = True
        cfr_player.create_player(match_id, seed=random.randrange(1 << 30))
        await store.save(record)

        if source_message_id:
            await safe_delete_message(bot, chat_id, source_message_id)

    first_text = "вы" if first_mover == user_id else "противник"
    await bot.send_message(user_id, f"{vs_start_message(record)}\nПервый ход - {first_text}")

    if first_mover == BOT_ID:
        await _bot_turn(bot, record, store)
    else:
        await _send_turn_prompt(bot, record, store)


@router.callback_query(ArenaCB.filter(F.action == "pve"))
async def start_pve(callback: CallbackQuery, bot: Bot, user_id: int) -> None:
    await callback.answer()
    await enter_pve(bot, user_id, callback.message.chat.id, callback.message.message_id)


@router.message(Command("fight_ai"))
async def cmd_fight_ai(message: Message, bot: Bot, user_id: int) -> None:
    await enter_pve(bot, user_id, message.chat.id)


# ──────────────────────────────────────────────
# BATTLE
# ──────────────────────────────────────────────

async def _send_turn_prompt(bot: Bot, record: MatchRecord, store: MatchStore) -> None:
    owner = record.turn_owner
    other = record.opponent_of[owner]

    if _is_human(record, other):
        await bot.send_message(other, "Ход противника")

    if _is_human(record, owner):
        await bot.send_message(owner, "Ваш ход")
        prev = record.player1_msg_id if owner == record.player1 else record.player2_msg_id
        if prev:
            await safe_delete_message(bot, owner, prev)
        msg = await bot.send_message(owner, turn_status(record, owner), reply_markup=battle_kb(record, owner))
        if owner == record.player1:
            record.player1_msg_id = msg.message_id
        else:
            record.player2_msg_id = msg.message_id

    await store.save(record)
    if _is_human(record, owner):
        _start_timer(bot, record.match_id, owner)


async def _bot_turn(bot: Bot, record: MatchRecord, store: MatchStore) -> None:
    player = cfr_player.get_player(record.match_id)
    if player is None:
        await _finish_match(bot, record, winner_is_player1=True)
        return

    planning = GameState(record.state.opponent, record.state.player, record.state.turn, True)
    allocation = await cfr_player.choose_guarded(player, planning, record.state.turn)
    record.pending_attacks = allocation.attacks
    record.pending_defends = allocation.defends
    record.pending_bonuses = allocation.bonuses
    record.pending_switch_to = allocation.switch_to if allocation.switch_to is not None else -1
    await _resolve_and_progress(bot, record, store)


def _start_timer(bot: Bot, match_id: str, owner: int) -> None:
    _cancel_timer(match_id)

    async def _job() -> None:
        store = MatchStore()
        warn = ARENA_WARN_BEFORE
        if warn > 0 and ARENA_TURN_TIMEOUT > warn:
            await asyncio.sleep(ARENA_TURN_TIMEOUT - warn)
            record = await store.load(match_id)
            if record is None or record.turn_owner != owner:
                return
            try:
                await bot.send_message(owner, f"⏳ Осталось {warn} секунд на ход!")
            except Exception as e:  # noqa: BLE001
                logger.error(f"Timeout warning failed for {owner}: {e}")
            await asyncio.sleep(warn)
        else:
            await asyncio.sleep(ARENA_TURN_TIMEOUT)

        record = await store.load(match_id)
        if record is None or record.turn_owner != owner:
            return
        await _finish_match(bot, record, winner_is_player1=(owner != record.player1), timeout=True)

    _timers[match_id] = asyncio.create_task(_job())


def _cancel_timer(match_id: str) -> None:
    task = _timers.pop(match_id, None)
    # Never cancel the task we're currently running in: _finish_match() calls
    # this from inside the timer task itself, and cancelling it would abort the
    # finish (timeouts would silently stop working).
    if task is not None and task is not asyncio.current_task():
        task.cancel()


def cancel_timers(match_ids=None) -> None:
    """Cancel turn timers for the given matches (or all when None)."""
    current = asyncio.current_task()
    if match_ids is None:
        for task in _timers.values():
            if task is not current:
                task.cancel()
        _timers.clear()
        return
    for match_id in match_ids:
        task = _timers.pop(match_id, None)
        if task is not None and task is not current:
            task.cancel()


async def _clear_message(bot: Bot, chat_id: int, message_id: int) -> None:
    """Delete a message, or at least strip its keyboard if deletion fails."""
    if await safe_delete_message(bot, chat_id, message_id):
        return
    try:
        await bot.edit_message_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=None)
    except Exception:  # noqa: BLE001
        pass


async def _send_card(bot: Bot, chat_id: int, image: str, caption: str) -> None:
    if image and Path(image).exists():
        await send_character_card(bot, chat_id, Path(image), caption)
    else:
        await bot.send_message(chat_id, caption)


async def _send_switch_media(bot: Bot, record: MatchRecord, actor_user: int, target_user: int, card: dict) -> None:
    image = card.get("image", "")
    if _is_human(record, actor_user):
        await _send_card(bot, actor_user, image, switch_caption(card, True))
    if _is_human(record, target_user):
        await _send_card(bot, target_user, image, switch_caption(card, False))


async def _resolve_and_progress(bot: Bot, record: MatchRecord, store: MatchStore) -> None:
    _cancel_timer(record.match_id)
    resolution = resolve_turn(record)

    if record.vs_bot:
        player = cfr_player.get_player(record.match_id)
        if player is not None:
            if resolution.actor_user == BOT_ID:
                await asyncio.to_thread(player.observe_shields, resolution.defender_shields)
            else:
                await asyncio.to_thread(
                    player.observe,
                    resolution.attacks,
                    resolution.bonuses,
                    resolution.switched,
                    resolution.actor_budget,
                    turn=resolution.turn,
                )

    actor_msg = record.player1_msg_id if resolution.actor_user == record.player1 else record.player2_msg_id
    if actor_msg and _is_human(record, resolution.actor_user):
        await safe_delete_message(bot, resolution.actor_user, actor_msg)

    record.state = resolution.new_state
    record.reset_pending()

    if resolution.switched and resolution.actor_user == BOT_ID:
        await _send_switch_media(bot, record, resolution.actor_user, resolution.target_user, resolution.actor_card)

    attacker_caption, defender_caption = action_captions(record, resolution)
    image = resolution.actor_card.get("image", "")
    if _is_human(record, resolution.actor_user):
        await _send_card(bot, resolution.actor_user, image, attacker_caption)
    if _is_human(record, resolution.target_user):
        await _send_card(bot, resolution.target_user, image, defender_caption)

    if resolution.promoted_card is not None:
        promoted = resolution.promoted_card
        promoted_image = promoted.get("image", "")
        if _is_human(record, resolution.target_user):
            await _send_card(bot, resolution.target_user, promoted_image, promotion_caption(promoted, True))
        if _is_human(record, resolution.actor_user):
            await _send_card(bot, resolution.actor_user, promoted_image, promotion_caption(promoted, False))

    if resolution.winner_is_player1 is not None:
        await _finish_match(bot, record, winner_is_player1=resolution.winner_is_player1)
        return

    await store.save(record)
    if record.vs_bot and record.turn_owner == BOT_ID:
        await _bot_turn(bot, record, store)
    else:
        await _send_turn_prompt(bot, record, store)


async def _update_pending(callback: CallbackQuery, callback_data: BattleCB, bot: Bot, user_id: int) -> None:
    store = MatchStore()
    record = await store.load_for_user(user_id)
    if record is None or record.token != callback_data.token:
        await callback.answer("Этот бой уже завершён", show_alert=True)
        await _clear_message(bot, callback.message.chat.id, callback.message.message_id)
        return
    if record.turn_owner != user_id:
        await callback.answer("Сейчас ход противника", show_alert=True)
        return

    action = callback_data.action
    if action == "attack":
        record.pending_attacks += 1
    elif action == "defend":
        record.pending_defends += 1
    elif action == "bonus":
        side = side_of(record, user_id)
        from features.arena.engine import MAX_BONUS

        if side.bonus + record.pending_bonuses >= MAX_BONUS:
            await callback.answer("Максимально возможный бонус", show_alert=True)
            return
        record.pending_bonuses += 1
    elif action == "switch":
        if not switch_targets(record):
            await callback.answer("Смена недоступна", show_alert=True)
            return
        try:
            await callback.message.edit_reply_markup(reply_markup=switch_kb(record, user_id))
        except TelegramBadRequest:
            pass
        await callback.answer()
        return
    elif action == "switchto":
        if callback_data.value not in switch_targets(record):
            await callback.answer("Недоступный персонаж", show_alert=True)
            return
        record.pending_switch_to = callback_data.value
        await store.save(record)
        card = record.cards_for(user_id)[callback_data.value]
        await _send_switch_media(bot, record, user_id, record.opponent_of[user_id], card)

        if is_turn_over(record):
            await _resolve_and_progress(bot, record, store)
            await callback.answer()
            return

        # Send the action menu as a NEW message below the switch media, so the
        # keyboard is not left above it.
        await _clear_message(bot, callback.message.chat.id, callback.message.message_id)
        msg = await bot.send_message(
            user_id, turn_status(record, user_id), reply_markup=battle_kb(record, user_id)
        )
        if user_id == record.player1:
            record.player1_msg_id = msg.message_id
        else:
            record.player2_msg_id = msg.message_id
        await store.save(record)
        await callback.answer()
        return
    elif action == "back":
        await safe_edit_text(
            bot, callback.message.chat.id, callback.message.message_id,
            turn_status(record, user_id), battle_kb(record, user_id),
        )
        await callback.answer()
        return
    else:
        await callback.answer()
        return

    if is_turn_over(record):
        await store.save(record)
        await _resolve_and_progress(bot, record, store)
        await callback.answer()
        return

    await store.save(record)
    await safe_edit_text(
        bot, callback.message.chat.id, callback.message.message_id,
        turn_status(record, user_id), battle_kb(record, user_id),
    )
    await callback.answer()


@router.callback_query(BattleCB.filter())
async def handle_battle(callback: CallbackQuery, callback_data: BattleCB, bot: Bot, user_id: int) -> None:
    if callback_data.action == "teams":
        record = await MatchStore().load_for_user(user_id)
        if record is None or record.token != callback_data.token:
            await callback.answer("Этот бой уже завершён", show_alert=True)
            await _clear_message(bot, callback.message.chat.id, callback.message.message_id)
            return
        await callback.message.answer(teams_message(record, user_id))
        await callback.answer()
        return
    await _update_pending(callback, callback_data, bot, user_id)


async def _finish_match(
    bot: Bot, record: MatchRecord, winner_is_player1: bool, timeout: bool = False
) -> None:
    _cancel_timer(record.match_id)
    store = MatchStore()

    if record.vs_bot:
        human = record.player1
        text = "🏆 Вы победили бота!" if winner_is_player1 else "💀 Вы проиграли боту."
        if timeout:
            text += "\nВы не успели выбрать действия"
        result = await run_db(record_pve_result, human, not winner_is_player1)
        text += f"\n🤖 Рейтинг бота: {result['bot_rating']} ({result['bot_delta']:+d})"
        await bot.send_message(human, text)
        for mid in (record.player1_msg_id, record.player2_msg_id):
            if mid:
                await _clear_message(bot, human, mid)
        await store.delete(record)
        cfr_player.drop_player(record.match_id)
        await show_main_menu(bot, human, human)
        return

    winner = record.player1 if winner_is_player1 else record.player2
    loser = record.player2 if winner_is_player1 else record.player1
    winner_name = await _display_name(winner)
    loser_name = await _display_name(loser)

    w_matches = (await run_db(get_rating, winner))[3]
    l_matches = (await run_db(get_rating, loser))[3]
    result = await run_db(record_pvp_result, winner, loser)

    w_line = "Калибровка" if w_matches < ARENA_CALIBRATION_MATCHES else f"+{result['winner_delta']} MMR 🏆"
    l_line = "Калибровка" if l_matches < ARENA_CALIBRATION_MATCHES else f"-{result['loser_delta']} MMR 🏆"

    timeout_winner = "\nПротивник не успел выбрать действия" if timeout else ""
    timeout_loser = "\nВы не успели выбрать действия" if timeout else ""

    await bot.send_message(
        winner, f"Вы победили <b>{loser_name}</b>!{timeout_winner}\n{w_line}", parse_mode="HTML"
    )
    await bot.send_message(
        loser, f"Вы проиграли <b>{winner_name}</b>!{timeout_loser}\n{l_line}", parse_mode="HTML"
    )

    for uid, mid in (
        (record.player1, record.player1_msg_id),
        (record.player2, record.player2_msg_id),
    ):
        if mid:
            await _clear_message(bot, uid, mid)

    await store.delete(record)
    await leave_queue(record.player1)
    await leave_queue(record.player2)
    await show_main_menu(bot, winner, winner)
    await show_main_menu(bot, loser, loser)
