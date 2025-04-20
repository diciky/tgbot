#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
MongoDB数据库连接模块
"""
import os
import logging
import motor.motor_asyncio
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

logger = logging.getLogger(__name__)

# 数据库配置
MONGO_HOST = os.getenv("MONGO_HOST", "localhost")
MONGO_PORT = int(os.getenv("MONGO_PORT", 27017))
MONGO_USERNAME = os.getenv("MONGO_USERNAME", "admin")
MONGO_PASSWORD = os.getenv("MONGO_PASSWORD", "465465Daz")
MONGO_DB = os.getenv("MONGO_DB", "tgbot")

# 构建MongoDB连接URI
MONGO_URI = f"mongodb://{MONGO_USERNAME}:{MONGO_PASSWORD}@{MONGO_HOST}:{MONGO_PORT}/{MONGO_DB}"

# 异步客户端
async_client = None
async_db = None

# 同步客户端
sync_client = None
sync_db = None

# 初始化同步客户端
try:
    sync_client = MongoClient(MONGO_URI)
    sync_db = sync_client[MONGO_DB]
except Exception as e:
    logger.error(f"初始化同步MongoDB连接时出错: {e}")

async def connect_to_mongodb():
    """连接到MongoDB数据库"""
    global async_client, async_db
    try:
        # 创建异步MongoDB客户端
        async_client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
        
        # 检查连接
        await async_client.admin.command("ping")
        
        # 获取异步数据库
        async_db = async_client[MONGO_DB]
        
        logger.info(f"已成功连接到MongoDB: {MONGO_HOST}:{MONGO_PORT}/{MONGO_DB}")
        return async_db
    except ConnectionFailure as e:
        logger.error(f"MongoDB连接失败: {e}")
        raise
    except Exception as e:
        logger.error(f"初始化MongoDB时出错: {e}")
        raise

async def close_mongodb_connection():
    """关闭MongoDB连接"""
    global async_client
    if async_client:
        async_client.close()
    logger.info("已关闭MongoDB连接")

# 集合访问器
def get_collection(collection_name):
    """获取指定的集合(同步)"""
    global sync_client, sync_db
    
    if sync_db is None:
        # 如果同步数据库未初始化，尝试初始化它
        try:
            sync_client = MongoClient(MONGO_URI)
            sync_db = sync_client[MONGO_DB]
        except Exception as e:
            logger.error(f"初始化同步MongoDB连接时出错: {e}")
            raise ConnectionError("数据库未连接")
            
    return sync_db[collection_name]

async def get_async_collection(collection_name):
    """获取指定的集合(异步)"""
    global async_db
    
    if async_db is None:
        raise ConnectionError("异步数据库未连接")
    return async_db[collection_name]

# 集合名称常量
USERS_COLLECTION = "users"
MESSAGES_COLLECTION = "messages"
GROUPS_COLLECTION = "groups"
SETTINGS_COLLECTION = "settings" 