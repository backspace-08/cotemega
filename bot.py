from bot_core import bot, run_bot
from database import init_db
from features.arena import *
from features.gacha import *
from features.characters import *
from features.menu import *
from features.shop import *
from features.top import *
from features.profile import *
from features.exchange import *
from features.admin import *
from features.donate import *

if __name__ == '__main__':
    init_db()
    run_bot()
