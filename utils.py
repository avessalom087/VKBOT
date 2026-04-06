import config
import re
from datetime import datetime, timezone, timedelta

def format_balance(amount: int) -> str:
    return f"{amount:,} ft".replace(",", " ")

def extract_user_id(text: str) -> int:
    match = re.search(r"\[id(\d+)\|.*?\]", text)
    if match:
        return int(match.group(1))
    return None

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
    status = "Админ" if user.get("status") == "admin" else "Игрок"
    vk_id_str = str(user.get("vk_id")).ljust(9)
    name_str = user.get("vk_name", "Неизвестно")[:12].ljust(12)
    char_str = user.get("character_name", "Неизвестно")[:12].ljust(12)
    status_str = status.ljust(7)
    balance_str = format_balance(user.get("balance", 0)).rjust(8)
    
    return f"{index:2} │ {vk_id_str} │ {name_str} │ {char_str} │ {status_str} │ {balance_str}"

def generate_bank_table(users: list) -> str:
    lines = [
        f"╔══ 🏦 {config.BANK_NAME.upper()} ══════════════════╗",
        "",
        " #  │ VK ID     │ Имя в VK     │ Персонаж     │ Статус  │  Счёт  ",
        "────┼───────────┼──────────────┼──────────────┼─────────┼─────────"
    ]
    
    total_balance = 0
    for i, user in enumerate(users[:config.BANK_TOP_LIMIT], 1):
        lines.append(format_user_row(i, user))
        total_balance += user.get("balance", 0)
        
    lines.append("")
    lines.append(f"Всего игроков: {len(users)} | Всего в обороте: {format_balance(total_balance)} ft")
    
    return "\n".join(lines)

def format_transaction(tx: dict, viewer_id: int) -> str:
    amount = tx.get("amount", 0)
    sign = "+" if amount >= 0 else "-"
    abs_amount = abs(amount)
    
    time_utc = tx.get("timestamp")
    if time_utc:
        # Check if it's a timestamp object or a datetime
        # firestore normally returns a datetime object with tzinfo=UTC
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
    
    prefix = "🔸" if amount >= 0 else "🔻"
    
    lines = [
        f"{prefix} {sign}{format_balance(abs_amount)}",
        f"🕒 {time_str}",
        f"📝 {reason}",
        f"💰 Остаток: {balance_after}"
    ]
    
    if admin_id and admin_id != viewer_id:
        lines.append(f"👤 Адм. ID: {admin_id}")
        
    return "\n".join(lines)
