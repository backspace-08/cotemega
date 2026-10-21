"""Arena message rendering. Text/markup mirrors the legacy arena UI."""

from html import escape

from core.i18n import normalize, t
from core.texts import (
    attack_action,
    card_name,
    defeated,
    enters_battle,
    gendered,
    get_type_char,
    not_attacked,
    spent,
)
from features.arena.adapter import to_character, to_engine_type
from features.arena.engine import multiplier, per_hit_damage
from features.arena.service import meta_to_fighter, remaining_actions, side_of
from features.arena.store import MatchRecord


def display_name(record: MatchRecord, user_id: int) -> str:
    return record.p1_name if user_id == record.player1 else record.p2_name


def _emoji(card: dict) -> str:
    return get_type_char(card.get("type", 0))


def _name(card: dict, lang: str = "ru") -> str:
    return f"{card_name(card, lang)} Lv.{card.get('level', 1)}"


def _relation_symbol(my_type: int, enemy_type: int) -> str:
    ratio = multiplier(to_engine_type(my_type), to_engine_type(enemy_type))
    if ratio > 1:
        return ">"
    if ratio < 1:
        return "<"
    return "="


def _fighter(card: dict):
    return to_character(meta_to_fighter(card))


def _possessive(lang: str, gender: str, *, your: bool) -> str:
    if normalize(lang) == "en":
        return "Your" if your else "Enemy's"
    if your:
        return gendered(gender, "Ваш", "Ваша", plural="Ваши")
    return gendered(gender, "Вражеский", "Вражеская", plural="Вражеские")


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
    lang = record.lang_for(user_id)
    opponent_id = record.opponent_of[user_id]
    my_card, my_hp, enemy_card, enemy_hp = active_cards(record, user_id)
    return (
        f"<blockquote><b>{escape(display_name(record, user_id))}</b>\n"
        f"★ {_emoji(my_card)} {_name(my_card, lang)}\n"
        f"├‣❤️ - {my_hp}\n"
        f"├‣💪 - {my_card['atk']}\n"
        f"VS\n"
        f"<b>{escape(display_name(record, opponent_id))}</b>\n"
        f"★ {_emoji(enemy_card)} {_name(enemy_card, lang)}\n"
        f"├‣❤️ - {enemy_hp}\n"
        f"├‣💪 - {enemy_card['atk']}</blockquote>"
    )


def damage_preview(record: MatchRecord, user_id: int) -> str:
    lang = record.lang_for(user_id)
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
        f"{t(lang, 'Урон противника:')}\n{enemy_damage}\n"
        f"{t(lang, 'Ваш урон:')}\n{my_now}>>>"
    )
    return f"{part1}<i>{escape(str(my_next))}</i>"


def turn_status(record: MatchRecord, user_id: int) -> str:
    lang = record.lang_for(user_id)
    return (
        t(lang, "Очки действия: {points}", points=remaining_actions(record))
        + "\n"
        + t(lang, "🔥 Атака: {count}", count=record.pending_attacks)
        + "\n"
        + t(lang, "🛡️ Защита: {count}", count=record.pending_defends)
        + "\n"
        + t(lang, "🔸 Бонус: {count}/4", count=record.pending_bonuses)
        + "\n"
        + vs_message(record, user_id)
        + "\n"
        + damage_preview(record, user_id)
    )


def _action_caption(record: MatchRecord, resolution, lang: str, *, own: bool) -> str:
    """Caption for one side, rendered in that side's language."""
    attacker = resolution.actor_card
    defender = resolution.target_card
    own_word = _possessive(lang, attacker.get("gender", "unknown"), your=own)
    verb = attack_action(lang, attacker.get("gender", "unknown"))

    if resolution.target_died:
        health_line = "\n" + t(
            lang,
            "{name} {verb} ☠",
            name=card_name(defender, lang),
            verb=defeated(lang, defender.get("gender", "unknown")),
        )
    else:
        health_line = "\n" + t(
            lang,
            "У {name} осталось ❤️ {hp}",
            name=card_name(defender, lang),
            hp=resolution.target_hp_after,
        )

    attacker_name = f"<b>{card_name(attacker, lang)}</b>"
    defender_name = f"<b>{card_name(defender, lang)}</b>"
    if resolution.attacks <= 0:
        skip_word = not_attacked(lang, attacker.get("gender", "unknown"))
        spent_word = spent(lang, defender.get("gender", "unknown"))
        text = (
            f"{own_word} {attacker_name} {skip_word}\n"
            f"{defender_name} {spent_word} 🛡{resolution.defender_shields}"
        )
    elif resolution.hits <= 0:
        text = (
            f"{t(lang, 'Блок! 🛡')}\n"
            f"{own_word} {attacker_name} {verb}\n"
            f"{defender_name}\n"
            f"🔥{resolution.attacks} vs 🛡{resolution.defender_shields}"
        )
    else:
        text = (
            f"{own_word} {attacker_name} {verb}\n"
            f"{defender_name}\n"
            f"🔥{resolution.attacks} vs 🛡{resolution.defender_shields}\n"
            f"{t(lang, 'Нанесено {damage} урона', damage=resolution.damage)}{health_line}"
        )
    if not own:
        text += "\n" + t(
            lang,
            "Ходы противника: {spent} + {bank}🔸",
            spent=resolution.actor_budget - resolution.actor_bank,
            bank=resolution.actor_bank,
        )
    return text


def action_captions(record: MatchRecord, resolution) -> tuple[str, str]:
    """(caption shown to the attacker, caption shown to the defender)."""
    return (
        _action_caption(record, resolution, record.lang_for(resolution.actor_user), own=True),
        _action_caption(record, resolution, record.lang_for(resolution.target_user), own=False),
    )


def promotion_caption(card: dict, for_owner: bool, lang: str = "ru") -> str:
    name = card_name(card, lang)
    if normalize(lang) == "en":
        prefix = t(lang, "Вступает в бой:") if for_owner else t(lang, "У противника вступает в бой:")
        return f"{prefix}\n{name}"
    verb = enters_battle(lang, card.get("gender", "unknown"))
    prefix = f"{verb} в бой:" if for_owner else f"У противника {verb.lower()} в бой:"
    return f"{prefix}\n{name}"


def switch_caption(card: dict, for_owner: bool, lang: str = "ru") -> str:
    prefix = t(lang, "Вы выбрали:" if for_owner else "Противник выбрал:")
    return f"{prefix}\n{card_name(card, lang)}"


def main_deck_block(slots: list[dict | None], name: str = "", lang: str = "ru") -> str:
    name = name or t(lang, "Твоя колода")
    body = []
    marks = ["★", "✦", "✦"]
    for index, card in enumerate(slots):
        if card is None:
            body.append(f"{marks[index]} {t(lang, 'Пусто')}")
            continue
        body.append(f"{marks[index]} {_emoji(card)} {_name(card, lang)}")
        body.append(f"├‣❤️ - {card['hp']}")
        body.append(f"├‣💪 - {card['atk']}")
    return f"📁<b>{escape(name)}:</b>\n<blockquote>" + "\n".join(body) + "</blockquote>"


def _deck_block(record: MatchRecord, user_id: int, lang: str | None = None) -> str:
    lang = lang or record.lang_for(user_id)
    side = side_of(record, user_id)
    cards = record.cards_for(user_id)
    order = side.normalized_order()
    body = []
    for position, idx in enumerate(order, start=1):
        card = cards[idx]
        hp = side.characters[idx].hp
        mark = "★" if position == 1 else "✦"
        if hp > 0:
            body.append(f"{mark} {_emoji(card)} {_name(card, lang)}")
            body.append(f"├‣❤️ - {hp}")
            body.append(f"├‣💪 - {card['atk']}")
        else:
            body.append(f"{mark} {t(lang, 'Побежден ☠')}")
            body.append("├‣☠ - 0")
            body.append("├‣☠ - 0")
    header = f"<b>{escape(display_name(record, user_id))}</b>"
    return header + "\n<blockquote>" + "\n".join(body) + "</blockquote>"


def teams_message(record: MatchRecord, user_id: int) -> str:
    opponent_id = record.opponent_of[user_id]
    lang = record.lang_for(user_id)
    return (
        f"{_deck_block(record, user_id, lang)}\n <b>VS</b> \n\n"
        f"{_deck_block(record, opponent_id, lang)}"
    )


def vs_start_message(record: MatchRecord, lang: str | None = None) -> str:
    """Both decks rendered in one language (each player gets their own copy)."""
    lang = lang or record.lang_for(record.player1)
    return (
        f"{_deck_block(record, record.player1, lang)}\n <b>VS</b> \n\n"
        f"{_deck_block(record, record.player2, lang)}"
    )
