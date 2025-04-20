#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Telegram Bot与Web管理平台入口程序
"""
import os
import logging
import asyncio
import threading
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

def run_bot(token):
    """在单独的线程中运行Telegram Bot"""
    # 连接数据库和启动Bot
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    # 运行Bot
    bot = loop.run_until_complete(setup_bot(token))
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
        
        # 启动Web服务器
        await setup_web_server(None, web_host, web_port)
        
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