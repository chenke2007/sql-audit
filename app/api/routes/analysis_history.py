"""
分析历史 API 路由

提供分析历史的保存、查询、删除功能。
"""

import json
import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, status, Depends, Query

from app.core.database import get_metadata_db
from app.core.rbac import get_current_user, require_permission
from app.models.user_models import (
    AnalysisHistoryCreate, AnalysisHistoryItem,
    AnalysisHistoryDetail, AnalysisHistoryListResponse
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/analysis-history", tags=["分析历史"])


def _history_row_to_item(row: dict, include_result: bool = False) -> dict:
    """将数据库行转换为响应字典"""
    item = {
        "id": row["id"],
        "db_source_name": row.get("db_source_name"),
        "schema": row.get("schema"),
        "sql_text": row["sql_text"],
        "sql_id": row.get("sql_id"),
        "input_mode": row["input_mode"],
        "risk_level": row.get("risk_level"),
        "created_at": row["created_at"],
    }
    if include_result:
        item["result_json"] = row.get("result_json")
        item["user_id"] = row["user_id"]
    if "username" in row:
        item["username"] = row["username"]
    return item


@router.get("", response_model=AnalysisHistoryListResponse)
async def get_my_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user)
):
    """获取当前用户的分析历史"""
    user_id = current_user["id"]

    with get_metadata_db() as conn:
        cursor = conn.cursor()

        # 构建查询
        where_clause = "WHERE h.user_id = ?"
        params = [user_id]
        if keyword:
            where_clause += " AND h.sql_text LIKE ?"
            params.append(f"%{keyword}%")

        # 查询总数
        cursor.execute(f"SELECT COUNT(*) as total FROM analysis_history h {where_clause}", params)
        total = cursor.fetchone()["total"]

        # 查询列表
        cursor.execute(f"""
            SELECT h.*, ds.name as db_source_name
            FROM analysis_history h
            LEFT JOIN db_sources ds ON h.db_source_id = ds.id
            {where_clause}
            ORDER BY h.created_at DESC
            LIMIT ? OFFSET ?
        """, params + [page_size, (page - 1) * page_size])

        items = [_history_row_to_item(dict(row)) for row in cursor.fetchall()]

        return AnalysisHistoryListResponse(
            items=[AnalysisHistoryItem(**item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )


@router.get("/all", response_model=AnalysisHistoryListResponse)
async def get_all_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: Optional[str] = Query(None),
    current_user: dict = Depends(require_permission("analysis:history:all"))
):
    """获取所有人的分析历史（管理员）"""
    with get_metadata_db() as conn:
        cursor = conn.cursor()

        where_clause = "WHERE 1=1"
        params = []
        if keyword:
            where_clause += " AND (h.sql_text LIKE ? OR u.username LIKE ?)"
            params.extend([f"%{keyword}%", f"%{keyword}%"])

        # 查询总数
        cursor.execute(f"""
            SELECT COUNT(*) as total FROM analysis_history h
            JOIN users u ON h.user_id = u.id
            {where_clause}
        """, params)
        total = cursor.fetchone()["total"]

        # 查询列表
        cursor.execute(f"""
            SELECT h.*, ds.name as db_source_name, u.username
            FROM analysis_history h
            JOIN users u ON h.user_id = u.id
            LEFT JOIN db_sources ds ON h.db_source_id = ds.id
            {where_clause}
            ORDER BY h.created_at DESC
            LIMIT ? OFFSET ?
        """, params + [page_size, (page - 1) * page_size])

        items = [_history_row_to_item(dict(row)) for row in cursor.fetchall()]

        return AnalysisHistoryListResponse(
            items=[AnalysisHistoryItem(**item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )


@router.get("/{history_id}", response_model=AnalysisHistoryDetail)
async def get_history_detail(
    history_id: int,
    current_user: dict = Depends(get_current_user)
):
    """获取单条分析历史详情"""
    with get_metadata_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT h.*, ds.name as db_source_name, u.username
            FROM analysis_history h
            JOIN users u ON h.user_id = u.id
            LEFT JOIN db_sources ds ON h.db_source_id = ds.id
            WHERE h.id = ?
        """, (history_id,))
        row = cursor.fetchone()

    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="记录不存在")

    record = dict(row)
    # 权限检查：只能看自己的，除非有 analysis:history:all 权限
    if record["user_id"] != current_user["id"] and "analysis:history:all" not in current_user.get("permissions", []):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="没有权限查看此记录")

    item = _history_row_to_item(record, include_result=True)
    return AnalysisHistoryDetail(**item)


@router.delete("/{history_id}")
async def delete_history(
    history_id: int,
    current_user: dict = Depends(get_current_user)
):
    """删除分析历史记录"""
    with get_metadata_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM analysis_history WHERE id = ?", (history_id,))
        row = cursor.fetchone()

    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="记录不存在")

    # 权限检查：只能删自己的，除非有 analysis:history:all 权限
    if row["user_id"] != current_user["id"] and "analysis:history:all" not in current_user.get("permissions", []):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="没有权限删除此记录")

    with get_metadata_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM analysis_history WHERE id = ?", (history_id,))
        conn.commit()

    return {"message": "记录已删除"}


async def save_analysis_history(
    user_id: int,
    db_source_id: Optional[str],
    schema: Optional[str],
    sql_text: str,
    sql_id: Optional[str],
    input_mode: str,
    result: dict,
    risk_level: Optional[str]
):
    """保存分析历史记录（供分析路由调用）"""
    try:
        with get_metadata_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO analysis_history
                (user_id, db_source_id, schema, sql_text, sql_id, input_mode, result_json, risk_level)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                user_id, db_source_id, schema, sql_text, sql_id,
                input_mode, json.dumps(result, ensure_ascii=False), risk_level
            ))
            conn.commit()
    except Exception as e:
        logger.warning(f"保存分析历史失败: {e}")
