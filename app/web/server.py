#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Web服务器模块
"""
import os
import logging
import jwt
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from fastapi import FastAPI, Depends, HTTPException, status, Request, Response
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, JSONResponse
from pydantic import BaseModel
import uvicorn
import requests
from telegram import Bot
from app.models.database import connect_to_mongodb, get_collection
from app.models.user import get_all_users, count_users, delete_user
from app.models.message import count_messages, get_chat_messages
from app.models.group import count_groups, get_all_groups

logger = logging.getLogger(__name__)

# 从环境变量获取配置
SECRET_KEY = os.getenv("SECRET_KEY", "465465Daz")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ACCESS_TOKEN_EXPIRE_MINUTES = 30
AUTO_DELETE_MESSAGES = os.getenv("AUTO_DELETE_MESSAGES", "true").lower() == "true"
DEBUG_MODE = os.getenv("DEBUG", "false").lower() == "true"

# 认证相关
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/token")

class Token(BaseModel):
    """令牌模型"""
    access_token: str
    token_type: str

class User(BaseModel):
    """Web用户模型"""
    username: str

class UserInDB(User):
    """数据库中的用户模型"""
    hashed_password: str

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    # 此处简化，实际应使用安全的哈希算法
    return plain_password == hashed_password

def get_user(username: str) -> Optional[UserInDB]:
    """获取用户"""
    # 此处简化，仅支持管理员账户
    if username == ADMIN_USERNAME:
        return UserInDB(username=ADMIN_USERNAME, hashed_password=ADMIN_PASSWORD)
    return None

def authenticate_user(username: str, password: str) -> Optional[User]:
    """认证用户"""
    user = get_user(username)
    if not user or not verify_password(password, user.hashed_password):
        return None
    return User(username=user.username)

def create_access_token(data: Dict[str, Any], expires_delta: timedelta = None) -> str:
    """创建访问令牌"""
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm="HS256")
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    """获取当前用户"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无效的认证凭据",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception
    
    user = get_user(username)
    if user is None:
        raise credentials_exception
    
    return User(username=user.username)

# FastAPI应用
app = FastAPI(title="Telegram Bot管理系统", docs_url="/api/docs", redoc_url="/api/redoc")

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 配置静态文件和模板
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

# 全局Bot实例
bot_instance = None

async def send_telegram_message(chat_id: int, text: str, bot_instance: Bot = None):
    """通过Telegram Bot发送消息"""
    # 如果有bot实例，直接使用
    if bot_instance:
        try:
            sent_message = await bot_instance.send_message(
                chat_id=chat_id,
                text=text
            )
            return {"ok": True, "result": {"message_id": sent_message.message_id}}
        except Exception as e:
            logger.error(f"通过Bot实例发送消息失败: {e}")
            # 如果Bot实例发送失败，尝试使用API
    
    # 使用API发送 (作为备选方案)
    if not BOT_TOKEN:
        raise HTTPException(status_code=503, detail="BOT_TOKEN未设置")
    
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": text
    }
    
    try:
        response = requests.post(url, json=data)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"发送消息失败: {e}")
        raise HTTPException(status_code=500, detail=f"发送消息失败: {str(e)}")

async def get_bot_info():
    """获取Bot信息"""
    global bot_instance
    
    # 如果有bot实例，直接使用
    if bot_instance:
        try:
            return {
                "username": bot_instance.username,
                "first_name": bot_instance.first_name,
                "id": bot_instance.id,
                "is_connected": True
            }
        except Exception as e:
            logger.error(f"通过Bot实例获取信息失败: {e}")
    
    # 如果没有bot实例或获取失败，使用API
    if not BOT_TOKEN:
        return {"username": "未知", "first_name": "未知Bot", "is_connected": False}
    
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getMe"
    
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        if data["ok"]:
            result = data["result"]
            result["is_connected"] = True
            return result
        return {"username": "未知", "first_name": "未知Bot", "is_connected": False}
    except Exception as e:
        logger.error(f"获取Bot信息失败: {e}")
        return {"username": "未知", "first_name": "未知Bot", "is_connected": False}

async def get_bot_stats():
    """获取Bot统计数据"""
    global bot_instance
    
    stats = {
        "is_connected": bot_instance is not None,
        "uptime": None,
        "processed_messages": 0,
        "commands_handled": 0,
        "groups_count": 0,
        "users_count": 0
    }
    
    # 从数据库获取更多统计信息
    try:
        # 获取群组数量
        groups_collection = get_collection("groups")
        stats["groups_count"] = groups_collection.count_documents({})
        
        # 获取用户数量
        users_collection = get_collection("users")
        stats["users_count"] = users_collection.count_documents({})
        
        # 获取消息数量
        messages_collection = get_collection("messages")
        stats["processed_messages"] = messages_collection.count_documents({})
        
        # 获取命令处理数量
        stats["commands_handled"] = messages_collection.count_documents({"text": {"$regex": "^/"}})
    except Exception as e:
        logger.error(f"获取Bot统计数据失败: {e}")
    
    return stats

async def setup_web_server(bot: Bot = None, host: str = "0.0.0.0", port: int = 7000) -> None:
    """设置并启动Web服务器"""
    global bot_instance
    
    # 保存Bot实例到全局变量
    bot_instance = bot
    if bot:
        logger.info(f"已接收Bot实例: {bot.username}")
    
    # 确保已连接到数据库
    await connect_to_mongodb()
    
    # 启动Web服务器
    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    
    # 非阻塞启动
    logger.info(f"Web服务器正在启动，地址: http://{host}:{port}")
    await server.serve()

# API路由
@app.post("/api/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    """获取访问令牌"""
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/api/users")
async def get_users(current_user: User = Depends(get_current_user), skip: int = 0, limit: int = 10):
    """获取用户列表"""
    try:
        logger.info(f"获取用户列表: skip={skip}, limit={limit}")
        users = await get_all_users(limit=limit, skip=skip)
        total = await count_users()
        logger.info(f"成功获取用户列表: 共{total}个用户")
        return {"users": users, "total": total}
    except Exception as e:
        logger.error(f"获取用户列表失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取用户列表失败: {str(e)}")

@app.get("/api/messages")
async def get_messages(
    current_user: User = Depends(get_current_user), 
    chat_id: int = None,
    skip: int = 0, 
    limit: int = 10
):
    """获取消息列表"""
    if not chat_id:
        # 获取群组列表供用户选择
        try:
            groups_collection = get_collection("groups")
            cursor = groups_collection.find({"is_active": True}).sort("title", 1)
            groups = await cursor.to_list(length=100)
            return {"groups": groups, "messages": [], "total": 0}
        except Exception as e:
            logger.error(f"获取群组列表失败: {e}")
            return {"groups": [], "messages": [], "total": 0}
    
    messages = await get_chat_messages(chat_id, limit=limit, skip=skip)
    total = await count_messages({"chat_id": chat_id})
    return {"messages": messages, "total": total, "groups": []}

@app.get("/api/bot/stats")
async def bot_stats_api(current_user: User = Depends(get_current_user)):
    """获取Bot统计API"""
    try:
        bot_info = await get_bot_info()
        bot_stats = await get_bot_stats()
        
        return {
            "info": bot_info,
            "stats": bot_stats,
            "status": "active" if bot_instance else "using_api"
        }
    except Exception as e:
        logger.error(f"获取Bot统计API失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取Bot统计失败: {str(e)}")

@app.get("/api/stats")
async def get_stats():
    """获取统计信息"""
    try:
        # 获取统计数据
        user_count = await count_users()
        message_count = await count_messages()
        group_count = await count_groups()
        
        # 获取活跃群组
        active_groups = await get_all_groups(limit=5)
        group_stats = [
            {
                "id": group["group_id"],
                "title": group["title"],
                "members": group["members_count"],
                "join_date": group["join_date"].isoformat() if isinstance(group["join_date"], datetime) else group["join_date"]
            }
            for group in active_groups
        ]
        
        # 获取Bot信息
        bot_info = await get_bot_info()
        
        # 返回结果
        return {
            "user_count": user_count,
            "message_count": message_count,
            "group_count": group_count,
            "active_groups": group_stats,
            "bot_info": bot_info
        }
    except Exception as e:
        logger.error(f"获取统计信息时出错: {e}")
        raise HTTPException(status_code=500, detail=f"获取统计信息失败: {str(e)}")

@app.delete("/api/users/{user_id}")
async def delete_user_api(user_id: int, current_user: User = Depends(get_current_user)):
    """删除用户"""
    success = await delete_user(user_id)
    if not success:
        raise HTTPException(status_code=404, detail="用户不存在")
    return {"success": True}

@app.post("/api/send_message")
async def send_message_api(
    chat_id: int, 
    text: str,
    current_user: User = Depends(get_current_user)
):
    """发送消息"""
    try:
        # 使用全局Bot实例
        result = await send_telegram_message(chat_id, text, bot_instance)
        return {"success": True, "message_id": result.get("result", {}).get("message_id", 0)}
    except Exception as e:
        logger.error(f"发送消息失败: {e}")
        raise HTTPException(status_code=500, detail=f"发送消息失败: {str(e)}")

@app.post("/api/bot/execute")
async def execute_bot_command(
    command: str,
    chat_id: int,
    current_user: User = Depends(get_current_user)
):
    """执行Bot命令"""
    global bot_instance
    
    if not bot_instance:
        raise HTTPException(status_code=503, detail="Bot实例不可用")
    
    try:
        # 验证命令格式
        if not command.startswith('/'):
            command = '/' + command
        
        # 使用Bot实例发送命令
        result = await send_telegram_message(chat_id, command, bot_instance)
        
        return {
            "success": True, 
            "message_id": result.get("result", {}).get("message_id", 0),
            "command": command
        }
    except Exception as e:
        logger.error(f"执行Bot命令失败: {e}")
        raise HTTPException(status_code=500, detail=f"执行Bot命令失败: {str(e)}")

# Web页面路由
@app.get("/")
async def index(request: Request):
    """首页"""
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/login")
async def login(request: Request):
    """登录页面"""
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/dashboard")
async def dashboard(request: Request):
    """仪表盘"""
    return templates.TemplateResponse("dashboard.html", {"request": request})

@app.get("/users")
async def users_page(request: Request):
    """用户管理页面"""
    return templates.TemplateResponse("users.html", {"request": request})

@app.get("/messages")
async def messages_page(request: Request):
    """消息管理页面"""
    return templates.TemplateResponse("messages.html", {"request": request})

@app.get("/settings")
async def settings_page(request: Request):
    """设置页面"""
    return templates.TemplateResponse("settings.html", {"request": request})

@app.get("/keywords")
async def keywords_page(request: Request):
    """关键词管理页面"""
    return templates.TemplateResponse("keywords.html", {"request": request})

@app.get("/commands")
async def commands_page(request: Request):
    """自定义命令管理页面"""
    return templates.TemplateResponse("commands.html", {"request": request})

@app.get("/groups")
async def groups_page(request: Request):
    """群组管理页面"""
    return templates.TemplateResponse("groups.html", {"request": request}) 