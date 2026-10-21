"""Localization regression tests.

The English table is keyed by the Russian source text, so a renamed or newly
added `t(lang, "...")` literal silently falls back to Russian. These tests scan
the source for such literals and fail when a translation is missing.
"""

import ast
import pathlib
import unittest

from core.i18n import LONG, normalize, t
from core.locales.en import EN

ROOT = pathlib.Path(__file__).resolve().parent.parent
SKIPPED_TOP_LEVEL = {"venv", ".git", "tests", "scripts", "cote_cfr"}
SKIPPED_FILES = {"admin.py", "admin_chars.py", "metrics.py"}


def _translation_keys() -> set[str]:
    keys: set[str] = set()
    for path in ROOT.rglob("*.py"):
        rel = path.relative_to(ROOT)
        if rel.parts[0] in SKIPPED_TOP_LEVEL or "__pycache__" in rel.parts:
            continue
        if path.name in SKIPPED_FILES:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
                continue
            if node.func.id != "t" or len(node.args) < 2:
                continue
            key = node.args[1]
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                keys.add(key.value)
    return keys


class I18nTest(unittest.TestCase):
    def test_every_source_key_is_translated(self):
        missing = sorted(k for k in _translation_keys() if not k.startswith("@") and k not in EN)
        self.assertEqual(missing, [], f"Missing EN translations: {missing}")

    def test_every_long_key_exists_in_both_locales(self):
        for lang in ("ru", "en"):
            for key in _translation_keys():
                if key.startswith("@"):
                    self.assertIn(key, LONG[lang], f"{key} missing from {lang}")

    def test_english_and_fallback(self):
        self.assertEqual(t("en", "🏆 Топ"), "🏆 Top")
        self.assertEqual(t("ru", "🏆 Топ"), "🏆 Топ")
        self.assertEqual(t("xx", "🏆 Топ"), "🏆 Топ")
        self.assertEqual(t("en", "no such key"), "no such key")

    def test_placeholders_are_formatted(self):
        self.assertEqual(t("en", "🎯 Калибровка {matches}/{total}", matches=3, total=10), "🎯 Calibration 3/10")
        self.assertIn("Action points", t("en", "@about", timeout=60, comments=2))

    def test_normalize(self):
        self.assertEqual(normalize(None), "ru")
        self.assertEqual(normalize("en"), "en")
        self.assertEqual(normalize("de"), "ru")
