#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
用户模型
"""
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from .database import get_collection, get_async_collection, USERS_COLLECTION

logger = logging.getLogger(__name__)

class PointsEntry(BaseModel):
    """积分记录模型"""
    amount: int
    source: str
    description: str
    timestamp: datetime = Field(default_factory=datetime.now)

    class Config:
        """Pydantic配置"""
        validate_assignment = True
        arbitrary_types_allowed = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

class User(BaseModel):
    """用户模型"""
    user_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    is_admin: bool = False
    is_bot: bool = False
    language_code: Optional[str] = None
    join_date: datetime = Field(default_factory=datetime.now)
    last_activity: datetime = Field(default_factory=datetime.now)
    groups: List[int] = Field(default_factory=list)
    settings: Dict[str, Any] = Field(default_factory=dict)
    points: int = 0
    points_history: List[Dict[str, Any]] = Field(default_factory=list)
    is_banned: bool = False
    is_muted: bool = False
    muted_until: Optional[datetime] = None
    
    class Config:
        """Pydantic配置"""
        validate_assignment = True
        arbitrary_types_allowed = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

async def get_user(user_id: int) -> Optional[Dict[str, Any]]:
    """获取用户信息"""
    collection = get_collection(USERS_COLLECTION)
    user = await collection.find_one({"user_id": user_id})
    return user

async def create_user(user_data: Dict[str, Any]) -> Dict[str, Any]:
    """创建用户"""
    collection = get_collection(USERS_COLLECTION)
    
    # 检查用户是否已存在
    existing_user = await get_user(user_data["user_id"])
    if existing_user:
        return existing_user
    
    # 设置创建时间
    user_data["join_date"] = datetime.now()
    user_data["last_activity"] = datetime.now()
    
    # 初始化积分系统
    if "points" not in user_data:
        user_data["points"] = 0
    if "points_history" not in user_data:
        user_data["points_history"] = []
    
    # 创建用户
    result = await collection.insert_one(user_data)
    if result.inserted_id:
        return await get_user(user_data["user_id"])
    return None

async def update_user(user_id: int, update_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """更新用户信息"""
    collection = get_collection(USERS_COLLECTION)
    
    # 更新用户活动时间
    update_data["last_activity"] = datetime.now()
    
    result = await collection.update_one(
        {"user_id": user_id},
        {"$set": update_data}
    )
    
    if result.modified_count > 0 or result.matched_count > 0:
        return await get_user(user_id)
    return None

async def update_user_points(
    user_id: int, 
    points: int, 
    source: str, 
    description: str = ""
) -> None:
    """异步更新用户积分"""
    try:
        # 异步更新
        collection = await get_async_collection(USERS_COLLECTION)
        
        # 更新积分
        result = await collection.update_one(
            {"user_id": user_id},
            {"$inc": {"points": points}}
        )
        
        if result.modified_count == 0:
            # 用户不存在，创建用户
            logger.warning(f"用户{user_id}不存在，无法更新积分")
            return
        
        # 记录积分历史
        points_history = {
            "user_id": user_id,
            "points": points,
            "source": source,
            "description": description,
            "date": datetime.now()
        }
        
        history_collection = await get_async_collection("points_history")
        await history_collection.insert_one(points_history)
        
    except Exception as e:
        logger.error(f"更新用户积分失败: {e}")

def update_user_points_sync(
    user_id: int, 
    points: int, 
    source: str, 
    description: str = ""
) -> None:
    """同步更新用户积分"""
    try:
        # 同步更新
        collection = get_collection(USERS_COLLECTION)
        
        # 更新积分
        result = collection.update_one(
            {"user_id": user_id},
            {"$inc": {"points": points}}
        )
        
        if result.modified_count == 0:
            # 用户不存在，创建用户
            logger.warning(f"用户{user_id}不存在，无法更新积分")
            return
        
        # 记录积分历史
        points_history = {
            "user_id": user_id,
            "points": points,
            "source": source,
            "description": description,
            "date": datetime.now()
        }
        
        history_collection = get_collection("points_history")
        history_collection.insert_one(points_history)
        
    except Exception as e:
        logger.error(f"更新用户积分失败: {e}")

async def get_all_users(limit: int = 100, skip: int = 0) -> List[Dict[str, Any]]:
    """获取所有用户"""
    try:
        collection = get_collection(USERS_COLLECTION)
        logger.info(f"执行查询: collection={USERS_COLLECTION}, skip={skip}, limit={limit}")
        cursor = collection.find().skip(skip).limit(limit)
        result = list(cursor)
        logger.info(f"查询完成: 获取到{len(result)}条记录")
        return result
    except Exception as e:
        logger.error(f"获取所有用户失败: {e}", exc_info=True)
        raise

async def get_top_users_by_points(limit: int = 10) -> List[Dict[str, Any]]:
    """获取积分排行榜"""
    collection = get_collection(USERS_COLLECTION)
    cursor = collection.find().sort("points", -1).limit(limit)
    result = list(cursor)
    return result

async def get_admins() -> List[Dict[str, Any]]:
    """获取所有管理员用户"""
    collection = get_collection(USERS_COLLECTION)
    cursor = collection.find({"is_admin": True})
    result = list(cursor)
    return result

async def count_users() -> int:
    """统计用户数量"""
    collection = get_collection(USERS_COLLECTION)
    return collection.count_documents({})

async def delete_user(user_id: int) -> bool:
    """删除用户"""
    collection = get_collection(USERS_COLLECTION)
    result = await collection.delete_one({"user_id": user_id})
    return result.deleted_count > 0 