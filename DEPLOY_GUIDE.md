# 🚀 Инструкция по деплою (Render.com)

Чтобы твой бот работал 24/7 бесплатно, выполни эти шаги.

## 1. Подготовка Firebase
1. Открой свой `.json` файл с ключами Firebase (тот, что лежит в папке проекта).
2. Скопируй **весь** текст внутри этого файла. Это понадобится для настройки переменных окружения.

---

## 2. Настройка на Render.com
1. Зарегистрируйся на [Render.com](https://render.com/) через GitHub (или просто создай аккаунт).
2. Нажми **New** → **Web Service**.
3. Подключи свой GitHub-репозиторий (или выбери "Public Git Repository" и вставь ссылку, если он публичный).
4. **Конфигурация**:
   - **Name**: `vk-bank-bot`
   - **Region**: `Frankfurt` (или любой другой)
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python bot.py`
5. Нажми **Advanced** → **Add Environment Variable** и добавь:
   - `VK_TOKEN`: [Твой токен из сообщества ВК]
   - `ADMIN_VK_ID`: [Твой числовой ID ВК]
   - `FIREBASE_CREDENTIALS`: [Вставь тот текст из JSON файла, который мы скопировали на шаге 1]
   - `PORT`: `10000`
6. Нажми **Create Web Service**.

---

## 3. Настройка UptimeRobot (Keep-Alive)
Бот на бесплатном тарифе Render "засыпает" через 15 минут бездействия. Чтобы этого не было:
1. Зарегистрируйся на [UptimeRobot.com](https://uptimerobot.com/).
2. Нажми **Add New Monitor**.
3. **Monitor Type**: `HTTP(s)`
4. **Friendly Name**: `VK Bank Bot`
5. **URL (or IP)**: `https://[название-твоего-сервиса].onrender.com/health`
6. **Monitoring Interval**: `5 minutes`.
7. Сохрани.

Теперь бот будет пинговаться каждые 5 минут и никогда не уснет.

---

## 🛠️ Если что-то пошло не так
- Проверь **Logs** на Render.com. Если там ошибка `FIREBASE_CREDENTIALS`, значит JSON вставлен не полностью или с ошибкой.
- Убедись, что в Сообществе ВК включены **Сообщения сообщества** и **Long Poll API** (вкладка "Работа с API").
