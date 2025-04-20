#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Telegram Bot与Web管理平台入口程序
"""
import os
import logging
import asyncio
import threading
import queue
from dotenv import load_dotenv
from app.bot.bot import setup_bot
from app.web.server import setup_web_server

# 加载环境变量
load_dotenv()

# 配置日志
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = os.getenv("LOG_FILE", "bot.log")
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# 用于跨线程通信的队列
bot_queue = queue.Queue()

def run_bot(token):
    """在单独的线程中运行Telegram Bot"""
    # 连接数据库和启动Bot
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    # 运行Bot
    bot = loop.run_until_complete(setup_bot(token))
    # 将bot实例放入队列，以便主线程可以获取它
    bot_queue.put(bot)
    # Bot会在setup_bot中自动启动polling
    loop.run_forever()

async def main():
    """启动Telegram Bot和Web服务器"""
    try:
        # 获取配置
        bot_token = os.getenv("BOT_TOKEN")
        web_host = os.getenv("WEB_HOST", "0.0.0.0")
        web_port = int(os.getenv("WEB_PORT", 7000))
        
        if not bot_token:
            logger.error("缺少BOT_TOKEN环境变量")
            return
        
        # 在单独的线程中启动Telegram Bot
        bot_thread = threading.Thread(
            target=run_bot, 
            args=(bot_token,),
            daemon=True
        )
        bot_thread.start()
        
        # 等待短暂时间让Bot初始化
        await asyncio.sleep(2)
        
        # 获取Bot实例
        try:
            bot = bot_queue.get(timeout=3)  # 等待最多3秒获取Bot实例
            logger.info("成功获取Bot实例，准备初始化Web服务器")
        except queue.Empty:
            logger.warning("无法获取Bot实例，Web服务器将使用API替代")
            bot = None
        
        # 启动Web服务器，传入Bot实例
        await setup_web_server(bot, web_host, web_port)
        
        # 保持程序运行
        logger.info(f"Telegram Bot和Web服务器已启动，Web地址: http://{web_host}:{web_port}")
        await asyncio.Event().wait()
        
    except Exception as e:
        logger.error(f"启动失败: {e}", exc_info=True)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("程序已手动停止")
    except Exception as e:
        logger.error(f"程序异常退出: {e}", exc_info=True) 