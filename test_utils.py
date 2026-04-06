import unittest
from datetime import datetime, timezone

# We mock config before importing utils so it doesn't fail if config variables change
import sys
from unittest.mock import MagicMock

mock_config = MagicMock()
mock_config.BANK_NAME = "Денежные сбережения"
mock_config.CURRENCY_FORMS = ("форинт", "форинта", "форинтов")
mock_config.BANK_TOP_LIMIT = 20
mock_config.TIMEZONE_OFFSET = 3

sys.modules['config'] = mock_config

import utils

class TestUtils(unittest.TestCase):
    
    def test_format_balance(self):
        self.assertEqual(utils.format_balance(0), "0 ₽")
        self.assertEqual(utils.format_balance(1000), "1 000 ₽")
        self.assertEqual(utils.format_balance(1000000), "1 000 000 ₽")
        self.assertEqual(utils.format_balance(-500), "-500 ₽")
        
    def test_get_currency_form(self):
        self.assertEqual(utils.get_currency_form(1), "форинт")
        self.assertEqual(utils.get_currency_form(2), "форинта")
        self.assertEqual(utils.get_currency_form(5), "форинтов")
        self.assertEqual(utils.get_currency_form(11), "форинтов")
        self.assertEqual(utils.get_currency_form(21), "форинт")
        self.assertEqual(utils.get_currency_form(102), "форинта")
        
    def test_format_user_row(self):
        user = {
            "vk_id": 12345,
            "vk_name": "Test User",
            "character_name": "Tester",
            "status": "admin",
            "balance": 1500
        }
        row = utils.format_user_row(1, user)
        self.assertIn("12345", row)
        self.assertIn("Test User", row)
        self.assertIn("Tester", row)
        self.assertIn("Админ", row)
        self.assertIn("1 500 ₽", row)

    def test_generate_bank_table(self):
        users = [
            {"vk_id": 1, "vk_name": "User 1", "character_name": "C1", "status": "admin", "balance": 1000},
            {"vk_id": 2, "vk_name": "User 2", "character_name": "C2", "status": "player", "balance": 500}
        ]
        table = utils.generate_bank_table(users)
        self.assertIn("ДЕНЕЖНЫЕ СБЕРЕЖЕНИЯ", table)
        self.assertIn("User 1", table)
        self.assertIn("User 2", table)
        self.assertIn("Всего игроков: 2", table)
        self.assertIn("Всего в обороте: 1 500 ₽", table)

if __name__ == '__main__':
    unittest.main()
