import config
import re
from datetime import datetime, timezone, timedelta

def format_balance(amount: int) -> str:
    return f"{amount:,} ft".replace(",", " ")

def get_currency_form(amount: int) -> str:
    n = abs(amount) % 100
    n1 = n % 10
    if n > 10 and n < 20: 
        return config.CURRENCY_FORMS[2]
    if n1 > 1 and n1 < 5: 
        return config.CURRENCY_FORMS[1]
    if n1 == 1: 
        return config.CURRENCY_FORMS[0]
    return config.CURRENCY_FORMS[2]

def format_user_row(index: int, user: dict) -> str:
    vk_id = user.get("vk_id")
    name = user.get("vk_name", "Неизвестно")
    char_name = user.get("character_name", "Неизвестно")
    balance = format_balance(user.get("balance", 0))
    
    return f"{index}. [id{vk_id}|{name}] ({char_name}) — {balance}"

def generate_bank_table(users: list) -> str:
    total_balance = sum(user.get("balance", 0) for user in users)
    
    lines = [
        f"🏛 {config.BANK_NAME.upper()} | ТОП-20",
        f"Участников: {len(users)} | Бюджет: {format_balance(total_balance)}",
        "------------------------------------"
    ]
    
    for i, user in enumerate(users[:config.BANK_TOP_LIMIT], 1):
        lines.append(format_user_row(i, user))
        
    return "\n".join(lines)

def format_transaction(tx: dict, viewer_id: int) -> str:
    amount = tx.get("amount", 0)
    sign = "+" if amount >= 0 else "-"
    abs_amount = abs(amount)
    
    time_utc = tx.get("timestamp")
    if time_utc:
        if hasattr(time_utc, 'astimezone'):
            tz = timezone(timedelta(hours=config.TIMEZONE_OFFSET))
            time_str = time_utc.astimezone(tz).strftime("%d.%m.%Y %H:%M")
        else:
            time_str = str(time_utc)
    else:
        time_str = "Неизвестно"
        
    reason = tx.get("reason", "Без причины")
    balance_after = format_balance(tx.get("balance_after", 0))
    admin_id = tx.get("admin_id")
    
    # Formatting without emojis
    line1 = f"{sign} {format_balance(abs_amount)} | Остаток: {balance_after}"
    line2 = f"Причина: {reason}"
    
    if admin_id and admin_id != viewer_id:
        line3 = f"{time_str} (Адм: @id{admin_id})"
    else:
        line3 = f"{time_str}"
        
    return f"{line1}\n{line2}\n{line3}"
