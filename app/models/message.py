#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
消息模型
"""
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from .database import get_collection, MESSAGES_COLLECTION

logger = logging.getLogger(__name__)

class Message(BaseModel):
    """消息模型"""
    message_id: int
    chat_id: int
    user_id: int
    text: Optional[str] = None
    date: datetime = Field(default_factory=datetime.now)
    message_type: str = "text"  # text, photo, video, document, etc.
    file_id: Optional[str] = None
    reply_to_message_id: Optional[int] = None
    forwarded_from: Optional[int] = None
    content: Dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        """Pydantic配置"""
        validate_assignment = True
        arbitrary_types_allowed = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

async def save_message(message_data: Dict[str, Any]) -> Dict[str, Any]:
    """保存消息"""
    collection = get_collection(MESSAGES_COLLECTION)
    
    # 确保有日期字段
    if "date" not in message_data:
        message_data["date"] = datetime.now()
    
    # 插入消息
    result = await collection.insert_one(message_data)
    if result.inserted_id:
        return await get_message(message_data["message_id"], message_data["chat_id"])
    return None

async def get_message(message_id: int, chat_id: int) -> Optional[Dict[str, Any]]:
    """获取消息"""
    collection = get_collection(MESSAGES_COLLECTION)
    message = await collection.find_one({
        "message_id": message_id,
        "chat_id": chat_id
    })
    return message

async def get_chat_messages(chat_id: int, limit: int = 100, skip: int = 0) -> List[Dict[str, Any]]:
    """获取聊天消息"""
    collection = get_collection(MESSAGES_COLLECTION)
    cursor = collection.find({"chat_id": chat_id}) \
        .sort("date", -1) \
        .skip(skip) \
        .limit(limit)
    return await cursor.to_list(length=limit)

async def get_user_messages(user_id: int, limit: int = 100, skip: int = 0) -> List[Dict[str, Any]]:
    """获取用户消息"""
    collection = get_collection(MESSAGES_COLLECTION)
    cursor = collection.find({"user_id": user_id}) \
        .sort("date", -1) \
        .skip(skip) \
        .limit(limit)
    return await cursor.to_list(length=limit)

async def get_group_messages(group_ids: List[int], limit: int = 100, skip: int = 0) -> List[Dict[str, Any]]:
    """获取多个群组的消息"""
    collection = get_collection(MESSAGES_COLLECTION)
    cursor = collection.find({"chat_id": {"$in": group_ids}}) \
        .sort("date", -1) \
        .skip(skip) \
        .limit(limit)
    return await cursor.to_list(length=limit)

async def delete_message(message_id: int, chat_id: int) -> bool:
    """删除消息"""
    collection = get_collection(MESSAGES_COLLECTION)
    result = await collection.delete_one({
        "message_id": message_id,
        "chat_id": chat_id
    })
    return result.deleted_count > 0

async def count_messages(query: Dict[str, Any] = None) -> int:
    """统计消息数量"""
    collection = get_collection(MESSAGES_COLLECTION)
    return await collection.count_documents(query or {})

async def search_messages(text: str, limit: int = 100, skip: int = 0) -> List[Dict[str, Any]]:
    """搜索消息"""
    collection = get_collection(MESSAGES_COLLECTION)
    cursor = collection.find(
        {"text": {"$regex": text, "$options": "i"}}
    ).sort("date", -1).skip(skip).limit(limit)
    return await cursor.to_list(length=limit)

async def get_message_types_stats() -> Dict[str, int]:
    """获取消息类型统计"""
    collection = get_collection(MESSAGES_COLLECTION)
    pipeline = [
        {"$group": {"_id": "$message_type", "count": {"$sum": 1}}}
    ]
    result = await collection.aggregate(pipeline).to_list(length=100)
    return {item["_id"]: item["count"] for item in result} 