import os
import logging
import asyncio
from aiohttp import web
from vkbottle import Bot
import config

# Import blueprints
from handlers.player import bp as player_bp
from handlers.admin import bp as admin_bp
from handlers.dice import bp as dice_bp

logger = logging.getLogger("vkbot.main")

bot = Bot(token=config.VK_TOKEN)

# Register blueprints
for bp in [player_bp, admin_bp, dice_bp]:
    bp.load(bot)

# Health-check HTTP server for keep-alive (Render.com + UptimeRobot)
async def health_check(request):
    return web.json_response({"status": "ok"})

async def start_web_server():
    app = web.Application()
    app.add_routes([web.get('/health', health_check), web.get('/', health_check)])
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    
    logger.info(f"Starting health-check server on port {port}")
    await site.start()
    
    # We don't block here, the server runs in background
    return runner

async def main():
    logger.info("Starting VK Bot...")
    await bot.run_polling()

if __name__ == "__main__":
    # Add web server to startup tasks
    bot.loop_wrapper.on_startup.append(start_web_server())
    
    try:
        logger.info("Bot is starting...")
        bot.run_forever()
    except KeyboardInterrupt:
        logger.info("Bot manually stopped")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
