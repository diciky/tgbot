#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
群组模型
"""
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from .database import get_collection, get_async_collection, GROUPS_COLLECTION

logger = logging.getLogger(__name__)

class Group(BaseModel):
    """群组模型"""
    group_id: int
    title: str
    description: Optional[str] = None
    join_date: datetime = Field(default_factory=datetime.now)
    left_date: Optional[datetime] = None
    is_active: bool = True
    members_count: int = 0
    settings: Dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        """Pydantic配置"""
        validate_assignment = True
        arbitrary_types_allowed = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

async def get_group(group_id: int) -> Optional[Dict[str, Any]]:
    """获取群组信息"""
    collection = get_collection(GROUPS_COLLECTION)
    group = await collection.find_one({"group_id": group_id})
    return group

async def create_group(group_data: Dict[str, Any]) -> Dict[str, Any]:
    """创建群组"""
    collection = get_collection(GROUPS_COLLECTION)
    
    # 检查群组是否已存在
    existing_group = await get_group(group_data["group_id"])
    if existing_group:
        return existing_group
    
    # 设置创建时间
    group_data["join_date"] = datetime.now()
    group_data["is_active"] = True
    
    # 创建群组
    result = await collection.insert_one(group_data)
    if result.inserted_id:
        return await get_group(group_data["group_id"])
    return None

async def update_group(group_id: int, update_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """更新群组信息"""
    collection = get_collection(GROUPS_COLLECTION)
    
    result = await collection.update_one(
        {"group_id": group_id},
        {"$set": update_data}
    )
    
    if result.modified_count > 0 or result.matched_count > 0:
        return await get_group(group_id)
    return None

async def get_all_groups(limit: int = 100, skip: int = 0, active_only: bool = True) -> List[Dict[str, Any]]:
    """获取所有群组"""
    try:
        collection = get_collection(GROUPS_COLLECTION)
        query = {"is_active": True} if active_only else {}
        cursor = collection.find(query).skip(skip).limit(limit)
        result = await cursor.to_list(length=limit)
        return result
    except Exception as e:
        logger.error(f"获取所有群组失败: {e}", exc_info=True)
        raise

async def count_groups(active_only: bool = True) -> int:
    """统计群组数量"""
    collection = get_collection(GROUPS_COLLECTION)
    query = {"is_active": True} if active_only else {}
    return await collection.count_documents(query)

async def delete_group(group_id: int) -> bool:
    """删除群组"""
    collection = get_collection(GROUPS_COLLECTION)
    result = await collection.delete_one({"group_id": group_id})
    return result.deleted_count > 0

async def deactivate_group(group_id: int) -> bool:
    """将群组标记为非活动"""
    collection = get_collection(GROUPS_COLLECTION)
    result = await collection.update_one(
        {"group_id": group_id},
        {"$set": {"is_active": False, "left_date": datetime.now()}}
    )
    return result.modified_count > 0

async def get_group_members_count(group_id: int) -> int:
    """获取群组成员数量"""
    try:
        collection = get_collection("users")
        count = await collection.count_documents({"groups": group_id})
        return count
    except Exception as e:
        logger.error(f"获取群组成员数量失败: {e}", exc_info=True)
        return 0

async def update_group_members_count(group_id: int) -> bool:
    """更新群组成员数量"""
    try:
        members_count = await get_group_members_count(group_id)
        collection = get_collection(GROUPS_COLLECTION)
        result = await collection.update_one(
            {"group_id": group_id},
            {"$set": {"members_count": members_count}}
        )
        return result.modified_count > 0
    except Exception as e:
        logger.error(f"更新群组成员数量失败: {e}", exc_info=True)
        return False

def get_group_sync(group_id: int) -> Optional[Dict[str, Any]]:
    """同步获取群组信息"""
    collection = get_collection(GROUPS_COLLECTION)
    group = collection.find_one({"group_id": group_id})
    return group

def update_group_sync(group_id: int, update_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """同步更新群组信息"""
    collection = get_collection(GROUPS_COLLECTION)
    
    result = collection.update_one(
        {"group_id": group_id},
        {"$set": update_data}
    )
    
    if result.modified_count > 0 or result.matched_count > 0:
        return get_group_sync(group_id)
    return None 