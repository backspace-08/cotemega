from bot_core import bot, resolve_user
from bot_core import is_message_old, safe_delete_message
from bot_core import decline_fragments, decline_spins
from bd_workers import update_currency, get_currency, get_user_data
from telebot import types


def exchange_menu_text(spins,shards,super_spins):
    exchange_menu_text=f"🎴Количество круток: {spins}\n🔮Количество осколков: {shards}\n🧧Количество супер круток: {super_spins}\n🔄Обменный курс: \n🎴1=🔮10\n🧧1=🔮80\nСупер крутки - крутки, в которых гарантирован минимум эпический персонаж. Шанс на легендарного персонажа выше в 10 раз"
    return exchange_menu_text


def exchange_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    buttons = [
        types.InlineKeyboardButton("10🔮 на 1🎴", callback_data="ex_num:spins:1"),
        types.InlineKeyboardButton("80🔮 на 1🧧", callback_data="ex_num:super_spins:1"),
        types.InlineKeyboardButton("50🔮 на 5🎴", callback_data="ex_num:spins:5"),
        types.InlineKeyboardButton("400🔮 на 5🧧", callback_data="ex_num:super_spins:5"),
        types.InlineKeyboardButton("100🔮 на 10🎴 ", callback_data="ex_num:spins:10"),
        types.InlineKeyboardButton("800🔮 на 10🧧 ", callback_data="ex_num:super_spins:10"),
        types.InlineKeyboardButton("все🔮 на 🎴", callback_data="ex_all:spins"),
        types.InlineKeyboardButton("все🔮 на 🧧", callback_data="ex_all:super_spins")
    ]
    markup.add(*buttons)
    big_btn2 = types.InlineKeyboardButton("В меню", callback_data="main_menu")
    markup.add(big_btn2)
    return markup

@bot.callback_query_handler(func=lambda call: call.data == 'exchange')
def show_exchange_menu(call):
    if is_message_old(call):
        return
    user_id, chat_id, username = resolve_user(call)
    safe_delete_message(bot, chat_id, call.message.message_id)
    data = get_user_data(user_id) or {}
    bot.send_message(
        chat_id,
        exchange_menu_text(data.get('spins', 0), data.get('shards', 0), data.get('super_spins', 0)),
        reply_markup=exchange_menu())


@bot.callback_query_handler(func=lambda call: call.data.startswith('ex_all:'))
def handle_exchange_all(call):
    try:
        if is_message_old(call):
            return
        user_id, chat_id, username = resolve_user(call)
        data = get_user_data(user_id) or {}
        start_shards = data.get('shards', 0)
        markup = exchange_menu()
        _, action = call.data.split(':')
        if action == 'super_spins':
            if start_shards >= 80:
                new_super_spins = start_shards // 80
                new_shards = start_shards % 80
                update_currency(user_id, 'super_spins', new_super_spins)
                update_currency(user_id, 'shards', new_shards - data['shards'])
                bot.answer_callback_query(call.id, text=f'Теперь у вас\n🧧{data["super_spins"] + new_super_spins} супер {decline_spins(new_super_spins)} и 🔮{new_shards} {decline_fragments(new_shards)}')
                bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=exchange_menu_text(data['spins'], new_shards, data['super_spins'] + new_super_spins), reply_markup=markup)
            else:
                bot.answer_callback_query(call.id, text='У вас недостаточно осколков')
        elif action == 'spins':
            if not start_shards < 10:
                new_spins = int(start_shards) // 10
                new_shards = int(start_shards) % 10
                update_currency(user_id, 'spins', new_spins)
                update_currency(user_id, 'shards', new_shards - data['shards'])
                bot.answer_callback_query(call.id, text=f'Теперь у вас\n🎴{data["spins"] + new_spins} {decline_spins(new_spins)} и 🔮{new_shards} {decline_fragments(new_shards)}')
                bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=exchange_menu_text(data['spins'] + new_spins, new_shards, data['super_spins']), reply_markup=markup)
            else:
                bot.answer_callback_query(call.id, text='У вас недостаточно осколков')
    except Exception as e:
        bot.answer_callback_query(call.id, text=f'Ошибка в модуле полного обмена: {e}')


@bot.callback_query_handler(func=lambda call: call.data.startswith('ex_num:'))
def handle_exchange_num(call):
    try:
        if is_message_old(call):
            return
        user_id, chat_id, username = resolve_user(call)
        data = get_user_data(user_id) or {}
        start_shards = data.get('shards', 0)
        markup = exchange_menu()
        _, action, num = call.data.split(':')
        number = int(num)
        if action == 'spins':
            const = 10
            if start_shards >= const * number:
                new_shards = start_shards - const * number
                update_currency(user_id, 'spins', number)
                update_currency(user_id, 'shards', new_shards - data['shards'])
                bot.answer_callback_query(call.id, text=f'Теперь у вас\n🎴{data["spins"] + number} {decline_spins(number)} и 🔮{new_shards} {decline_fragments(new_shards)}')
                bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=exchange_menu_text(data['spins'] + number, new_shards, data['super_spins']), reply_markup=markup)
            else:
                bot.answer_callback_query(call.id, text='У вас недостаточно осколков')
        elif action == 'super_spins':
            const = 80
            if not start_shards < const * number:
                new_super_spins = number
                new_shards = int(start_shards) - const * number
                update_currency(user_id, 'super_spins', new_super_spins)
                update_currency(user_id, 'shards', new_shards - get_currency(user_id, 'shards'))
                super_spins = get_currency(user_id, 'super_spins')
                spins = get_currency(user_id, 'spins')
                bot.answer_callback_query(call.id, text=f'Теперь у вас\n🧧{super_spins} супер {decline_spins(spins)} и 🔮{new_shards} {decline_fragments(new_shards)}')
                bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=exchange_menu_text(spins, new_shards, super_spins), reply_markup=markup)
            else:
                bot.answer_callback_query(call.id, text='У вас недостаточно осколков')
    except Exception as e:
        bot.send_message(user_id, text=f'Ошибка в модуле частичного обмена: {e}')
        bot.answer_callback_query(call.id)