import unittest
from handlers.admin import extract_user_id

class TestAdminRegex(unittest.TestCase):
    
    def test_extract_user_id_valid(self):
        # Regular mention
        self.assertEqual(extract_user_id("[id1234567|@username]"), 1234567)
        # Mention with name
        self.assertEqual(extract_user_id("[id987654|Иван Иванов]"), 987654)
        # Inside text
        self.assertEqual(extract_user_id("Переведи [id111222|Петру] 500 рублей"), 111222)
        
    def test_extract_user_id_invalid(self):
        # Invalid format
        self.assertIsNone(extract_user_id("@username"))
        self.assertIsNone(extract_user_id("id1234567"))
        self.assertIsNone(extract_user_id("[club123|Группа]"))
        
if __name__ == '__main__':
    unittest.main()
