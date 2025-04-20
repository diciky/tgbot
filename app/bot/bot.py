#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Telegram Bot主模块
"""
import os
import logging
import asyncio
import json
import re
import requests
import threading
from io import BytesIO
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')
import seaborn as sns
import pandas as pd
from typing import List, Dict, Any, Union, Optional, Tuple
from datetime import datetime, timedelta
from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions, ParseMode
from telegram.ext import Updater, CommandHandler, MessageHandler, CallbackQueryHandler, CallbackContext
from telegram.ext import Filters
from telegraph import Telegraph
from app.models.database import connect_to_mongodb, close_mongodb_connection, get_collection
from app.models.user import (
    create_user, get_user, update_user, update_user_points_sync, 
    get_top_users_by_points
)
from app.models.message import save_message, get_user_messages, get_group_messages
from app.models.group import get_group_sync, update_group_sync

logger = logging.getLogger(__name__)

# 从环境变量获取管理员ID
admin_ids_str = os.getenv("ADMIN_IDS", "")
# 移除可能的注释
if '#' in admin_ids_str:
    admin_ids_str = admin_ids_str.split('#')[0].strip()
ADMIN_IDS = [int(admin_id.strip()) for admin_id in admin_ids_str.split(",") if admin_id.strip()]
# 自动删除消息配置
AUTO_DELETE_MESSAGES = os.getenv("AUTO_DELETE_MESSAGES", "true").lower() == "true"
AUTO_DELETE_INTERVAL = int(os.getenv("AUTO_DELETE_INTERVAL", 30))

# 全局Bot实例
_bot = None

async def setup_bot(token: str) -> Bot:
    """设置并启动Telegram Bot"""
    global _bot
    
    # 连接数据库
    await connect_to_mongodb()
    
    # 创建应用实例
    updater = Updater(token=token, use_context=True)
    
    # 获取调度器和Bot实例
    dispatcher = updater.dispatcher
    _bot = updater.bot
    
    # 注册命令处理器
    dispatcher.add_handler(CommandHandler("start", start_command))
    dispatcher.add_handler(CommandHandler("help", help_command))
    dispatcher.add_handler(CommandHandler("stats", stats_command))
    dispatcher.add_handler(CommandHandler("admin", admin_command))
    
    # 添加新命令
    dispatcher.add_handler(CommandHandler("web", web_command))
    dispatcher.add_handler(CommandHandler("qd", checkin_command))
    dispatcher.add_handler(CommandHandler("zt", user_info_command))
    dispatcher.add_handler(CommandHandler("fy", translate_command))
    dispatcher.add_handler(CommandHandler("jf", points_command))
    dispatcher.add_handler(CommandHandler("ban", ban_command))
    dispatcher.add_handler(CommandHandler("jy", mute_command))
    dispatcher.add_handler(CommandHandler("tu", heatmap_command))
    dispatcher.add_handler(CommandHandler("jfxx", points_detail_command))
    
    # 注册消息处理器
    dispatcher.add_handler(MessageHandler(Filters.text & (~Filters.command), handle_message))
    dispatcher.add_handler(MessageHandler(Filters.photo, handle_photo))
    dispatcher.add_handler(MessageHandler(Filters.document, handle_document))
    
    # 添加新成员和成员离开消息处理器
    dispatcher.add_handler(MessageHandler(Filters.status_update.new_chat_members, handle_new_chat_members))
    dispatcher.add_handler(MessageHandler(Filters.status_update.left_chat_member, handle_left_chat_member))
    
    # 注册回调查询处理器
    dispatcher.add_handler(CallbackQueryHandler(handle_callback_query))
    
    # 注册错误处理器
    dispatcher.add_error_handler(error_handler)
    
    # 启动Bot
    updater.start_polling()
    
    logger.info("Telegram Bot已启动")
    return _bot

def is_command_for_me(update: Update, context: CallbackContext) -> bool:
    """检查命令是否直接针对本机器人
    
    例如，如果机器人用户名是 mybot:
    - /command@mybot 是针对本机器人的命令
    - /command 在私聊中是针对本机器人的命令
    - /command 在群组中不确定是针对哪个机器人，除非设置了默认机器人
    """
    if not update.message or not update.message.text:
        return False
    
    # 检查是否是命令
    if not update.message.text.startswith('/'):
        return False
    
    # 在私聊中，所有命令都是给当前机器人的
    if update.effective_chat.type == "private":
        return True
    
    # 在群组中，检查命令是否明确标记给本机器人
    if context.bot.username:
        # 分割命令，检查是否有@username部分
        command_parts = update.message.text.split('@', 1)
        if len(command_parts) > 1:
            # 如果有@部分，检查是否是给本机器人的
            return command_parts[1].strip() == context.bot.username
        
        # 如果没有@部分，在群组中我们不确定命令是否针对本机器人
        # 可以根据群组设置进行判断，比如检查机器人是否是群组的默认机器人
        return False
    
    return False
    
def start_command(update: Update, context: CallbackContext) -> None:
    """处理/start命令"""
    user = update.effective_user
    
    # 保存用户信息到数据库
    user_data = {
        "user_id": user.id,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "is_admin": user.id in ADMIN_IDS,
        "is_bot": user.is_bot,
        "language_code": user.language_code
    }
    # 同步方式创建用户
    collection = get_collection("users")
    collection.update_one(
        {"user_id": user.id},
        {"$set": user_data},
        upsert=True
    )
    
    # 构建欢迎消息
    keyboard = [
        [
            InlineKeyboardButton("帮助", callback_data="help"),
            InlineKeyboardButton("统计", callback_data="stats")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message = update.message.reply_text(
        f"你好，{user.first_name}！欢迎使用Telegram Bot。\n"
        f"你可以使用 /help 命令获取帮助。",
        reply_markup=reply_markup
    )
    
    # 保存消息
    save_message_to_db_sync(update, "text", message.text)
    
    # 自动删除机器人的回复消息
    if AUTO_DELETE_MESSAGES:
        auto_delete_message_sync(update.effective_chat.id, message.message_id)
        
        # 只在私聊或命令明确针对本机器人时才删除用户的原始消息
        if update.effective_chat.type == "private" or is_command_for_me(update, context):
            auto_delete_message_sync(update.effective_chat.id, update.message.message_id)

def help_command(update: Update, context: CallbackContext) -> None:
    """处理/help命令"""
    chat_title = update.effective_chat.title if update.effective_chat.title else "私聊"
    
    help_text = (
        f"📱 *{chat_title} - 机器人指令帮助*\n\n"
        
        f"🔹 *通用指令*\n"
        f"/start - 开始使用机器人\n"
        f"/help - 显示帮助信息\n"
        f"/web - 网页转Telegraph链接，格式：/web [URL]\n"
        f"/qd - 每日签到，获取积分\n"
        f"/zt - 查看个人信息\n"
        f"/fy - 翻译功能，格式：/fy [语言代码] [文本]\n"
        f"      例如：/fy en 你好，/fy zh hello\n"
        f"/tu - 聊天热力图，参数：d(日)、m(月)、y(年)\n"
        f"      例如：/tu d\n"
    )
    
    # 如果是管理员，添加管理员命令
    user = update.effective_user
    if user.id in ADMIN_IDS:
        help_text += (
            f"\n🔸 *管理员指令*\n"
            f"/admin - 访问管理员功能\n"
            f"/jf - 积分排行榜，或查看指定用户积分\n"
            f"      格式：/jf 或 /jf @用户名\n"
            f"/jfxx - 查看积分详情\n"
            f"      格式：/jfxx 或 /jfxx @用户名\n"
            f"/ban - 踢出用户，格式：/ban @用户名\n"
            f"/jy - 禁言用户，格式：/jy @用户名\n"
            f"/stats - 显示统计信息\n"
        )
    
    message = update.message.reply_text(
        help_text,
        parse_mode=ParseMode.MARKDOWN
    )
    
    # 保存消息
    save_message_to_db_sync(update, "text", message.text)
    
    # 自动删除机器人的回复消息
    if AUTO_DELETE_MESSAGES:
        auto_delete_message_sync(update.effective_chat.id, message.message_id)
        
        # 只在私聊或命令明确针对本机器人时才删除用户的原始消息
        if update.effective_chat.type == "private" or is_command_for_me(update, context):
            auto_delete_message_sync(update.effective_chat.id, update.message.message_id)

def stats_command(update: Update, context: CallbackContext) -> None:
    """处理/stats命令"""
    # 这里应该从数据库获取统计信息
    stats_text = "Bot统计信息：\n(这里将显示从数据库获取的统计数据)"
    
    message = update.message.reply_text(stats_text)
    
    # 保存消息
    save_message_to_db_sync(update, "text", message.text)
    
    # 自动删除机器人的回复消息
    if AUTO_DELETE_MESSAGES:
        auto_delete_message_sync(update.effective_chat.id, message.message_id)
        
        # 只在私聊或命令明确针对本机器人时才删除用户的原始消息
        if update.effective_chat.type == "private" or is_command_for_me(update, context):
            auto_delete_message_sync(update.effective_chat.id, update.message.message_id)

def admin_command(update: Update, context: CallbackContext) -> None:
    """处理/admin命令 - 仅管理员可用"""
    user = update.effective_user
    
    if user.id not in ADMIN_IDS:
        message = update.message.reply_text("抱歉，只有管理员才能使用此命令。")
        # 自动删除消息
        if AUTO_DELETE_MESSAGES:
            auto_delete_message_sync(update.effective_chat.id, message.message_id)
        return
    
    # 构建管理菜单
    keyboard = [
        [
            InlineKeyboardButton("网页管理后台", url=f"http://{os.getenv('WEB_HOST', '0.0.0.0')}:{os.getenv('WEB_PORT', 7000)}")
        ],
        [
            InlineKeyboardButton("用户管理", callback_data="admin_users"),
            InlineKeyboardButton("消息管理", callback_data="admin_messages")
        ],
        [
            InlineKeyboardButton("设置", callback_data="admin_settings")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message = update.message.reply_text(
        "管理员控制面板：",
        reply_markup=reply_markup
    )
    
    # 保存消息
    save_message_to_db_sync(update, "text", message.text)

def handle_message(update: Update, context: CallbackContext) -> None:
    """处理文本消息"""
    # 更新用户活动状态
    user = update.effective_user
    update_user_sync(user.id, {"last_activity": datetime.now()})
    
    # 保存消息到数据库
    save_message_to_db_sync(update, "text", update.message.text)
    
    # 检查是否是和机器人的直接对话
    is_private_chat = update.effective_chat.type == "private"
    contains_bot_mention = False
    
    # 检查是否提到了机器人
    if update.message.text and context.bot.username:
        if f"@{context.bot.username}" in update.message.text:
            contains_bot_mention = True
    
    # 只有在私聊或者消息中提到机器人的情况下才回复
    if is_private_chat or contains_bot_mention:
        # 简单的回复
        message = update.message.reply_text(f"收到你的消息: {update.message.text}")
        
        # 仅删除机器人自己的回复消息
        if AUTO_DELETE_MESSAGES:
            auto_delete_message_sync(update.effective_chat.id, message.message_id)
            
            # 在群组中，只有当提到机器人时才删除用户的原始消息
            if contains_bot_mention and not is_private_chat:
                auto_delete_message_sync(update.effective_chat.id, update.message.message_id)

def handle_photo(update: Update, context: CallbackContext) -> None:
    """处理图片消息"""
    # 更新用户活动状态
    user = update.effective_user
    update_user_sync(user.id, {"last_activity": datetime.now()})
    
    # 获取图片信息
    photo = update.message.photo[-1]  # 获取最大尺寸的图片
    file_id = photo.file_id
    
    # 保存消息到数据库
    save_message_to_db_sync(update, "photo", None, file_id=file_id)
    
    # 检查是否是和机器人的直接对话
    is_private_chat = update.effective_chat.type == "private"
    contains_bot_mention = False
    
    # 检查是否提到了机器人
    if update.message.caption and context.bot.username:
        if f"@{context.bot.username}" in update.message.caption:
            contains_bot_mention = True
    
    # 只有在私聊或者消息中提到机器人的情况下才回复
    if is_private_chat or contains_bot_mention:
        # 回复消息
        message = update.message.reply_text("收到你的图片")
        
        # 仅删除机器人自己的回复消息
        if AUTO_DELETE_MESSAGES:
            auto_delete_message_sync(update.effective_chat.id, message.message_id)
            
            # 在群组中，只有当提到机器人时才删除用户的原始消息
            if contains_bot_mention and not is_private_chat:
                auto_delete_message_sync(update.effective_chat.id, update.message.message_id)

def handle_document(update: Update, context: CallbackContext) -> None:
    """处理文档消息"""
    # 更新用户活动状态
    user = update.effective_user
    update_user_sync(user.id, {"last_activity": datetime.now()})
    
    # 获取文档信息
    document = update.message.document
    file_id = document.file_id
    file_name = document.file_name
    
    # 保存消息到数据库
    save_message_to_db_sync(
        update, 
        "document", 
        None, 
        file_id=file_id, 
        content={"file_name": file_name}
    )
    
    # 检查是否是和机器人的直接对话
    is_private_chat = update.effective_chat.type == "private"
    contains_bot_mention = False
    
    # 检查是否提到了机器人
    if update.message.caption and context.bot.username:
        if f"@{context.bot.username}" in update.message.caption:
            contains_bot_mention = True
    
    # 只有在私聊或者消息中提到机器人的情况下才回复
    if is_private_chat or contains_bot_mention:
        # 回复消息
        message = update.message.reply_text(f"收到你的文档: {file_name}")
        
        # 仅删除机器人自己的回复消息
        if AUTO_DELETE_MESSAGES:
            auto_delete_message_sync(update.effective_chat.id, message.message_id)
            
            # 在群组中，只有当提到机器人时才删除用户的原始消息
            if contains_bot_mention and not is_private_chat:
                auto_delete_message_sync(update.effective_chat.id, update.message.message_id)

def handle_callback_query(update: Update, context: CallbackContext) -> None:
    """处理按钮回调查询"""
    query = update.callback_query
    query.answer()
    
    # 根据回调数据处理不同的操作
    if query.data == "help":
        query.edit_message_text(text="这里是帮助信息...")
    elif query.data == "stats":
        query.edit_message_text(text="这里是统计信息...")
    elif query.data.startswith("admin_"):
        # 处理管理员操作
        if query.from_user.id not in ADMIN_IDS:
            query.edit_message_text(text="抱歉，只有管理员才能执行此操作。")
            return
        
        if query.data == "admin_users":
            query.edit_message_text(text="用户管理功能...")
        elif query.data == "admin_messages":
            query.edit_message_text(text="消息管理功能...")
        elif query.data == "admin_settings":
            query.edit_message_text(text="设置功能...")

def error_handler(update: object, context: CallbackContext) -> None:
    """处理错误"""
    logger.error(f"更新 {update} 导致错误 {context.error}")

def save_message_to_db_sync(
    update: Update, 
    message_type: str, 
    text: str = None, 
    file_id: str = None, 
    content: Dict = None
) -> None:
    """同步方式保存消息到数据库"""
    try:
        if not update or not update.effective_message:
            return
        
        message = update.effective_message
        user = update.effective_user
        chat = update.effective_chat
        
        # 创建消息数据
        message_data = {
            "message_id": message.message_id,
            "chat_id": chat.id,
            "user_id": user.id if user else None,
            "text": text or message.text,
            "date": datetime.now(),
            "message_type": message_type,
            "file_id": file_id,
            "content": content or {}
        }
        
        # 保存消息
        collection = get_collection("messages")
        collection.insert_one(message_data)
    except Exception as e:
        logger.error(f"保存消息到数据库时出错: {e}")

def update_user_sync(user_id: int, update_data: Dict) -> None:
    """同步方式更新用户数据"""
    try:
        collection = get_collection("users")
        collection.update_one(
            {"user_id": user_id},
            {"$set": update_data}
        )
    except Exception as e:
        logger.error(f"更新用户数据时出错: {e}")

def should_delete_message(update: Update, context: CallbackContext) -> bool:
    """判断消息是否应该被自动删除
    规则：
    1. 私聊中的消息总是可以删除
    2. 群组中只有明确针对本机器人的命令和回复可以删除
    3. 群组中普通聊天不删除
    """
    if not AUTO_DELETE_MESSAGES:
        return False
    
    # 检查是否是私聊
    if update.effective_chat.type == "private":
        return True
    
    # 检查是否是命令，且命令是针对本机器人
    if is_command_for_me(update, context):
        return True
    
    # 检查是否明确提到了机器人
    if update.message:
        if update.message.text and context.bot.username and f"@{context.bot.username}" in update.message.text:
            return True
        if update.message.caption and context.bot.username and f"@{context.bot.username}" in update.message.caption:
            return True
    
    # 其他情况不删除
    return False

def auto_delete_message_sync(chat_id: int, message_id: int) -> None:
    """同步方式自动删除消息"""
    if not AUTO_DELETE_MESSAGES or not _bot:
        return
    
    try:
        # 创建一个新线程来处理延迟删除
        def delayed_delete():
            import time
            time.sleep(AUTO_DELETE_INTERVAL)
            try:
                # 使用同步方式删除消息
                _bot.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.error(f"删除消息时出错: {e}")
        
        # 启动线程
        threading_thread = threading.Thread(target=delayed_delete)
        threading_thread.daemon = True
        threading_thread.start()
        
    except Exception as e:
        logger.error(f"自动删除消息时出错: {e}")

def web_command(update: Update, context: CallbackContext) -> None:
    """处理/web命令 - 网页转Telegraph"""
    user = update.effective_user
    
    # 保存用户活动
    update_user_sync(user.id, {"last_activity": datetime.now()})
    
    # 检查参数
    if not context.args or len(context.args) < 1:
        message = update.message.reply_text(
            "请提供一个网页链接，例如：\n/web https://example.com"
        )
        if AUTO_DELETE_MESSAGES:
            auto_delete_message_sync(update.effective_chat.id, message.message_id)
        return
    
    url = context.args[0]
    
    # 验证URL格式
    if not url.startswith("http://") and not url.startswith("https://"):
        message = update.message.reply_text("请提供有效的URL链接，必须以http://或https://开头")
        if AUTO_DELETE_MESSAGES:
            auto_delete_message_sync(update.effective_chat.id, message.message_id)
        return
    
    try:
        # 获取网页内容
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        # 初始化Telegraph
        telegraph = Telegraph()
        telegraph.create_account(short_name='TelegramBot')
        
        # 提取标题
        title_match = re.search(r'<title>(.*?)</title>', response.text, re.IGNORECASE)
        title = title_match.group(1) if title_match else "网页内容"
        
        # 创建Telegraph页面
        response = telegraph.create_page(
            title=title,
            html_content=f'<p>原始链接：<a href="{url}">{url}</a></p><hr>{response.text}',
            author_name=user.username or user.first_name
        )
        
        telegraph_url = f"https://telegra.ph/{response['path']}"
        
        # 回复Telegraph链接
        message = update.message.reply_text(
            f"网页已转换为Telegraph链接:\n{telegraph_url}",
            disable_web_page_preview=False
        )
        
        # 记录积分
        update_user_points_sync(
            user.id, 
            2, 
            "web_command", 
            f"使用网页转Telegraph功能: {url}"
        )
        
        # 保存消息记录
        save_message_to_db_sync(update, "text", message.text)
        
        if AUTO_DELETE_MESSAGES:
            auto_delete_message_sync(update.effective_chat.id, message.message_id)
    
    except Exception as e:
        logger.error(f"网页转Telegraph失败: {e}", exc_info=True)
        message = update.message.reply_text(f"转换失败: {str(e)}")
        if AUTO_DELETE_MESSAGES:
            auto_delete_message_sync(update.effective_chat.id, message.message_id)

def user_info_command(update: Update, context: CallbackContext) -> None:
    """处理/zt命令 - 显示用户个人信息"""
    user = update.effective_user
    user_id = user.id
    
    # 获取用户数据 - 使用同步方式
    collection = get_collection("users")
    user_data = collection.find_one({"user_id": user_id})
    if not user_data:
        message = update.message.reply_text("未找到你的用户数据")
        if AUTO_DELETE_MESSAGES:
            auto_delete_message_sync(update.effective_chat.id, message.message_id)
        return
    
    # 获取用户消息统计 - 使用同步方式
    collection = get_collection("messages")
    cursor = collection.find({"user_id": user_id}).sort("date", -1).limit(100)
    messages = list(cursor)
    message_count = len(messages)
    
    # 构建用户信息文本
    points = user_data.get("points", 0)
    last_activity = user_data.get("last_activity", datetime.now())
    join_date = user_data.get("created_at", datetime.now())
    settings = user_data.get("settings", {})
    checkin_streak = settings.get("checkin_streak", 0)
    
    info_text = (
        f"*个人信息*\n"
        f"👤 用户: {user.first_name} {user.last_name or ''}\n"
        f"🆔 ID: `{user.id}`\n"
        f"💰 积分: {points}\n"
        f"📊 发送消息: {message_count}条\n"
        f"📅 加入时间: {join_date.strftime('%Y-%m-%d')}\n"
        f"🔄 连续签到: {checkin_streak}天\n"
        f"⏱ 上次活动: {last_activity.strftime('%Y-%m-%d %H:%M:%S')}\n"
    )
    
    # 发送用户信息
    message = update.message.reply_text(
        info_text,
        parse_mode=ParseMode.MARKDOWN
    )
    
    # 保存消息记录
    save_message_to_db_sync(update, "text", message.text)
    
    if AUTO_DELETE_MESSAGES:
        auto_delete_message_sync(update.effective_chat.id, message.message_id)

def translate_command(update: Update, context: CallbackContext) -> None:
    """处理/fy命令 - 翻译功能"""
    user = update.effective_user
    
    # 检查参数
    if not context.args or len(context.args) < 2:
        message = update.message.reply_text(
            "翻译格式: /fy [目标语言] [文本]\n例如:\n/fy en 你好\n/fy zh hello"
        )
        if AUTO_DELETE_MESSAGES:
            auto_delete_message_sync(update.effective_chat.id, message.message_id)
        return
    
    target_lang = context.args[0].lower()
    text_to_translate = " ".join(context.args[1:])
    
    # 语言代码映射
    lang_map = {
        "en": "英语",
        "zh": "中文", 
        "ch": "中文",
        "jp": "日语",
        "fr": "法语",
        "de": "德语",
        "es": "西班牙语",
        "it": "意大利语",
        "ru": "俄语",
        "ko": "韩语"
    }
    
    # 转换简化的语言代码
    if target_lang == "ch":
        target_lang = "zh"
    
    # 检查目标语言
    if target_lang not in lang_map:
        message = update.message.reply_text(
            f"不支持的目标语言: {target_lang}\n"
            f"支持的语言代码: {', '.join(lang_map.keys())}"
        )
        if AUTO_DELETE_MESSAGES:
            auto_delete_message_sync(update.effective_chat.id, message.message_id)
        return
    
    # 尝试使用Ollama进行翻译
    ollama_url = os.getenv("OLLAMA_API_URL", "")
    ollama_model = os.getenv("OLLAMA_MODEL", "")
    
    try:
        if ollama_url and ollama_model:
            # 使用Ollama API翻译
            prompt = f"将以下文本翻译成{lang_map[target_lang]}，不要添加解释，只返回翻译结果:\n{text_to_translate}"
            
            response = requests.post(
                f"{ollama_url}/api/generate",
                json={
                    "model": ollama_model,
                    "prompt": prompt,
                    "stream": False
                },
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                translated_text = result.get("response", "").strip()
                
                message = update.message.reply_text(
                    f"原文: {text_to_translate}\n"
                    f"译文({lang_map[target_lang]}): {translated_text}"
                )
                
                # 更新积分
                update_user_points_sync(
                    user.id, 
                    2, 
                    "translate", 
                    f"使用翻译功能: {target_lang}"
                )
                
                # 保存消息记录
                save_message_to_db_sync(update, "text", message.text)
                
                if AUTO_DELETE_MESSAGES:
                    auto_delete_message_sync(update.effective_chat.id, message.message_id)
                return
        
        # 如果Ollama不可用或失败，使用公共翻译API
        # 这里可以替换为其他翻译API
        message = update.message.reply_text(
            "翻译API暂不可用，请稍后再试"
        )
        if AUTO_DELETE_MESSAGES:
            auto_delete_message_sync(update.effective_chat.id, message.message_id)
        
    except Exception as e:
        logger.error(f"翻译失败: {e}", exc_info=True)
        message = update.message.reply_text(f"翻译失败: {str(e)}")
        if AUTO_DELETE_MESSAGES:
            auto_delete_message_sync(update.effective_chat.id, message.message_id)

def points_command(update: Update, context: CallbackContext) -> None:
    """处理/jf命令 - 积分排行"""
    user = update.effective_user
    
    # 检查参数
    if context.args and len(context.args) > 0:
        # 查询指定用户的积分
        target_username = context.args[0].replace("@", "")
        
        # 尝试获取用户数据 - 使用同步方式
        collection = get_collection("users")
        user_data = collection.find_one({"username": target_username})
        
        if not user_data:
            message = update.message.reply_text(f"未找到用户 @{target_username}")
            if AUTO_DELETE_MESSAGES:
                auto_delete_message_sync(update.effective_chat.id, message.message_id)
            return
        
        # 显示用户积分
        message = update.message.reply_text(
            f"用户 @{target_username} 的积分: {user_data.get('points', 0)}分"
        )
        
        # 保存消息记录
        save_message_to_db_sync(update, "text", message.text)
        
        if AUTO_DELETE_MESSAGES:
            auto_delete_message_sync(update.effective_chat.id, message.message_id)
        return
    
    # 显示积分排行榜 - 使用同步方式
    collection = get_collection("users")
    cursor = collection.find().sort("points", -1).limit(10)
    top_users = list(cursor)
    
    if not top_users:
        message = update.message.reply_text("暂无积分数据")
        if AUTO_DELETE_MESSAGES:
            auto_delete_message_sync(update.effective_chat.id, message.message_id)
        return
    
    # 构建排行榜文本
    rank_text = "*📊 积分排行榜 TOP 10*\n\n"
    
    for i, user_data in enumerate(top_users):
        username = user_data.get("username", "无用户名")
        first_name = user_data.get("first_name", "")
        points = user_data.get("points", 0)
        
        if i == 0:
            rank_emoji = "🥇"
        elif i == 1:
            rank_emoji = "🥈"
        elif i == 2:
            rank_emoji = "🥉"
        else:
            rank_emoji = f"{i+1}."
        
        rank_text += f"{rank_emoji} @{username} - {points}分\n"
    
    # 发送积分排行榜
    message = update.message.reply_text(
        rank_text,
        parse_mode=ParseMode.MARKDOWN
    )
    
    # 保存消息记录
    save_message_to_db_sync(update, "text", message.text)
    
    if AUTO_DELETE_MESSAGES:
        auto_delete_message_sync(update.effective_chat.id, message.message_id)

def ban_command(update: Update, context: CallbackContext) -> None:
    """处理/ban命令 - 踢人"""
    user = update.effective_user
    
    # 检查是否有管理员权限
    if user.id not in ADMIN_IDS:
        message = update.message.reply_text("你没有权限执行此命令")
        if AUTO_DELETE_MESSAGES:
            auto_delete_message_sync(update.effective_chat.id, message.message_id)
        return
    
    # 检查参数
    if not context.args or len(context.args) < 1:
        message = update.message.reply_text("请提供要踢出的用户名，例如：/ban @username")
        if AUTO_DELETE_MESSAGES:
            auto_delete_message_sync(update.effective_chat.id, message.message_id)
        return
    
    # 获取目标用户名
    target_username = context.args[0].lstrip('@')
    
    try:
        # 获取目标用户ID
        collection = get_collection("users")
        user_data = collection.find_one({"username": target_username})
        
        if not user_data:
            message = update.message.reply_text(f"未找到用户 @{target_username}")
            if AUTO_DELETE_MESSAGES:
                auto_delete_message_sync(update.effective_chat.id, message.message_id)
            return
        
        target_user_id = user_data.get("user_id")
        
        # 踢出用户
        _bot.ban_chat_member(
            chat_id=update.effective_chat.id,
            user_id=target_user_id
        )
        
        # 标记用户为已封禁
        update_user(target_user_id, {"is_banned": True})
        
        # 发送成功消息
        message = update.message.reply_text(f"已成功将 @{target_username} 踢出群组")
        
        # 保存消息记录
        save_message_to_db_sync(update, "text", message.text)
        
        if AUTO_DELETE_MESSAGES:
            auto_delete_message_sync(update.effective_chat.id, message.message_id)
    
    except Exception as e:
        logger.error(f"踢人失败: {e}", exc_info=True)
        message = update.message.reply_text(f"操作失败: {str(e)}")
        if AUTO_DELETE_MESSAGES:
            auto_delete_message_sync(update.effective_chat.id, message.message_id)

def mute_command(update: Update, context: CallbackContext) -> None:
    """处理/jy命令 - 禁言"""
    user = update.effective_user
    
    # 检查是否有管理员权限
    if user.id not in ADMIN_IDS:
        message = update.message.reply_text("你没有权限执行此命令")
        if AUTO_DELETE_MESSAGES:
            auto_delete_message_sync(update.effective_chat.id, message.message_id)
        return
    
    # 检查参数
    if not context.args or len(context.args) < 1:
        message = update.message.reply_text("请提供要禁言的用户名，例如：/jy @username")
        if AUTO_DELETE_MESSAGES:
            auto_delete_message_sync(update.effective_chat.id, message.message_id)
        return
    
    # 获取目标用户名
    target_username = context.args[0].lstrip('@')
    
    try:
        # 获取目标用户ID
        collection = get_collection("users")
        user_data = collection.find_one({"username": target_username})
        
        if not user_data:
            message = update.message.reply_text(f"未找到用户 @{target_username}")
            if AUTO_DELETE_MESSAGES:
                auto_delete_message_sync(update.effective_chat.id, message.message_id)
            return
        
        target_user_id = user_data.get("user_id")
        
        # 默认禁言时间（1小时）
        mute_duration = 3600
        mute_until = datetime.now() + timedelta(seconds=mute_duration)
        
        # 禁言用户
        permissions = ChatPermissions(
            can_send_messages=False,
            can_send_media_messages=False,
            can_send_polls=False,
            can_send_other_messages=False,
            can_add_web_page_previews=False,
            can_change_info=False,
            can_invite_users=False,
            can_pin_messages=False
        )
        
        _bot.restrict_chat_member(
            chat_id=update.effective_chat.id,
            user_id=target_user_id,
            permissions=permissions,
            until_date=mute_until
        )
        
        # 标记用户为已禁言
        update_user(target_user_id, {
            "is_muted": True,
            "muted_until": mute_until
        })
        
        # 发送成功消息
        message = update.message.reply_text(
            f"已成功禁言 @{target_username} 1小时"
        )
        
        # 保存消息记录
        save_message_to_db_sync(update, "text", message.text)
        
        if AUTO_DELETE_MESSAGES:
            auto_delete_message_sync(update.effective_chat.id, message.message_id)
    
    except Exception as e:
        logger.error(f"禁言失败: {e}", exc_info=True)
        message = update.message.reply_text(f"操作失败: {str(e)}")
        if AUTO_DELETE_MESSAGES:
            auto_delete_message_sync(update.effective_chat.id, message.message_id)

def heatmap_command(update: Update, context: CallbackContext) -> None:
    """处理/tu命令 - 聊天热力图"""
    user = update.effective_user
    
    # 检查参数
    if not context.args or len(context.args) < 1:
        message = update.message.reply_text(
            "请提供热力图类型，例如：\n"
            "/tu d - 当日聊天热力图\n"
            "/tu m - 当月聊天热力图\n"
            "/tu y - 年度聊天热力图"
        )
        if AUTO_DELETE_MESSAGES:
            auto_delete_message_sync(update.effective_chat.id, message.message_id)
        return
    
    # 获取热力图类型
    heatmap_type = context.args[0].lower()
    
    if heatmap_type not in ['d', 'm', 'y']:
        message = update.message.reply_text(
            "不支持的热力图类型，请使用：\n"
            "d - 当日热力图\n"
            "m - 当月热力图\n"
            "y - 年度热力图"
        )
        if AUTO_DELETE_MESSAGES:
            auto_delete_message_sync(update.effective_chat.id, message.message_id)
        return
    
    try:
        # 发送正在生成消息
        processing_message = update.message.reply_text("正在生成热力图，请稍候...")
        
        # 获取群组ID
        chat_id = update.effective_chat.id
        
        # 根据热力图类型获取时间范围
        now = datetime.now()
        
        if heatmap_type == 'd':
            # 当日热力图
            start_time = datetime(now.year, now.month, now.day, 0, 0, 0)
            end_time = start_time + timedelta(days=1)
            title = f"{now.year}年{now.month}月{now.day}日聊天热力图"
            
            # 获取消息数据
            messages = get_group_messages(chat_id, start_time, end_time)
            
            # 按小时统计消息
            hour_counts = {}
            for msg in messages:
                created_at = msg.get("created_at")
                if isinstance(created_at, str):
                    try:
                        created_at = datetime.fromisoformat(created_at)
                    except ValueError:
                        continue
                
                hour = created_at.hour
                hour_counts[hour] = hour_counts.get(hour, 0) + 1
            
            # 创建热力图数据
            hours = list(range(24))
            counts = [hour_counts.get(h, 0) for h in hours]
            
            # 创建图表
            plt.figure(figsize=(12, 6))
            plt.bar(hours, counts, color='skyblue')
            plt.xlabel('小时')
            plt.ylabel('消息数量')
            plt.title(title)
            plt.xticks(hours)
            plt.grid(axis='y', linestyle='--', alpha=0.7)
            
        elif heatmap_type == 'm':
            # 当月热力图
            start_time = datetime(now.year, now.month, 1, 0, 0, 0)
            if now.month == 12:
                end_time = datetime(now.year + 1, 1, 1, 0, 0, 0)
            else:
                end_time = datetime(now.year, now.month + 1, 1, 0, 0, 0)
            
            title = f"{now.year}年{now.month}月聊天热力图"
            
            # 获取消息数据
            messages = get_group_messages(chat_id, start_time, end_time)
            
            # 按日期统计消息
            day_counts = {}
            for msg in messages:
                created_at = msg.get("created_at")
                if isinstance(created_at, str):
                    try:
                        created_at = datetime.fromisoformat(created_at)
                    except ValueError:
                        continue
                
                day = created_at.day
                day_counts[day] = day_counts.get(day, 0) + 1
            
            # 创建热力图数据
            import calendar
            days_in_month = calendar.monthrange(now.year, now.month)[1]
            days = list(range(1, days_in_month + 1))
            counts = [day_counts.get(d, 0) for d in days]
            
            # 创建图表
            plt.figure(figsize=(12, 6))
            plt.bar(days, counts, color='skyblue')
            plt.xlabel('日期')
            plt.ylabel('消息数量')
            plt.title(title)
            plt.xticks(days)
            plt.grid(axis='y', linestyle='--', alpha=0.7)
            
        else:  # heatmap_type == 'y'
            # 年度热力图
            start_time = datetime(now.year, 1, 1, 0, 0, 0)
            end_time = datetime(now.year + 1, 1, 1, 0, 0, 0)
            title = f"{now.year}年聊天热力图"
            
            # 获取消息数据
            messages = get_group_messages(chat_id, start_time, end_time)
            
            # 按月份统计消息
            month_counts = {}
            for msg in messages:
                created_at = msg.get("created_at")
                if isinstance(created_at, str):
                    try:
                        created_at = datetime.fromisoformat(created_at)
                    except ValueError:
                        continue
                
                month = created_at.month
                month_counts[month] = month_counts.get(month, 0) + 1
            
            # 创建热力图数据
            months = list(range(1, 13))
            month_names = ['一月', '二月', '三月', '四月', '五月', '六月', 
                          '七月', '八月', '九月', '十月', '十一月', '十二月']
            counts = [month_counts.get(m, 0) for m in months]
            
            # 创建图表
            plt.figure(figsize=(12, 6))
            plt.bar(month_names, counts, color='skyblue')
            plt.xlabel('月份')
            plt.ylabel('消息数量')
            plt.title(title)
            plt.xticks(rotation=45)
            plt.grid(axis='y', linestyle='--', alpha=0.7)
        
        # 保存图表到内存
        img_data = BytesIO()
        plt.tight_layout()
        plt.savefig(img_data, format='png')
        img_data.seek(0)
        
        # 删除处理中消息
        _bot.delete_message(
            chat_id=update.effective_chat.id,
            message_id=processing_message.message_id
        )
        
        # 发送热力图
        message = _bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=img_data,
            caption=title
        )
        
        # 更新积分
        update_user_points_sync(
            user.id, 
            1, 
            "heatmap", 
            f"生成{heatmap_type}类型热力图"
        )
        
        # 清理图表
        plt.close()
        
        if AUTO_DELETE_MESSAGES:
            # 延长自动删除时间
            asyncio.create_task(asyncio.sleep(AUTO_DELETE_INTERVAL * 2))
            asyncio.create_task(_bot.delete_message(
                chat_id=update.effective_chat.id,
                message_id=message.message_id
            ))
    
    except Exception as e:
        logger.error(f"生成热力图失败: {e}", exc_info=True)
        _bot.delete_message(
            chat_id=update.effective_chat.id,
            message_id=processing_message.message_id
        )
        message = update.message.reply_text(f"生成热力图失败: {str(e)}")
        if AUTO_DELETE_MESSAGES:
            auto_delete_message_sync(update.effective_chat.id, message.message_id)

def points_detail_command(update: Update, context: CallbackContext) -> None:
    """处理/jfxx命令 - 积分详情"""
    user = update.effective_user
    target_user_id = user.id
    
    # 检查参数
    if context.args and len(context.args) > 0:
        # 检查是否有管理员权限
        if user.id not in ADMIN_IDS:
            message = update.message.reply_text("只有管理员才能查看其他用户的积分详情")
            if AUTO_DELETE_MESSAGES:
                auto_delete_message_sync(update.effective_chat.id, message.message_id)
            return
        
        # 查询指定用户的积分
        target_username = context.args[0].replace("@", "")
        
        # 尝试获取用户数据
        collection = get_collection("users")
        user_data = collection.find_one({"username": target_username})
        
        if not user_data:
            message = update.message.reply_text(f"未找到用户 @{target_username}")
            if AUTO_DELETE_MESSAGES:
                auto_delete_message_sync(update.effective_chat.id, message.message_id)
            return
        
        target_user_id = user_data.get("user_id")
    
    # 获取用户数据
    collection = get_collection("users")
    user_data = collection.find_one({"user_id": target_user_id})
    if not user_data:
        message = update.message.reply_text(f"未找到用户数据")
        if AUTO_DELETE_MESSAGES:
            auto_delete_message_sync(update.effective_chat.id, message.message_id)
        return
    
    # 获取积分历史
    history_collection = get_collection("points_history")
    cursor = history_collection.find({"user_id": target_user_id}).sort("date", -1).limit(10)
    history = list(cursor)
    
    # 构建积分详情文本
    points = user_data.get("points", 0)
    username = user_data.get("username", "无用户名")
    
    detail_text = (
        f"*{username} 的积分详情*\n\n"
        f"💰 当前积分: {points}分\n\n"
        f"📝 *最近积分记录*\n"
    )
    
    if history:
        for i, record in enumerate(history, 1):
            record_date = record.get("date", datetime.now())
            record_points = record.get("points", 0)
            record_source = record.get("source", "未知来源")
            record_desc = record.get("description", "")
            
            detail_text += (
                f"{i}. {record_date.strftime('%Y-%m-%d')} "
                f"{'+' if record_points > 0 else ''}{record_points}分 "
                f"[{record_source}] {record_desc}\n"
            )
    else:
        detail_text += "暂无积分记录\n"
    
    # 发送积分详情
    message = update.message.reply_text(
        detail_text,
        parse_mode=ParseMode.MARKDOWN
    )
    
    # 保存消息记录
    save_message_to_db_sync(update, "text", message.text)
    
    if AUTO_DELETE_MESSAGES:
        auto_delete_message_sync(update.effective_chat.id, message.message_id)

def checkin_command(update: Update, context: CallbackContext) -> None:
    """处理/qd命令 - 签到功能"""
    user = update.effective_user
    user_id = user.id
    
    # 获取用户数据 - 使用同步方式
    collection = get_collection("users")
    user_data = collection.find_one({"user_id": user_id})
    if not user_data:
        # 如果用户不存在，创建用户
        user_data = {
            "user_id": user_id,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "is_admin": user_id in ADMIN_IDS,
            "is_bot": user.is_bot,
            "language_code": user.language_code
        }
        # 使用同步方式创建用户
        collection.insert_one(user_data)
        user_data = collection.find_one({"user_id": user_id})
    
    # 检查今天是否已经签到
    settings = user_data.get("settings", {})
    last_checkin_str = settings.get("last_checkin", "")
    try:
        if last_checkin_str:
            last_checkin = datetime.strptime(last_checkin_str, "%Y-%m-%d").date()
        else:
            last_checkin = None
    except:
        last_checkin = None
    
    today = datetime.now().date()
    today_str = today.strftime("%Y-%m-%d")
    
    if last_checkin == today:
        message = update.message.reply_text(f"{user.first_name}，你今天已经签到过了！")
        if AUTO_DELETE_MESSAGES:
            auto_delete_message_sync(update.effective_chat.id, message.message_id)
        return
    
    # 计算连续签到天数
    checkin_streak = settings.get("checkin_streak", 0)
    if last_checkin:
        # 检查是否连续签到
        yesterday = today - timedelta(days=1)
        if last_checkin == yesterday:
            # 连续签到
            checkin_streak += 1
        else:
            # 断签，重置连续天数
            checkin_streak = 1
    else:
        # 第一次签到
        checkin_streak = 1
    
    # 计算积分奖励
    base_points = 5  # 基础积分
    streak_bonus = min(checkin_streak, 30)  # 连续签到奖励，最多30天
    total_points = base_points + streak_bonus
    
    # 更新签到记录
    if "settings" not in user_data:
        settings = {}
    settings["last_checkin"] = today_str
    settings["checkin_streak"] = checkin_streak
    
    # 更新用户设置 - 使用同步方式
    collection.update_one(
        {"user_id": user_id},
        {"$set": {"settings": settings}}
    )
    
    # 更新用户积分
    update_user_points_sync(
        user_id, 
        total_points, 
        "checkin", 
        f"第{checkin_streak}天连续签到"
    )
    
    # 获取更新后的用户数据
    updated_user = collection.find_one({"user_id": user_id})
    current_points = updated_user.get("points", 0)
    
    # 发送签到成功消息
    message = update.message.reply_text(
        f"✅ {user.first_name}，签到成功！\n"
        f"➕ 获得{total_points}积分（基础{base_points}分+连续签到{streak_bonus}分）\n"
        f"📊 当前积分：{current_points}\n"
        f"🔄 已连续签到{checkin_streak}天"
    )
    
    # 保存消息记录
    save_message_to_db_sync(update, "text", message.text)
    
    if AUTO_DELETE_MESSAGES:
        auto_delete_message_sync(update.effective_chat.id, message.message_id)

def handle_new_chat_members(update: Update, context: CallbackContext) -> None:
    """处理新成员加入群组的事件"""
    chat_id = update.effective_chat.id
    chat_title = update.effective_chat.title
    new_members = update.message.new_chat_members
    
    for new_member in new_members:
        if new_member.is_bot and new_member.id != context.bot.id:
            # 处理其他机器人加入
            logger.info(f"机器人 {new_member.username} 加入了群组 {chat_title} (ID: {chat_id})")
            continue
        
        if new_member.id == context.bot.id:
            # 处理本机器人被加入群组
            welcome_message = f"👋 大家好！我是一个功能强大的管理机器人。\n输入 /help 查看可用命令。"
            update.effective_chat.send_message(welcome_message)
            
            # 记录群组信息到数据库
            group_data = {
                "group_id": chat_id,
                "title": chat_title,
                "join_date": datetime.now(),
                "is_active": True,
                "members_count": update.effective_chat.get_members_count()
            }
            collection = get_collection("groups")
            collection.update_one(
                {"group_id": chat_id},
                {"$set": group_data},
                upsert=True
            )
            
            logger.info(f"机器人被添加到群组 {chat_title} (ID: {chat_id})")
            return
            
        # 普通用户加入
        user_data = {
            "user_id": new_member.id,
            "username": new_member.username,
            "first_name": new_member.first_name,
            "last_name": new_member.last_name,
            "is_bot": new_member.is_bot,
            "language_code": new_member.language_code,
            "last_activity": datetime.now()
        }
        
        # 更新用户信息
        user_collection = get_collection("users")
        existing_user = user_collection.find_one({"user_id": new_member.id})
        
        if existing_user:
            # 已存在的用户，更新其群组列表
            if chat_id not in existing_user.get("groups", []):
                user_collection.update_one(
                    {"user_id": new_member.id},
                    {"$push": {"groups": chat_id}, "$set": {"last_activity": datetime.now()}}
                )
        else:
            # 新用户，创建记录
            user_data["groups"] = [chat_id]
            user_data["join_date"] = datetime.now()
            user_data["points"] = 0
            user_data["points_history"] = []
            user_data["is_admin"] = False
            user_collection.insert_one(user_data)
        
        # 欢迎新成员
        welcome_message = f"👋 欢迎 {new_member.first_name} 加入 {chat_title}！\n请查看群组规则，并友好交流。"
        message = update.effective_chat.send_message(welcome_message)
        
        # 记录欢迎消息
        save_message_to_db_sync(update, "system", welcome_message)
        
        # 自动删除欢迎消息
        if AUTO_DELETE_MESSAGES:
            auto_delete_message_sync(chat_id, message.message_id)
            
        logger.info(f"用户 {new_member.username or new_member.first_name} (ID: {new_member.id}) 加入了群组 {chat_title} (ID: {chat_id})")

def handle_left_chat_member(update: Update, context: CallbackContext) -> None:
    """处理成员离开群组的事件"""
    chat_id = update.effective_chat.id
    chat_title = update.effective_chat.title
    left_member = update.message.left_chat_member
    
    if left_member.id == context.bot.id:
        # 机器人被踢出群组
        collection = get_collection("groups")
        collection.update_one(
            {"group_id": chat_id},
            {"$set": {"is_active": False, "left_date": datetime.now()}}
        )
        logger.info(f"机器人被移出群组 {chat_title} (ID: {chat_id})")
        return
    
    # 更新用户在该群组的状态
    user_collection = get_collection("users")
    user_collection.update_one(
        {"user_id": left_member.id},
        {"$pull": {"groups": chat_id}, "$set": {"last_activity": datetime.now()}}
    )
    
    # 记录用户离开消息
    leave_message = f"👋 {left_member.first_name} 离开了群组。"
    save_message_to_db_sync(update, "system", leave_message)
    
    logger.info(f"用户 {left_member.username or left_member.first_name} (ID: {left_member.id}) 离开了群组 {chat_title} (ID: {chat_id})") 