import json
import urllib.request

from sqlalchemy import delete, select

from config import CHARACTERS_URL
from db.models import Character, UserCharacter
from db.session import get_session, init_db


def _load_catalog() -> dict:
    """Character catalog from R2 (CHARACTERS_URL)."""
    if not CHARACTERS_URL:
        raise RuntimeError("CHARACTERS_URL не задан (каталог персонажей хранится в R2)")
    # Cloudflare blocks the default "Python-urllib" User-Agent (403), so set our own.
    request = urllib.request.Request(CHARACTERS_URL, headers={"User-Agent": "megaverse-bot/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def apply_catalog(data: dict) -> dict:
    """Upsert the given catalog into the DB and prune removed characters.

    Returns {"total": int, "removed": int, "characters": list[dict]}.
    """
    chars = data["characters"]

    with get_session() as session:
        for char in chars:
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

        # The catalog is the source of truth: drop characters no longer in it.
        names = {char["name_en"] for char in chars}
        stale_ids = session.execute(
            select(Character.char_id).where(Character.char_name.notin_(names))
        ).scalars().all()
        if stale_ids:
            session.execute(delete(UserCharacter).where(UserCharacter.char_id.in_(stale_ids)))
            session.execute(delete(Character).where(Character.char_id.in_(stale_ids)))

    return {"total": len(chars), "removed": len(stale_ids), "characters": chars}


def sync_characters() -> dict:
    """Pull the catalog from R2 and apply it to the DB."""
    return apply_catalog(_load_catalog())


def seed() -> None:
    init_db()
    summary = sync_characters()
    print(f"Seeded {summary['total']} characters, removed {summary['removed']} stale")


if __name__ == "__main__":
    seed()
