import os
import json
import logging
from dotenv import load_dotenv

load_dotenv()

# ─── Логирование ───────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("vkbot")

# ─── VK ────────────────────────────────────────────────────────────────────────
VK_TOKEN: str = os.getenv("VK_TOKEN", "").strip()

_admin_id_raw = os.getenv("ADMIN_VK_ID", "0").strip()
ADMIN_VK_ID: int = int(_admin_id_raw) if _admin_id_raw.isdigit() else 0

if not VK_TOKEN:
    raise ValueError("VK_TOKEN не задан! Проверьте файл .env или Environment Variables в панели Render.com.")
if not ADMIN_VK_ID:
    raise ValueError("ADMIN_VK_ID не задан или равен 0! Проверьте файл .env или Environment Variables в панели Render.com.")

# ─── Firebase ──────────────────────────────────────────────────────────────────
_firebase_raw = os.getenv("FIREBASE_CREDENTIALS", "")

def load_firebase_credentials(raw_val: str) -> dict:
    # 1. Try to parse as JSON string
    if raw_val and raw_val != "{}":
        try:
            return json.loads(raw_val)
        except json.JSONDecodeError:
            # 2. If not JSON, maybe it's a file path?
            if os.path.exists(raw_val):
                with open(raw_val, 'r', encoding='utf-8') as f:
                    return json.load(f)
    
    # 3. Fallback: Look for the first .json file starting with 'avesproject' or containing 'firebase-adminsdk'
    json_files = [f for f in os.listdir('.') if f.endswith('.json') and ('firebase-adminsdk' in f or f.startswith('avesproject'))]
    if json_files:
        logger.info(f"Using Firebase credentials from local file: {json_files[0]}")
        with open(json_files[0], 'r', encoding='utf-8') as f:
            return json.load(f)
            
    raise ValueError("FIREBASE_CREDENTIALS не найден (ни в .env, ни как локальный JSON)")

FIREBASE_CREDENTIALS = load_firebase_credentials(_firebase_raw)

# ─── Константы игры ────────────────────────────────────────────────────────────
BANK_NAME = "Банк"
CURRENCY_FORMS = ("ft", "ft", "ft")  # единственное число не меняется для ft

MIN_TRANSACTION = 1
MAX_TRANSACTION = 5_000_000
MAX_REASON_LEN = 200
MIN_NAME_LEN = 3
MAX_NAME_LEN = 32
HISTORY_LIMIT = 5
BANK_TOP_LIMIT = 20
DELETE_CONFIRM_TIMEOUT = 60  # секунд

# ─── Константы кубиков ─────────────────────────────────────────────────────────
ALLOWED_DICE = (4, 6, 8, 10, 12, 20, 100)
DICE_COOLDOWN = 3
MAX_DICE_LABEL_LEN = 50
MAX_DICE_COUNT = 10

# ─── Timezone ──────────────────────────────────────────────────────────────────
TIMEZONE_OFFSET = 3  # UTC+3 (Москва)
