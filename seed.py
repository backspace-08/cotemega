import json
from config import DATA_DIR
from database import get_session
from models import Character
from sqlalchemy import select

CHARACTERS_JSON = DATA_DIR / 'characters.json'


def seed():
    with open(CHARACTERS_JSON, 'r', encoding='utf-8') as f:
        data = json.load(f)

    with get_session() as session:
        for char in data['characters']:
            existing = session.execute(
                select(Character).where(Character.char_name == char['name_en'])
            ).scalar_one_or_none()

            if existing:
                existing.image_path = f"{char['rarity']}/{char['filename']}"
                existing.translation = char['name_ru']
                existing.rarity = char['rarity']
                existing.type = char.get('type', 0)
                existing.health = char.get('health', 1000)
                existing.attack = char.get('attack', 100)
            else:
                session.add(Character(
                    char_name=char['name_en'],
                    image_path=f"{char['rarity']}/{char['filename']}",
                    translation=char['name_ru'],
                    rarity=char['rarity'],
                    type=char.get('type', 0),
                    health=char.get('health', 1000),
                    attack=char.get('attack', 100),
                ))

    print(f"Seeded {len(data['characters'])} characters")


if __name__ == '__main__':
    seed()
