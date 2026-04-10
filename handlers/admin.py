import re
import os
import csv
import tempfile
from vkbottle import DocMessagesUploader
from vkbottle.bot import Blueprint, Message
import functools
import database
import config
import utils
import flavor

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
    await message.answer(table)

@bp.on.message(text=["/банк эксель", "/банк excel", "Банк эксель", "Банк excel", "/банк выгрузка"])
@require_admin
async def bank_excel_handler(message: Message, admin_data: dict):
    users = await database.get_all_users_unlimited()
    if not users:
        await message.answer("В банке пока нет зарегистрированных игроков.")
        return
    
    try:
        # Пишем файл с BOM для корректного отображения кириллицы в русском Excel (разделитель - точка с запятой)
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix=".csv", prefix="bank_", encoding='utf-8-sig', newline='') as tmp:
            writer = csv.writer(tmp, delimiter=';')
            writer.writerow(["VK ID", "Имя ВК", "Персонаж", "Статус", "Баланс (ft)"])
            for u in users:
                status_ru = "Администратор" if u.get("status") == "admin" else "Игрок"
                writer.writerow([str(u.get('vk_id', '')), u.get('vk_name', ''), u.get('character_name', ''), status_ru, u.get('balance', 0)])
            temp_path = tmp.name
        
        uploader = DocMessagesUploader(bp.api)
        doc = await uploader.upload(title="База_Банка.csv", file_source=temp_path, peer_id=message.peer_id)
        
        await message.answer("✅ Вся база игроков успешно выгружена:", attachment=doc)
    except Exception as e:
        await message.answer(f"❌ Ошибка выгрузки: {e}")
    finally:
        if 'temp_path' in locals() and os.path.exists(temp_path):
            os.remove(temp_path)

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

def parse_multi_deposit(raw: str):
    """
    Парсит строку аргументов команды /начислить.
    Возвращает:
        list of (user_id: int, amount: int)  — пары «кому» + «сколько»
        reason: str
        error: str | None
    """
    raw = raw.strip()
    mentions = []
    numbers = []
    
    mention_re = re.compile(r"^(?:\[id(\d+)\|[^\]]*\]|(?:@|\*|vk\.com/)?id(\d+))", re.IGNORECASE)
    number_re = re.compile(r"^\d+")
    separator_re = re.compile(r"^[\s,]+")
    
    idx = 0
    while idx < len(raw):
        sep_match = separator_re.match(raw, idx)
        if sep_match:
            idx = sep_match.end()
            if idx >= len(raw): break
                
        m_match = mention_re.match(raw, idx)
        if m_match:
            mentions.append(int(m_match.group(1) or m_match.group(2)))
            idx = m_match.end()
            continue
            
        n_match = number_re.match(raw, idx)
        if n_match:
            numbers.append(int(n_match.group(0)))
            idx = n_match.end()
            continue
            
        break
        
    reason = raw[idx:].strip() or "Начисление"
    
    if not mentions:
        return None, None, "Не найдено ни одного упоминания игрока."

    pairs = []
    if len(numbers) == 1 or (len(numbers) > 1 and len(mentions) != len(numbers)):
        global_amt = numbers[0]
        pairs = [(uid, global_amt) for uid in mentions]
        
        if len(numbers) > 1:
            extra_nums = " ".join(str(n) for n in numbers[1:])
            reason = f"{extra_nums} {reason}".strip()
            
    elif len(numbers) == len(mentions):
        pairs = list(zip(mentions, numbers))
    else:
        return None, None, "Не удалось определить сумму. Укажите сумму после каждого упоминания или одну общую сумму."

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
    flavor_text = f"\n\n_{flavor.get_deposit_flavor()}_"
    await message.answer(f"📋 Результаты начисления (причина: {reason}):\n\n{summary}{flavor_text}")

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
            f"📝 Причина: {reason}\n\n"
            f"_{flavor.get_withdraw_flavor()}_"
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
