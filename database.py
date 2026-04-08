import asyncio
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
from datetime import datetime, timezone
import logging
import config

logger = logging.getLogger("vkbot.database")

# Initialize Firebase app
if not firebase_admin._apps:
    try:
        cred = credentials.Certificate(config.FIREBASE_CREDENTIALS)
        firebase_admin.initialize_app(cred)
        logger.info("Firebase initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize Firebase: {e}")
        raise

db = firestore.client()

def _get_user_sync(vk_id: int):
    doc = db.collection('users').document(str(vk_id)).get()
    if doc.exists:
        return doc.to_dict()
    return None

async def get_user(vk_id: int):
    return await asyncio.to_thread(_get_user_sync, vk_id)

def _create_user_sync(vk_id: int, vk_name: str, character_name: str):
    user_ref = db.collection('users').document(str(vk_id))
    status = "admin" if vk_id == config.ADMIN_VK_ID else "player"
    user_data = {
        "vk_id": vk_id,
        "vk_name": vk_name,
        "character_name": character_name,
        "status": status,
        "balance": 0,
        "registered_at": datetime.now(timezone.utc)
    }
    user_ref.set(user_data)
    return user_data

async def create_user(vk_id: int, vk_name: str, character_name: str):
    return await asyncio.to_thread(_create_user_sync, vk_id, vk_name, character_name)

def _update_user_sync(vk_id: int, **kwargs):
    user_ref = db.collection('users').document(str(vk_id))
    user_ref.update(kwargs)

async def update_user(vk_id: int, **kwargs):
    await asyncio.to_thread(_update_user_sync, vk_id, **kwargs)

async def check_is_admin(vk_id: int) -> bool:
    if vk_id == config.ADMIN_VK_ID:
        return True
    user = await get_user(vk_id)
    if user and user.get("status") == "admin":
        return True
    return False

def _change_balance_sync(user_id: int, admin_id: int, amount: int, reason: str):
    user_ref = db.collection('users').document(str(user_id))
    
    @firestore.transactional
    def update_in_transaction(transaction, user_ref):
        snapshot = user_ref.get(transaction=transaction)
        if not snapshot.exists:
            raise ValueError("Пользователь не найден.")
            
        user_data = snapshot.to_dict()
        current_balance = user_data.get("balance", 0)
        
        new_balance = current_balance + amount
        if new_balance < 0:
            raise ValueError(f"Недостаточно средств. Текущий счёт: {current_balance} ft")
            
        transaction.update(user_ref, {
            "balance": new_balance
        })
        
        tx_ref = db.collection('transactions').document()
        transaction.set(tx_ref, {
            "user_id": user_id,
            "admin_id": admin_id,
            "amount": amount,
            "reason": reason,
            "balance_after": new_balance,
            "timestamp": datetime.now(timezone.utc)
        })
        
        return new_balance

    tr = db.transaction()
    return update_in_transaction(tr, user_ref)

async def change_balance(user_id: int, admin_id: int, amount: int, reason: str):
    return await asyncio.to_thread(_change_balance_sync, user_id, admin_id, amount, reason)

def _get_all_users_sync():
    users_ref = db.collection('users')
    docs = users_ref.order_by("balance", direction=firestore.Query.DESCENDING).limit(config.BANK_TOP_LIMIT).get()
    return [doc.to_dict() for doc in docs]

async def get_all_users():
    return await asyncio.to_thread(_get_all_users_sync)

def _get_all_users_unlimited_sync():
    users_ref = db.collection('users')
    docs = users_ref.order_by("balance", direction=firestore.Query.DESCENDING).get()
    return [doc.to_dict() for doc in docs]

async def get_all_users_unlimited():
    return await asyncio.to_thread(_get_all_users_unlimited_sync)

def _get_user_history_sync(user_id: int, limit: int):
    tx_ref = db.collection('transactions')
    query = tx_ref.where(filter=firestore.FieldFilter("user_id", "==", user_id)).order_by("timestamp", direction=firestore.Query.DESCENDING).limit(limit)
    docs = query.get()
    return [doc.to_dict() for doc in docs]

async def get_user_history(user_id: int, limit: int = config.HISTORY_LIMIT):
    return await asyncio.to_thread(_get_user_history_sync, user_id, limit)

def _delete_user_sync(vk_id: int):
    db.collection('users').document(str(vk_id)).delete()

async def delete_user(vk_id: int):
    await asyncio.to_thread(_delete_user_sync, vk_id)
