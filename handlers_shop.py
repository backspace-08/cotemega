from bot_core import bot
from bot_core import is_message_old, safe_delete_message
from bot_core import decline_fragments, decline_spins, exchange_menu_text, exchange_menu
from bot_core import spins_type
from config import PRICES
from bd_workers import plus_spins, plus_super_spins
from bd_workers import get_spins, get_super_spins
from bd_workers import get_shards, new_shards_db
from telebot import types

@bot.callback_query_handler(func=lambda call: call.data=='donate')
def show_donate_menu(call):
    if is_message_old(call):
        return
    safe_delete_message(bot, call.message.chat.id, call.message.message_id)
    user_id = str(call.from_user.id)
    chat_id = call.message.chat.id
    markup = types.InlineKeyboardMarkup(row_width=2)
    buttons = [
        types.InlineKeyboardButton("35🔮", callback_data="buy_lava:50"),
        types.InlineKeyboardButton("80🔮", callback_data="buy_lava:100"),
        types.InlineKeyboardButton("300🔮", callback_data="buy_lava:300"),
        types.InlineKeyboardButton("600🔮", callback_data="buy_lava:500"),
        types.InlineKeyboardButton("1300🔮", callback_data="buy_lava:1000"),
    ]
    markup.add(*buttons)
    big_btn2 = types.InlineKeyboardButton("↩️ В меню", callback_data="main_menu")
    markup.add(big_btn2)
    bot.send_message(
        user_id,
        text=PRICES+f"""<b><a href="https://telegra.ph/Polzovatelskoe-soglashenie-07-09-20">📝Пользовательское соглашение</a></b>""",
        parse_mode="HTML",
        reply_markup=markup,disable_web_page_preview=True
    )
@bot.callback_query_handler(func=lambda call: call.data=='exchange')
def show_exchange_menu(call):
    if is_message_old(call):
        return
    safe_delete_message(bot, call.message.chat.id, call.message.message_id)
    chat_id = call.message.chat.id
    user_id = str(call.from_user.id)
    username = call.from_user.username
    markup=exchange_menu()
    spins_data = get_spins(user_id)
    spins = spins_type(spins_data)
    shards = get_shards(user_id)
    super_spins = get_super_spins(user_id)
    bot.send_message(
        chat_id,
        exchange_menu_text(spins,shards,super_spins),
        reply_markup=markup)
@bot.callback_query_handler(func=lambda call: call.data.startswith('ex_all:'))
def handle_exchange_all(call):
    try:
        if is_message_old(call):
            return
        user_id = call.from_user.id
        start_shards = get_shards(user_id) or 0
        markup = exchange_menu()
        _,action = call.data.split(':')
        if action == 'super_spins':
            if not start_shards < 80:
                new_super_spins = int(start_shards) // 80
                new_shards = int(start_shards) % 80
                plus_super_spins(user_id, super_spins_plus=new_super_spins)
                new_shards_db(user_id, new_shards)
                spins_data = get_spins(user_id)
                spins = spins_type(spins_data)
                super_spins = get_super_spins(user_id)
                bot.answer_callback_query(call.id, text=f'Теперь у вас\n🧧{super_spins} супер {decline_spins(new_super_spins)} и 🔮{new_shards} {decline_fragments(new_shards)}')
                bot.edit_message_text(chat_id = call.message.chat.id, message_id = call.message.message_id, text = exchange_menu_text(spins, new_shards, super_spins), reply_markup = markup)
            else:
                bot.answer_callback_query(call.id, text='У вас недостаточно осколков')
        elif action == 'spins':
            if not start_shards < 10:
                new_spins = int(start_shards) // 10
                new_shards = int(start_shards) % 10
                plus_spins(user_id, new_spins)
                new_shards_db(user_id, new_shards)
                super_spins = get_super_spins(user_id)
                spins_data = get_spins(user_id)
                spins = spins_type(spins_data)
                bot.answer_callback_query(call.id, text=f'Теперь у вас\n🎴{spins} {decline_spins(spins)} и 🔮{new_shards} {decline_fragments(new_shards)}')
                bot.edit_message_text(chat_id = call.message.chat.id, message_id = call.message.message_id, text = exchange_menu_text(spins, new_shards, super_spins), reply_markup = markup)
            else:
                bot.answer_callback_query(call.id, text = 'У вас недостаточно осколков')
    except Exception as e:
        bot.answer_callback_query(call.id,text = f'Ошибка в модуле полного обмена: {e}')
@bot.callback_query_handler(func=lambda call: call.data.startswith('ex_num:'))
def handle_exchange_num(call):
    try:
        if is_message_old(call):
            return
        user_id = call.from_user.id
        start_shards = get_shards(user_id) or 0
        markup = exchange_menu()
        _,action,num = call.data.split(':')
        number=int(num)
        if action =='spins':
            const=10
            if not start_shards < const*number:
                new_spins = number
                new_shards = int(start_shards) - const*number
                plus_spins(user_id, new_spins)
                new_shards_db(user_id, new_shards)
                super_spins = get_super_spins(user_id)
                spins_data = get_spins(user_id)
                spins = spins_type(spins_data)
                bot.answer_callback_query(call.id, text = f'Теперь у вас\n🎴{spins} {decline_spins(spins)} и 🔮{new_shards} {decline_fragments(new_shards)}')
                bot.edit_message_text(chat_id = call.message.chat.id, message_id = call.message.message_id, text = exchange_menu_text(spins, new_shards, super_spins), reply_markup = markup)
            else:
                bot.answer_callback_query(call.id, text = 'У вас недостаточно осколков')
        elif action =='super_spins':
            const=80
            if not start_shards < const*number:
                new_super_spins = number
                new_shards = int(start_shards) - const*number
                plus_super_spins(user_id, new_super_spins)
                new_shards_db(user_id, new_shards)
                super_spins = get_super_spins(user_id)
                spins_data = get_spins(user_id)
                spins = spins_type(spins_data)
                bot.answer_callback_query(call.id, text = f'Теперь у вас\n🧧{super_spins} супер {decline_spins(spins)} и 🔮{new_shards} {decline_fragments(new_shards)}')
                bot.edit_message_text(chat_id = call.message.chat.id, message_id = call.message.message_id, text = exchange_menu_text(spins, new_shards, super_spins), reply_markup = markup)
            else:
                bot.answer_callback_query(call.id, text = 'У вас недостаточно осколков')
    except Exception as e:
        bot.send_message(user_id,text = f'Ошибка в модуле частичного обмена: {e}')
        bot.answer_callback_query(call.id)