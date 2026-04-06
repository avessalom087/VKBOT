from vkbottle.bot import Blueprint, Message
import functools
from vkbottle import BaseStateGroup
import database
import config
import utils

bp = Blueprint("PlayerCommands")

class RegistrationState(BaseStateGroup):
    WAIT_FOR_NAME = "WAIT_FOR_NAME"

def require_registration(func):
    @functools.wraps(func)
    async def wrapper(message: Message, *args, **kwargs):
        user_data = await database.get_user(message.from_id)
        if not user_data:
            await message.answer("❌ Вы не зарегистрированы в банке! Напишите: /регистрация [имя персонажа]")
            return
        return await func(message, *args, user_data=user_data, **kwargs)
    return wrapper

@bp.on.message(text=["/регистрация", "/reg", "/регистрация <char_name>", "/reg <char_name>"])
async def register_handler(message: Message, char_name: str = None):
    vk_id = message.from_id
    user_data = await database.get_user(vk_id)

    if user_data:
        await message.answer(f"✅ Вы уже зарегистрированы как {user_data.get('character_name')}.")
        return

    if not char_name:
        await message.answer("Пожалуйста, укажите имя персонажа после команды.\nПример: /регистрация Эльфира")
        return

    char_name = char_name.strip()
    if len(char_name) < config.MIN_NAME_LEN or len(char_name) > config.MAX_NAME_LEN:
        await message.answer(f"❌ Имя персонажа должно быть от {config.MIN_NAME_LEN} до {config.MAX_NAME_LEN} символов.")
        return

    users_info = await bp.api.users.get(user_ids=[vk_id])
    if users_info:
        vk_name = f"{users_info[0].first_name} {users_info[0].last_name}"
    else:
        vk_name = "Неизвестный"

    new_user = await database.create_user(vk_id, vk_name, char_name)

    greeting = "Поздравляем с регистрацией в банке!"
    if new_user.get("status") == "admin":
        greeting += "\n👑 Вам выданы права Банкира."

    await message.answer(f"✅ {greeting}\nИмя персонажа: {char_name}\nСчёт: {utils.format_balance(0)}")

# ─── /счёт ──────────────────────────────────────────────────────────────────

@bp.on.message(text=["/счёт", "/счет", "/bal", "/balance"])
@require_registration
async def balance_handler(message: Message, user_data: dict):
    char_name = user_data.get("character_name", "Неизвестно")
    balance = user_data.get("balance", 0)

    text = (f"👤 Персонаж: {char_name}\n"
            f"💰 Ваш счёт: {utils.format_balance(balance)}")

    await message.answer(text)

# ─── /история ───────────────────────────────────────────────────────────────

@bp.on.message(text=["/история", "/history"])
@require_registration
async def player_history_handler(message: Message, user_data: dict):
    vk_id = message.from_id
    history = await database.get_user_history(vk_id, limit=config.HISTORY_LIMIT)

    if not history:
        await message.answer("📭 У вас пока нет ни одной транзакции.")
        return

    blocks = [f"📜 Последние {len(history)} операций:"]
    for i, tx in enumerate(history, 1):
        blocks.append(f"--- Транзакция #{i} ---\n" + utils.format_transaction(tx, viewer_id=vk_id))

    await message.answer("\n\n".join(blocks))

# ─── /помощь ────────────────────────────────────────────────────────────────

@bp.on.message(text=["/помощь", "/help"])
async def help_handler(message: Message):
    is_admin = await database.check_is_admin(message.from_id)

    text = (
        "📖 ДОСТУПНЫЕ КОМАНДЫ:\n\n"
        "🔹 Ваш счёт:\n"
        "• /счёт — Показать текущий счёт\n"
        "• /снять [сумма] [причина] — Снять деньги со своего счёта\n"
        "• /история — Последние операции\n"
        "\n🔹 Прочее:\n"
        "• /регистрация [имя] — Регистрация в банке\n"
        "• /помощь — Этот список\n"
    )

    if is_admin:
        text += (
            "\n👑 Команды Банкира:\n"
            "• /банк — Таблица всех игроков\n"
            "• /счёт @игрок — Проверить баланс игрока\n"
            "• /начислить @игрок [сумма] [причина] — начислить одному\n"
            "• /начислить @игрок, @игрок [сумма] [причина] — начислить нескольким\n"
            "• /начислить @игрок [сумма], @игрок [сумма] [причина] — каждому свою сумму\n"
            "• /снять @игрок [сумма] [причина] — Снять у игрока\n"
            "• /история @игрок — История другого игрока\n"
            "• /изменитьперса @игрок новое_имя\n"
            "• /сделатьбанкиром @игрок\n"
            "• /снятьбанкира @игрок\n"
            "• /удалить @игрок — Удалить игрока\n"
        )

    await message.answer(text)

# ─── /снять (только для себя, игрокам) ──────────────────────────────────────

@bp.on.message(text=[
    "Снять <amount:int> <reason>", "/снять <amount:int> <reason>",
])
@require_registration
async def player_withdraw_handler(message: Message, amount: int, reason: str, user_data: dict):
    """Игроки могут снимать только со своего счёта."""
    # Валидация суммы
    if amount < config.MIN_TRANSACTION or amount > config.MAX_TRANSACTION:
        await message.answer(f"❌ Сумма должна быть от {config.MIN_TRANSACTION} до {config.MAX_TRANSACTION}.")
        return

    if len(reason) > config.MAX_REASON_LEN:
        await message.answer(f"❌ Причина слишком длинная (максимум {config.MAX_REASON_LEN} символов).")
        return

    try:
        new_balance = await database.change_balance(message.from_id, message.from_id, -amount, reason)
        response = (
            f"🔻 Успешно снято {utils.format_balance(amount)}.\n"
            f"💰 Остаток на счёте: {utils.format_balance(new_balance)}\n"
            f"📝 Причина: {reason}"
        )
        await message.answer(response)
    except ValueError as e:
        await message.answer(f"❌ Операция отклонена: {e}")
    except Exception as e:
        await message.answer(f"❌ Произошла ошибка при обработке транзакции: {e}")
