"""Covers src/context/symbols.py: bank shape/uniqueness, the "none" sentinel, fixture coverage,
and the cross-language sync with src/symbols.ts (the frontend's id -> lucide component map)."""
import json
import re
import unittest
from pathlib import Path

from src.context.symbols import NO_SYMBOL, SYMBOL_BANK, SYMBOL_IDS

CONTEXT_FIXTURES_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "context_fixtures.json"
FRONTEND_SYMBOLS_PATH = Path(__file__).resolve().parents[2] / "src" / "symbols.ts"

_ID_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


class SymbolBankTest(unittest.TestCase):
    def test_ids_are_unique(self):
        ids = [symbol_id for symbol_id, _ in SYMBOL_BANK]
        self.assertEqual(len(ids), len(set(ids)))

    def test_ids_match_kebab_case_pattern(self):
        for symbol_id, _ in SYMBOL_BANK:
            self.assertRegex(symbol_id, _ID_PATTERN)

    def test_sentinel_is_not_a_bank_id(self):
        self.assertNotIn(NO_SYMBOL, SYMBOL_IDS)

    def test_bank_size_is_reasonable(self):
        self.assertGreaterEqual(len(SYMBOL_BANK), 40)
        self.assertLessEqual(len(SYMBOL_BANK), 200)

    def test_every_fixture_symbol_is_in_the_bank_or_the_sentinel(self):
        fixtures = json.loads(CONTEXT_FIXTURES_PATH.read_text(encoding="utf-8"))
        allowed = SYMBOL_IDS | {NO_SYMBOL}
        for fixture in fixtures:
            for item in fixture["response"]["dynamicIcons"]:
                self.assertIn(item["symbol"], allowed, f"fixture {fixture['description']!r}")

    def test_every_bank_id_is_mirrored_in_the_frontend_symbol_map(self):
        frontend_source = FRONTEND_SYMBOLS_PATH.read_text(encoding="utf-8")
        missing = [
            symbol_id for symbol_id in SYMBOL_IDS if f"'{symbol_id}':" not in frontend_source
        ]
        self.assertEqual(missing, [], f"ids missing from {FRONTEND_SYMBOLS_PATH}: {missing}")


if __name__ == "__main__":
    unittest.main()
