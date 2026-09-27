import json

from sqlalchemy import select

from config import DATA_DIR
from db.models import Character
from db.session import get_session, init_db

CHARACTERS_JSON = DATA_DIR / "characters.json"


def seed() -> None:
    init_db()

    with open(CHARACTERS_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)

    with get_session() as session:
        for char in data["characters"]:
            values = {
                "image_path": f"{char['rarity']}/{char['filename']}",
                "translation": char["name_ru"],
                "rarity": char["rarity"],
                "type": char.get("type", 0),
                "gender": char.get("gender", "unknown"),
                "base_hp": char.get("health", 1000),
                "base_attack": char.get("attack", 100),
            }
            existing = session.execute(
                select(Character).where(Character.char_name == char["name_en"])
            ).scalar_one_or_none()

            if existing:
                for key, value in values.items():
                    setattr(existing, key, value)
            else:
                session.add(Character(char_name=char["name_en"], **values))

    print(f"Seeded {len(data['characters'])} characters")


if __name__ == "__main__":
    seed()
