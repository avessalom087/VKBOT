import re
from vkbottle.bot import Blueprint, Message
import functools
import database
import config
import utils

bp = Blueprint("AdminCommands")

def require_admin(func):
    @functools.wraps(func)
    async def wrapper(message: Message, *args, **kwargs):
        is_admin = await database.check_is_admin(message.from_id)
        if not is_admin:
            await message.answer("❌ У вас нет прав Банкира.")
            return
        admin_data = await database.get_user(message.from_id)
        return await func(message, *args, admin_data=admin_data, **kwargs)
    return wrapper

# ─── /банк ──────────────────────────────────────────────────────────────────

@bp.on.message(text=["/банк", "/bank"])
@require_admin
async def bank_handler(message: Message, admin_data: dict):
    users = await database.get_all_users()
    if not users:
        await message.answer("В банке пока нет зарегистрированных игроков.")
        return
    table = utils.generate_bank_table(users)
    await message.answer(f"```\n{table}\n```")

# ─── /счёт @user (для Банкиров) ───────────────────────────────────────────

@bp.on.message(text=["/счёт <mention>", "/счет <mention>"])
@require_admin
async def admin_check_balance_handler(message: Message, mention: str, admin_data: dict):
    target_id = utils.extract_user_id(mention)
    if not target_id:
        await message.answer("❌ Неверный формат упоминания.")
        return

    target_user = await database.get_user(target_id)
    if not target_user:
        await message.answer("❌ Пользователь не найден в базе банка.")
        return

    char_name = target_user.get("character_name", "Неизвестно")
    balance = target_user.get("balance", 0)

    await message.answer(f"👤 Персонаж: {char_name}\n💰 Счёт: {utils.format_balance(balance)}")

# ─── /начислить — с поддержкой нескольких игроков ───────────────────────────
#
#  Форматы:
#    /начислить @user 500 причина               — одному
#    /начислить @user, @user, @user 500 причина — нескольким одну сумму
#    /начислить @user 200, @user 300 причина    — каждому свою сумму
#    /начислить @user 200, @user 300, @user 100 причина

MENTION_RE = re.compile(r"\[id(\d+)\|[^\]]*\]")

def parse_multi_deposit(raw: str):
    """
    Парсит строку аргументов команды /начислить.
    Возвращает:
        list of (user_id: int, amount: int)  — пары «кому» + «сколько»
        reason: str
        error: str | None
    """
    # Убираем начальный пробел
    raw = raw.strip()

    # --- Формат А: "[@user] сумма, [@user] сумма, ... причина"  (каждому своя)
    # --- Формат Б: "[@user], [@user], ... сумма причина"        (всем одна)
    #
    # Стратегия: найти все упоминания + числа по порядку, последний токен-строка = причина

    # Разбиваем на «токены»: упоминание, число или остаток-строка
    token_re = re.compile(r"\[id\d+\|[^\]]*\]|\d+|[а-яА-Яa-zA-Z][^\[,\d]*")
    tokens = token_re.findall(raw)

    # Собираем «segments» — пары (mention_id, amount_or_None)
    mentions = []      # list of (user_id, amount_or_None)
    numbers = []       # list of int — числа, найденные вне пар
    text_parts = []    # строки — кандидаты на причину

    i = 0
    while i < len(tokens):
        token = tokens[i].strip()
        m = MENTION_RE.match(token)
        if m:
            uid = int(m.group(1))
            # Следующий токен — число?
            if i + 1 < len(tokens):
                next_tok = tokens[i + 1].strip()
                if re.fullmatch(r"\d+", next_tok):
                    mentions.append((uid, int(next_tok)))
                    i += 2
                    continue
            mentions.append((uid, None))
        elif re.fullmatch(r"\d+", token):
            numbers.append(int(token))
        else:
            text_parts.append(token.strip(" ,"))
        i += 1

    reason = " ".join(p for p in text_parts if p) or "Начисление"

    if not mentions:
        return None, None, "Не найдено ни одного упоминания игрока."

    # Определяем: у каждого своя сумма или одна общая?
    has_individual = all(amt is not None for _, amt in mentions)
    has_global = any(amt is None for _, amt in mentions) and len(numbers) > 0

    if has_individual:
        pairs = [(uid, amt) for uid, amt in mentions]
    elif has_global:
        global_amount = numbers[0]
        if global_amount < config.MIN_TRANSACTION or global_amount > config.MAX_TRANSACTION:
            return None, None, f"Сумма должна быть от {config.MIN_TRANSACTION} до {config.MAX_TRANSACTION}."
        pairs = [(uid, global_amount) for uid, _ in mentions]
    else:
        return None, None, "Не удалось определить сумму. Укажите сумму после каждого упоминания или одну общую сумму."

    # Валидация индивидуальных сумм
    for uid, amt in pairs:
        if amt < config.MIN_TRANSACTION or amt > config.MAX_TRANSACTION:
            return None, None, f"Сумма {amt} вне допустимого диапазона ({config.MIN_TRANSACTION}–{config.MAX_TRANSACTION})."

    return pairs, reason, None


@bp.on.message(text=["/начислить <args>", "Начислить <args>"])
@require_admin
async def deposit_handler(message: Message, args: str, admin_data: dict):
    pairs, reason, error = parse_multi_deposit(args)
    if error:
        await message.answer(f"❌ Ошибка: {error}\n\nФорматы:\n"
                             "• /начислить @игрок сумма причина\n"
                             "• /начислить @игрок, @игрок 500 причина\n"
                             "• /начислить @игрок 200, @игрок 300 причина")
        return

    results = []
    for target_id, amount in pairs:
        target_user = await database.get_user(target_id)
        if not target_user:
            results.append(f"⚠️ ID {target_id} — не найден в банке, пропущен.")
            continue
        try:
            new_balance = await database.change_balance(target_id, message.from_id, amount, reason)
            char = target_user.get("character_name", "Неизвестно")
            results.append(f"✅ {char}: +{utils.format_balance(amount)} → {utils.format_balance(new_balance)}")
        except ValueError as e:
            char = target_user.get("character_name", f"ID {target_id}")
            results.append(f"❌ {char}: {e}")
        except Exception as e:
            results.append(f"❌ ID {target_id}: непредвиденная ошибка — {e}")

    summary = "\n".join(results)
    await message.answer(f"📋 Результаты начисления (причина: {reason}):\n\n{summary}")

# ─── /снять @user сумма причина (только для Банкира) ────────────────────────

@bp.on.message(text=[
    "/снять <mention> <amount:int> <reason>",
    "Снять <mention> <amount:int> <reason>"
])
@require_admin
async def admin_withdraw_handler(message: Message, mention: str, amount: int, reason: str, admin_data: dict):
    target_id = utils.extract_user_id(mention)
    if not target_id:
        await message.answer("❌ Неверный формат упоминания пользователя.")
        return

    if amount < config.MIN_TRANSACTION or amount > config.MAX_TRANSACTION:
        await message.answer(f"❌ Сумма должна быть от {config.MIN_TRANSACTION} до {config.MAX_TRANSACTION}.")
        return

    target_user = await database.get_user(target_id)
    if not target_user:
        await message.answer("❌ Пользователь не найден в банке.")
        return

    try:
        new_balance = await database.change_balance(target_id, message.from_id, -amount, reason)
        char = target_user.get("character_name", "Неизвестно")
        await message.answer(
            f"🔻 Снято {utils.format_balance(amount)} у персонажа {char}.\n"
            f"💰 Остаток: {utils.format_balance(new_balance)}\n"
            f"📝 Причина: {reason}"
        )
    except ValueError as e:
        await message.answer(f"❌ Операция отклонена: {e}")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

# ─── /история @user ──────────────────────────────────────────────────────────

@bp.on.message(text=["/история <mention>"])
@require_admin
async def admin_history_handler(message: Message, mention: str, admin_data: dict):
    target_id = utils.extract_user_id(mention)
    if not target_id:
        await message.answer("❌ Неверный формат упоминания пользователя.")
        return

    try:
        history = await database.get_user_history(target_id, limit=config.HISTORY_LIMIT)
        
        if not history:
            await message.answer("📭 У этого пользователя пока нет транзакций.")
            return
            
        blocks = [f"📜 Последние {len(history)} операций пользователя:"]
        for i, tx in enumerate(history, 1):
            blocks.append(f"--- Транзакция #{i} ---\n" + utils.format_transaction(tx, viewer_id=message.from_id))
            
        await message.answer("\n\n".join(blocks))
    except Exception as e:
        if "requires an index" in str(e):
            await message.answer("⚠️ Ошибка работы с базой: Необходим индекс Firestore.\n\n"
                                 "Пожалуйста, проверьте логи на Render.com и перейдите по ссылке для создания индекса.")
        else:
            await message.answer(f"❌ Не удалось получить историю: {str(e)}")

# ─── /изменитьперса ───────────────────────────────────────────────────────────

@bp.on.message(text=["/изменитьперса <mention> <new_name>", "Изменитьперса <mention> <new_name>"])
@require_admin
async def change_character_name(message: Message, mention: str, new_name: str, admin_data: dict):
    target_id = utils.extract_user_id(mention)
    if not target_id:
        await message.answer("❌ Неверный формат упоминания.")
        return

    new_name = new_name.strip()
    if len(new_name) < config.MIN_NAME_LEN or len(new_name) > config.MAX_NAME_LEN:
        await message.answer(f"❌ Имя персонажа должно быть от {config.MIN_NAME_LEN} до {config.MAX_NAME_LEN} символов.")
        return

    target_user = await database.get_user(target_id)
    if not target_user:
        await message.answer("❌ Пользователь не найден.")
        return

    await database.update_user(target_id, character_name=new_name)
    await message.answer(f"✅ Имя персонажа изменено на: {new_name}")

# ─── /сделатьбанкиром ────────────────────────────────────────────────────────

@bp.on.message(text=["/сделатьбанкиром <mention>", "Сделатьбанкиром <mention>",
                      "/сделатьадмином <mention>", "Сделатьадмином <mention>"])
@require_admin
async def set_admin_handler(message: Message, mention: str, admin_data: dict):
    target_id = utils.extract_user_id(mention)
    if not target_id:
        await message.answer("❌ Неверный формат упоминания.")
        return

    target_user = await database.get_user(target_id)
    if not target_user:
        await message.answer("❌ Пользователь не найден.")
        return

    await database.update_user(target_id, status="admin")
    await message.answer(f"👑 Персонаж {target_user.get('character_name')} назначен Банкиром.")

# ─── /снятьбанкира ───────────────────────────────────────────────────────────

@bp.on.message(text=["/снятьбанкира <mention>", "Снятьбанкира <mention>",
                      "/снятьадмина <mention>", "Снятьадмина <mention>"])
@require_admin
async def remove_admin_handler(message: Message, mention: str, admin_data: dict):
    target_id = utils.extract_user_id(mention)
    if not target_id:
        await message.answer("❌ Неверный формат упоминания.")
        return

    if target_id == config.ADMIN_VK_ID:
        await message.answer("❌ Нельзя снять права с Главного Банкира (указан в .env).")
        return

    target_user = await database.get_user(target_id)
    if not target_user:
        await message.answer("❌ Пользователь не найден.")
        return

    await database.update_user(target_id, status="player")
    await message.answer(f"👤 Персонаж {target_user.get('character_name')} больше не Банкир.")

# ─── /удалить ────────────────────────────────────────────────────────────────

@bp.on.message(text=["/удалить <mention>", "Удалить <mention>"])
@require_admin
async def delete_user_handler(message: Message, mention: str, admin_data: dict):
    target_id = utils.extract_user_id(mention)
    if not target_id:
        await message.answer("❌ Неверный формат упоминания.")
        return

    if target_id == config.ADMIN_VK_ID:
        await message.answer("❌ Нельзя удалить Главного Банкира.")
        return

    target_user = await database.get_user(target_id)
    if not target_user:
        await message.answer("❌ Пользователь не найден.")
        return

    await database.delete_user(target_id)
    await message.answer(f"🗑️ Персонаж {target_user.get('character_name')} удалён из банка.")
