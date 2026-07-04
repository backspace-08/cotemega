import json
import os
from config import DB_CONFIG, DATA_DIR
import psycopg2

CHARACTERS_JSON = DATA_DIR / 'characters.json'

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    user_id BIGINT PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    points INTEGER DEFAULT 0,
    shards INTEGER DEFAULT 0,
    spins INTEGER DEFAULT 10,
    super_spins INTEGER NOT NULL DEFAULT 0,
    mmr INTEGER DEFAULT 0,
    last_button_press TIMESTAMP DEFAULT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    deck_1 INTEGER DEFAULT 0,
    deck_2 INTEGER DEFAULT 0,
    deck_3 INTEGER DEFAULT 0,
    verse TEXT DEFAULT 'COTE'
);

CREATE TABLE IF NOT EXISTS characters (
    char_id SERIAL PRIMARY KEY,
    char_name TEXT NOT NULL UNIQUE,
    image_path TEXT NOT NULL,
    translation TEXT,
    rarity TEXT,
    type INTEGER DEFAULT 0,
    health INTEGER DEFAULT 1000,
    attack INTEGER DEFAULT 100,
    verse TEXT DEFAULT 'COTE'
);

CREATE TABLE IF NOT EXISTS inventory (
    user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
    char_id INTEGER REFERENCES characters(char_id) ON DELETE CASCADE,
    obtained_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (user_id, char_id)
);

CREATE TABLE IF NOT EXISTS arena_queue (
    user_id BIGINT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    message_id BIGINT,
    opponent_id BIGINT,
    deck_1 INTEGER DEFAULT 0,
    deck_2 INTEGER DEFAULT 0,
    deck_3 INTEGER DEFAULT 0,
    deck_1hp INTEGER DEFAULT 0,
    deck_2hp INTEGER DEFAULT 0,
    deck_3hp INTEGER DEFAULT 0,
    points INTEGER DEFAULT 0,
    attack INTEGER DEFAULT 0,
    def INTEGER DEFAULT 0,
    bonus INTEGER DEFAULT 0,
    applied_bonus INTEGER DEFAULT 0,
    round INTEGER DEFAULT 0,
    switch INTEGER DEFAULT 0,
    pick_phase INTEGER DEFAULT 0,
    deck_order TEXT,
    picked_chars TEXT,
    first_picker INTEGER DEFAULT 0,
    second_picker INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS battle_log (
    id SERIAL PRIMARY KEY,
    user1_id BIGINT,
    user2_id BIGINT,
    user1_name TEXT,
    user2_name TEXT,
    fought_at TIMESTAMP DEFAULT NOW()
);
"""

def seed():
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = True

    with conn.cursor() as cur:
        cur.execute(SCHEMA_SQL)
        print("Tables created successfully")

    with open(CHARACTERS_JSON, 'r', encoding='utf-8') as f:
        data = json.load(f)

    verse = 'COTE'
    inserted = 0
    skipped = 0

    with conn.cursor() as cur:
        for char in data['characters']:
            char_name = char['name_en']
            image_path = f"{char['rarity']}/{char['filename']}"
            translation = char['name_ru']
            rarity = char['rarity']
            ctype = char.get('type', 0)
            health = char.get('health', 1000)
            attack = char.get('attack', 100)

            cur.execute("""
                INSERT INTO characters (char_name, image_path, translation, rarity, type, health, attack, verse)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (char_name) DO UPDATE SET
                    image_path = EXCLUDED.image_path,
                    translation = EXCLUDED.translation,
                    rarity = EXCLUDED.rarity,
                    type = EXCLUDED.type,
                    health = EXCLUDED.health,
                    attack = EXCLUDED.attack,
                    verse = EXCLUDED.verse
            """, (char_name, image_path, translation, rarity, ctype, health, attack, verse))
            inserted += 1

    print(f"Seeded {inserted} characters")
    conn.close()

if __name__ == '__main__':
    seed()
