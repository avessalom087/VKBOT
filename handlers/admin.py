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
    target_id = await resolve_to_id(bp.api, mention)
    if not target_id:
        await message.answer("❌ Не удалось распознать пользователя.")
        return

    target_user = await database.get_user(target_id)
    if not target_user:
        await message.answer("❌ Пользователь не найден в базе банка.")
        return

    char_name = target_user.get("character_name", "Неизвестно")
    balance = target_user.get("balance", 0)

    await message.answer(f"👤 Персонаж: {char_name}\n💰 Счёт: {utils.format_balance(balance)}")

# ─── /начислить — с поддержкой нескольких игроков ───────────────────────────
# Форматы:
#   /начислить @user 500 причина
#   /начислить @user, @user 500 причина
#   /начислить @user 100, @user 200 причина

# Компилируем один раз на старте
_MENTION_RE = re.compile(r"\[(?:id|club|public)(\d+)\|[^\]]*\]|@([a-zA-Z0-9._]+)", re.IGNORECASE)
_NUMBER_RE  = re.compile(r"(\d+)(?![a-zA-Z_])")

def parse_multi_deposit(raw: str):
    """
    Парсит строку аргументов команды /начислить.
    Поддерживает алиасы (@aves_087), [id123|Имя], @id123.
    Возвращает:
        list of (mention_str: str, amount: int)
        reason: str
        error: str | None
    """
    raw = raw.strip()
    if not raw:
        return None, None, "Пустой запрос."

    mentions = []
    numbers  = []
    last_end = 0

    pos = 0
    while pos < len(raw):
        # Пропускаем пробелы и запятые
        while pos < len(raw) and raw[pos] in " \t,":
            pos += 1
        if pos >= len(raw):
            break

        # Сначала ищем упоминание (@alias или [id...|...])
        m_match = _MENTION_RE.match(raw, pos)
        if m_match:
            uid = m_match.group(1) or m_match.group(2)
            mentions.append(uid)
            last_end = m_match.end()
            pos = last_end
            continue

        # Затем ищем число
        n_match = _NUMBER_RE.match(raw, pos)
        if n_match and n_match.start() == pos:
            numbers.append(int(n_match.group(1)))
            last_end = n_match.end()
            pos = last_end
            continue

        # Ни то ни другое — начало текста причины
        break

    reason = raw[last_end:].strip().lstrip(",").strip() or "Начисление"

    if not mentions:
        return None, None, "Не найдено ни одного упоминания игрока."

    if not numbers:
        return None, None, "Не указана сумма начисления."

    if len(numbers) == 1:
        # одна сумма на всех
        pairs = [(m, numbers[0]) for m in mentions]
    elif len(numbers) == len(mentions):
        # каждому своя сумма
        pairs = list(zip(mentions, numbers))
    else:
        return None, None, "Не удалось сопоставить суммы игрокам. Укажите либо одну общую сумму, либо по сумме после каждого игрока."

    return pairs, reason, None


async def resolve_to_id(api, raw_mention: str) -> int:
    """Превращает строку (ID или алиас) в цифровой VK ID."""
    if not raw_mention: return None
    
    # Формат [id123456|Имя] — стандартный ВК-формат упоминания
    bracket_match = re.match(r"\[(?:id|club|public)(\d+)\|[^\]]*\]", raw_mention, re.IGNORECASE)
    if bracket_match:
        return int(bracket_match.group(1))

    # Если это уже просто цифры
    if raw_mention.isdigit():
        return int(raw_mention)

    # Если это id123
    if raw_mention.lower().startswith("id") and raw_mention[2:].isdigit():
        return int(raw_mention[2:])

    # Убираем символ @ если есть, и пробуем резолвить через API как алиас
    clean = raw_mention.lstrip("@").strip()
    if not clean:
        return None
    try:
        users = await api.users.get(user_ids=[clean])
        if users:
            return users[0].id
    except Exception:
        pass
    return None


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
    for raw_mention, amount in pairs:
        # Валидация суммы тут
        if amount < config.MIN_TRANSACTION or amount > config.MAX_TRANSACTION:
            results.append(f"❌ Сумма {amount} вне диапазона ({config.MIN_TRANSACTION}–{config.MAX_TRANSACTION}).")
            continue

        target_id = await resolve_to_id(bp.api, raw_mention)
        if not target_id:
            results.append(f"⚠️ Не удалось распознать игрока: {raw_mention}")
            continue

        target_user = await database.get_user(target_id)
        if not target_user:
            results.append(f"⚠️ {raw_mention} (ID {target_id}) — не найден в банке.")
            continue
        try:
            new_balance = await database.change_balance(target_id, message.from_id, amount, reason)
            char = target_user.get("character_name", "Неизвестно")
            results.append(f"✅ {char}: +{utils.format_balance(amount)} → {utils.format_balance(new_balance)}")
        except ValueError as e:
            char = target_user.get("character_name", f"ID {target_id}")
            results.append(f"❌ {char}: {e}")
        except Exception as e:
            results.append(f"❌ ID {target_id}: ошибка — {e}")

    summary = "\n".join(results)
    flavor_text = f"\n\n💰 «{flavor.get_deposit_flavor()}»"
    await message.answer(f"📋 Результаты начисления (причина: {reason}):\n\n{summary}{flavor_text}")

# ─── /снять @user сумма причина (только для Банкира) ────────────────────────

@bp.on.message(text=[
    "/снять <mention> <amount:int> <reason>",
    "Снять <mention> <amount:int> <reason>"
])
@require_admin
async def admin_withdraw_handler(message: Message, mention: str, amount: int, reason: str, admin_data: dict):
    target_id = await resolve_to_id(bp.api, mention)
    if not target_id:
        await message.answer("❌ Не удалось распознать пользователя.")
        return

    if amount < config.MIN_TRANSACTION or amount > config.MAX_TRANSACTION:
        await message.answer(f"❌ Сумма должна быть от {config.MIN_TRANSACTION} до {config.MAX_TRANSACTION}.")
        return

    target_user = await database.get_user(target_id)
    if not target_user:
        await message.answer(f"❌ Пользователь (ID {target_id}) не найден в банке.")
        return

    try:
        new_balance = await database.change_balance(target_id, message.from_id, -amount, reason)
        char = target_user.get("character_name", "Неизвестно")
        await message.answer(
            f"🔻 Снято {utils.format_balance(amount)} у персонажа {char}.\n"
            f"💰 Остаток: {utils.format_balance(new_balance)}\n"
            f"📝 Причина: {reason}\n\n"
            f"💸 «{flavor.get_withdraw_flavor()}»"
        )
    except ValueError as e:
        await message.answer(f"❌ Операция отклонена: {e}")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

# ─── /история @user ──────────────────────────────────────────────────────────

@bp.on.message(text=["/история <mention>"])
@require_admin
async def admin_history_handler(message: Message, mention: str, admin_data: dict):
    target_id = await resolve_to_id(bp.api, mention)
    if not target_id:
        await message.answer("❌ Не удалось распознать пользователя.")
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
    target_id = await resolve_to_id(bp.api, mention)
    if not target_id:
        await message.answer("❌ Не удалось распознать пользователя.")
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
    target_id = await resolve_to_id(bp.api, mention)
    if not target_id:
        await message.answer("❌ Не удалось распознать пользователя.")
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
    target_id = await resolve_to_id(bp.api, mention)
    if not target_id:
        await message.answer("❌ Не удалось распознать пользователя.")
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
    target_id = await resolve_to_id(bp.api, mention)
    if not target_id:
        await message.answer("❌ Не удалось распознать пользователя.")
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
