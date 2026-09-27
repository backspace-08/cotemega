"""Arena message rendering. Text/markup mirrors the legacy arena UI."""

from html import escape

from core.texts import attack_action, gendered, get_type_char
from features.arena.adapter import to_character, to_engine_type
from features.arena.engine import multiplier, per_hit_damage
from features.arena.service import meta_to_fighter, remaining_actions, side_of
from features.arena.store import MatchRecord


def display_name(record: MatchRecord, user_id: int) -> str:
    return record.p1_name if user_id == record.player1 else record.p2_name


def _emoji(card: dict) -> str:
    return get_type_char(card.get("type", 0))


def _relation_symbol(my_type: int, enemy_type: int) -> str:
    ratio = multiplier(to_engine_type(my_type), to_engine_type(enemy_type))
    if ratio > 1:
        return ">"
    if ratio < 1:
        return "<"
    return "="


def _fighter(card: dict):
    return to_character(meta_to_fighter(card))


def active_cards(record: MatchRecord, user_id: int) -> tuple[dict, int, dict, int]:
    """(my_card, my_hp, enemy_card, enemy_hp) honouring a pending switch."""
    opponent_id = record.opponent_of[user_id]
    my_side = side_of(record, user_id)
    enemy_side = side_of(record, opponent_id)

    my_idx = my_side.active
    if user_id == record.turn_owner and record.pending_switch_to >= 0:
        my_idx = record.pending_switch_to

    my_card = record.cards_for(user_id)[my_idx]
    enemy_card = record.cards_for(opponent_id)[enemy_side.active]
    return my_card, my_side.characters[my_idx].hp, enemy_card, enemy_side.characters[enemy_side.active].hp


def vs_message(record: MatchRecord, user_id: int) -> str:
    opponent_id = record.opponent_of[user_id]
    my_card, my_hp, enemy_card, enemy_hp = active_cards(record, user_id)
    return (
        f"<blockquote><b>{escape(display_name(record, user_id))}</b>\n"
        f"★ {_emoji(my_card)} {my_card['name']}\n"
        f"├‣❤️ - {my_hp}\n"
        f"├‣💪 - {my_card['atk']}\n"
        f"VS\n"
        f"<b>{escape(display_name(record, opponent_id))}</b>\n"
        f"★ {_emoji(enemy_card)} {enemy_card['name']}\n"
        f"├‣❤️ - {enemy_hp}\n"
        f"├‣💪 - {enemy_card['atk']}</blockquote>"
    )


def damage_preview(record: MatchRecord, user_id: int) -> str:
    my_card, _, enemy_card, _ = active_cards(record, user_id)
    my = _fighter(my_card)
    enemy = _fighter(enemy_card)
    symbol = _relation_symbol(my_card["type"], enemy_card["type"])
    enemy_damage = per_hit_damage(enemy, my)
    my_hit = per_hit_damage(my, enemy)
    my_now = my_hit * record.pending_attacks
    my_next = my_hit * (record.pending_attacks + 1)
    part1 = escape(
        f"{_emoji(my_card)}{symbol}{_emoji(enemy_card)}\n"
        f"Урон противника:\n{enemy_damage}\n"
        f"Ваш урон:\n{my_now}>>>"
    )
    return f"{part1}<i>{escape(str(my_next))}</i>"


def turn_status(record: MatchRecord, user_id: int) -> str:
    return (
        f"Очки действия: {remaining_actions(record)}\n"
        f"🔥 Атака: {record.pending_attacks}\n"
        f"🛡️ Защита: {record.pending_defends}\n"
        f"🔸 Бонус: {record.pending_bonuses}/4\n"
        f"{vs_message(record, user_id)}\n"
        f"{damage_preview(record, user_id)}"
    )


def _action_verb(gender: str) -> str:
    return attack_action(gender)


def action_captions(record: MatchRecord, resolution) -> tuple[str, str]:
    """(caption shown to the attacker, caption shown to the defender)."""
    attacker = resolution.actor_card
    defender = resolution.target_card
    enemy_word = gendered(attacker.get("gender", "unknown"), "Вражеский", "Вражеская")
    own_word = gendered(attacker.get("gender", "unknown"), "Ваш", "Ваша")
    verb = _action_verb(attacker.get("gender", "unknown"))

    if resolution.target_died:
        health_line = f"\n{defender['name']} побежден ☠"
    else:
        health_line = f"\nУ {defender['name']} осталось ❤️ {resolution.target_hp_after}"

    if resolution.attacks <= 0:
        own = f"{own_word} <b>{attacker['name']}</b> не атаковал(а)\n<b>{defender['name']}</b> потратил 🛡{resolution.defender_shields}"
        enemy = f"{enemy_word} <b>{attacker['name']}</b> не атаковал(а)\n<b>{defender['name']}</b> потратил 🛡{resolution.defender_shields}"
    elif resolution.hits <= 0:
        own = f"Блок! 🛡\n{own_word} <b>{attacker['name']}</b> {verb}\n<b>{defender['name']}</b>\n🔥{resolution.attacks} vs 🛡{resolution.defender_shields}"
        enemy = f"Блок! 🛡\n{enemy_word} <b>{attacker['name']}</b> {verb}\n<b>{defender['name']}</b>\n🔥{resolution.attacks} vs 🛡{resolution.defender_shields}"
    else:
        own = (
            f"{own_word} <b>{attacker['name']}</b> {verb}\n"
            f"<b>{defender['name']}</b>\n"
            f"🔥{resolution.attacks} vs 🛡{resolution.defender_shields}\n"
            f"Нанесено {resolution.damage} урона{health_line}"
        )
        enemy = (
            f"{enemy_word} <b>{attacker['name']}</b> {verb}\n"
            f"<b>{defender['name']}</b>\n"
            f"🔥{resolution.attacks} vs 🛡{resolution.defender_shields}\n"
            f"Нанесено {resolution.damage} урона{health_line}"
        )

    enemy += f"\nХоды противника: {resolution.actor_budget - resolution.actor_bank} + {resolution.actor_bank}🔸"
    return own, enemy


def promotion_caption(card: dict, for_owner: bool) -> str:
    prefix = "Вступает в бой:" if for_owner else "У противника вступает в бой:"
    return f"{prefix}\n{card['name']}"


def switch_caption(card: dict, for_owner: bool) -> str:
    prefix = "Вы выбрали:" if for_owner else "Противник выбрал:"
    return f"{prefix}\n{card['name']}"


def main_deck_block(slots: list[dict | None]) -> str:
    body = []
    marks = ["★", "✦", "✦"]
    for index, card in enumerate(slots):
        if card is None:
            body.append(f"{marks[index]} Пусто")
            continue
        body.append(f"{marks[index]} {_emoji(card)} {card['name']}")
        body.append(f"├‣❤️ - {card['hp']}")
        body.append(f"├‣💪 - {card['atk']}")
    return "📁<b>Твоя колода:</b>\n<blockquote>" + "\n".join(body) + "</blockquote>"


def _deck_block(record: MatchRecord, user_id: int) -> str:
    side = side_of(record, user_id)
    cards = record.cards_for(user_id)
    order = side.normalized_order()
    body = []
    for position, idx in enumerate(order, start=1):
        card = cards[idx]
        hp = side.characters[idx].hp
        mark = "★" if position == 1 else "✦"
        if hp > 0:
            body.append(f"{mark} {_emoji(card)} {card['name']}")
            body.append(f"├‣❤️ - {hp}")
            body.append(f"├‣💪 - {card['atk']}")
        else:
            body.append(f"{mark} Побежден ☠")
            body.append("├‣☠ - 0")
            body.append("├‣☠ - 0")
    header = f"<b>{escape(display_name(record, user_id))}</b>"
    return header + "\n<blockquote>" + "\n".join(body) + "</blockquote>"


def teams_message(record: MatchRecord, user_id: int) -> str:
    opponent_id = record.opponent_of[user_id]
    return f"{_deck_block(record, user_id)}\n <b>VS</b> \n\n{_deck_block(record, opponent_id)}"


def vs_start_message(record: MatchRecord) -> str:
    """The 'players and first move' message sent once at match start."""
    return f"{_deck_block(record, record.player1)}\n <b>VS</b> \n\n{_deck_block(record, record.player2)}"
