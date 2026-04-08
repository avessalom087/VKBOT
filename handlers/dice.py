import re
import random
import time
from vkbottle.bot import Blueprint, Message
import config

bp = Blueprint("DiceCommands")

last_rolls = {}

# Match examples: d20, d20+3, d20 - 1, d20+5 attack, d100 stealth
DICE_REGEX = re.compile(r"^d(\d+)(?:\s*([+-]\s*\d+))?(?:\s+(.+))?$", re.IGNORECASE)

@bp.on.message(text=["/roll", "/кинуть", "/roll <args>", "/кинуть <args>"])
async def roll_handler(message: Message, args: str = None):
    user_id = message.from_id
    
    # Cooldown check
    current_time = time.time()
    last_time = last_rolls.get(user_id, 0)
    if current_time - last_time < config.DICE_COOLDOWN:
        await message.answer("⏳ Подожди немного перед следующим броском.")
        return
        
    if not args:
        # User only typed /roll without arguments
        last_rolls[user_id] = current_time # still apply cooldown on errors
        await message.answer("❌ Укажите кубик для броска.\nПример: /roll d20 или /roll d20+3 атака\nПодробнее: /помощь дайсы")
        return

    args = args.strip()
    match = DICE_REGEX.match(args)
    
    if not match:
        last_rolls[user_id] = current_time
        await message.answer("❌ Неверный формат броска.\nПример: /roll d20+3 атака\nПодробнее: /помощь дайсы")
        return
        
    dice_type_str = match.group(1)
    modifier_str = match.group(2)
    label = match.group(3)
    
    try:
        dice_type = int(dice_type_str)
    except ValueError:
        last_rolls[user_id] = current_time
        await message.answer(f"❌ Неверный тип кубика. Разрешены: d{', d'.join(map(str, config.ALLOWED_DICE))}")
        return
        
    if dice_type not in config.ALLOWED_DICE:
        last_rolls[user_id] = current_time
        await message.answer(f"❌ Кубик d{dice_type} не поддерживается.\nРазрешены: d{', d'.join(map(str, config.ALLOWED_DICE))}")
        return
        
    modifier = 0
    if modifier_str:
        modifier = int(modifier_str.replace(" ", ""))
        
    if label:
        label = label.strip()
        if len(label) > config.MAX_DICE_LABEL_LEN:
            label = label[:config.MAX_DICE_LABEL_LEN] + "..."
            
    # Everything is valid, update cooldown
    last_rolls[user_id] = current_time
            
    # Roll logic
    roll_result = random.randint(1, dice_type)
    total = roll_result + modifier
    
    crit_msg = ""
    if roll_result == 1:
        crit_msg = "\n💀 **КРИТИЧЕСКИЙ ПРОВАЛ!** 💀"
    elif roll_result == dice_type:
        crit_msg = "\n✨ **КРИТИЧЕСКИЙ УСПЕХ!** ✨"
        
    vk_mention = f"@id{user_id}"
    
    mod_text = ""
    dice_display = f"d{dice_type}"
    
    if modifier > 0:
        mod_text = f"\n➕ Модификатор: **+{modifier}**"
        dice_display += f"+{modifier}"
    elif modifier < 0:
        mod_text = f"\n➖ Модификатор: **{modifier}**"
        dice_display += f"{modifier}"

    label_text = f"\n📝 *Подпись: {label}*" if label else ""

    text = (f"🎲 {vk_mention}, результат броска **{dice_display}**:\n"
            f"🎰 Выпало: **{roll_result}**{mod_text}\n"
            f"🏆 Итого: **{total}**{crit_msg}{label_text}")

    await message.answer(text, disable_mentions=False)

@bp.on.message(text=["/помощь дайсы", "/help dice", "помощь дайсы"])
async def help_dice_handler(message: Message):
    allowed = ", ".join(f"d{d}" for d in config.ALLOWED_DICE)
    text = (
        "🎲 ПОМОЩЬ ПО КУБИКАМ 🎲\n\n"
        f"Допустимые кубики: {allowed}\n\n"
        "Примеры команд:\n"
        "• /roll d20 — чистый бросок d20\n"
        "• /roll d20+3 — бросок с плюсом\n"
        "• /roll d8-1 — бросок с минусом\n"
        "• /кинуть d100 поиск — бросок с подписью\n\n"
        "ℹ️ Критические успехи и провалы (Нат 1 и Нат Макс) определяются по голому броску кубика до применения модификатора. Подпись обрезается до 50 символов."
    )
    await message.answer(text)
