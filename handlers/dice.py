import re
import random
import time
from vkbottle.bot import Blueprint, Message
import config
import flavor

bp = Blueprint("DiceCommands")

last_rolls = {}

# Match examples: d20, 2d10, d20+3, 3d6 - 1, 2d20+5 attack
DICE_REGEX = re.compile(r"^(\d+)?d(\d+)(?:\s*([+-]\s*\d+))?(?:\s+(.+))?$", re.IGNORECASE)

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
        await message.answer("❌ Укажите кубик для броска.\nПример: /roll d20 или /roll 2d10+3 атака\nПодробнее: /помощь дайсы")
        return

    args = args.strip()
    match = DICE_REGEX.match(args)
    
    if not match:
        last_rolls[user_id] = current_time
        await message.answer("❌ Неверный формат броска.\nПример: /roll 2d10+3 атака\nПодробнее: /помощь дайсы")
        return
        
    count_str = match.group(1)
    dice_type_str = match.group(2)
    modifier_str = match.group(3)
    label = match.group(4)
    
    count = 1
    if count_str:
        count = int(count_str)
        if count < 1:
            count = 1
        if count > getattr(config, 'MAX_DICE_COUNT', 10):
            last_rolls[user_id] = current_time
            await message.answer(f"❌ Слишком много кубиков. Максимум за раз: {getattr(config, 'MAX_DICE_COUNT', 10)}")
            return
            
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
    rolls = [random.randint(1, dice_type) for _ in range(count)]
    total = sum(rolls) + modifier
        
    # Пытаемся получить имя пользователя или его кастомный никнейм для красивого упоминания
    try:
        users_info = await bp.api.users.get(user_ids=[user_id], fields=["screen_name"])
        if users_info:
            user = users_info[0]
            # Если есть красивый никнейм (@aves_087), используем его, иначе просто Имя
            if user.screen_name and not user.screen_name.startswith("id"):
                name_display = f"@{user.screen_name}"
            else:
                name_display = user.first_name
            vk_mention = f"[id{user_id}|{name_display}]"
        else:
            vk_mention = f"@id{user_id}"
    except Exception:
        vk_mention = f"@id{user_id}"
    
    dice_display = f"{count}d{dice_type}" if count > 1 else f"d{dice_type}"
    mod_str = ""
    if modifier > 0:
        mod_str = f"+{modifier}"
    elif modifier < 0:
        mod_str = f"{modifier}"

    full_dice_display = f"{dice_display}{mod_str}"
    label_text = f" ({label})" if label else ""

    vypalo_str = str(rolls[0]) if count == 1 else f"[{', '.join(map(str, rolls))}]"
            
    text_lines = [f"🎲 {vk_mention}, результат броска {full_dice_display}{label_text}:"]
    text_lines.append(f"🎰 Выпало: {vypalo_str}")
    
    if modifier != 0:
        mod_icon = "➕" if modifier > 0 else "➖"
        text_lines.append(f"{mod_icon} Модификатор: {mod_str}")
        
    crit_msg = ""
    crit_flavor = ""
    if count == 1:
        if rolls[0] == 1:
            crit_msg = " 💀 (КРИТИЧЕСКИЙ ПРОВАЛ!)"
            crit_flavor = f"\n\n💀 «{flavor.get_crit_fail_flavor()}»"
        elif rolls[0] == dice_type:
            crit_msg = " ✨ (КРИТИЧЕСКИЙ УСПЕХ!)"
            crit_flavor = f"\n\n🎲 «{flavor.get_crit_success_flavor()}»"

    text_lines.append(f"🏆 Итого: {total}{crit_msg}{crit_flavor}")
    
    text = "\n".join(text_lines)

    await message.answer(text, disable_mentions=False)

@bp.on.message(text=["/помощь дайсы", "/help dice", "помощь дайсы"])
async def help_dice_handler(message: Message):
    allowed = ", ".join(f"d{d}" for d in config.ALLOWED_DICE)
    text = (
        "🎲 ПОМОЩЬ ПО КУБИКАМ 🎲\n\n"
        f"Допустимые кубики: {allowed}\n\n"
        "Примеры команд:\n"
        "• /roll d20 — одиночный бросок\n"
        "• /roll 2d10 — бросок двух кубиков d10\n"
        "• /roll 3d6+3 — три кубика с плюсом\n"
        "• /roll d100 [подпись] — бросок с подписью\n\n"
        "ℹ️ Критические успехи и провалы срабатывают только при броске одного кубика (Нат 1 и Нат Макс до применения модов).\n"
        f"Максимальное количество кубиков за один раз: {getattr(config, 'MAX_DICE_COUNT', 10)}"
    )
    await message.answer(text)
