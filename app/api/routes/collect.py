"""
SQL 采集 API 路由

提供三种输入方式的 HTTP 接口:
1. 自动采集慢SQL
2. SQL_ID 查询
3. 文件上传
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from app.config import settings
from app.core.dynamic_db_client import DynamicOracleClient
from app.core.database import DBSourceManager
from app.oracle.client import oracle_client, OracleConnectionError, OracleQueryError
from app.oracle.collector import SQLCollector, SQLObject
from app.oracle.metadata import MetadataCollector

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/collect", tags=["SQL采集"])


# ========== 数据模型 ==========

class SQLObjectResponse(BaseModel):
    """SQL对象响应 - Oracle性能指标"""
    sql_id: Optional[str] = Field(None, description="SQL标识符")
    sql_text: str = Field(..., description="SQL文本")
    schema: Optional[str] = Field(None, description="Schema/Parsing Schema Name")
    source: str = Field(..., description="来源: auto_collect, sql_id_query, file_upload")
    execution_stats: Optional[dict] = Field(None, description="执行统计")
    has_execution_plan: bool = Field(False, description="是否有执行计划")
    # Oracle特定性能指标
    cpu_pct: Optional[float] = Field(None, description="CPU Time %")
    elapsed_pct: Optional[float] = Field(None, description="Elapsed %")
    elapsed_sec: Optional[float] = Field(None, description="Elapsed Time (Sec)")
    elapsed_per_exec_sec: Optional[float] = Field(None, description="Elapsed Time/exec (Sec)")

    class Config:
        from_attributes = True


class SlowSQLCollectionRequest(BaseModel):
    """慢SQL采集请求"""
    db_source_id: Optional[str] = Field(None, description="数据源ID，不传则使用默认数据源")
    top_n: int = Field(20, ge=1, le=100, description="获取前N条")
    cpu_threshold_ms: int = Field(1000, ge=0, description="CPU时间阈值(毫秒)")
    elapsed_threshold_ms: int = Field(1000, ge=0, description="执行时间阈值(毫秒)")
    buffer_gets_threshold: int = Field(10000, ge=0, description="逻辑读阈值")
    exclude_system: bool = Field(True, description="是否排除系统SQL")


class SQLIdQueryRequest(BaseModel):
    """SQL_ID查询请求"""
    db_source_id: Optional[str] = Field(None, description="数据源ID，不传则使用默认数据源")
    sql_id: str = Field(..., min_length=1, description="SQL标识符")
    include_plan: bool = Field(True, description="是否获取执行计划")
    include_metadata: bool = Field(True, description="是否获取元数据")


class SQLUploadRequest(BaseModel):
    """SQL文本上传请求"""
    db_source_id: Optional[str] = Field(None, description="数据源ID，不传则使用默认数据源")
    sql_text: str = Field(..., min_length=1, description="SQL文本")
    include_plan: bool = Field(True, description="是否获取执行计划")


# ========== 辅助函数 ==========

def sql_object_to_response(obj: SQLObject, truncate_sql: bool = True) -> SQLObjectResponse:
    """将SQLObject转换为响应模型"""
    stats = None
    cpu_pct = elapsed_pct = elapsed_sec = elapsed_per_exec_sec = None
    schema = None

    if obj.execution_stats:
        stats = {
            "sql_id": obj.execution_stats.sql_id,
            "executions": obj.execution_stats.executions,
            "cpu_time_ms": obj.execution_stats.cpu_time_ms,
            "elapsed_time_ms": obj.execution_stats.elapsed_time_ms,
            "buffer_gets": obj.execution_stats.buffer_gets,
            "disk_reads": obj.execution_stats.disk_reads,
            "rows_processed": obj.execution_stats.rows_processed,
        }
        # Oracle性能指标
        schema = obj.execution_stats.schema
        cpu_pct = obj.execution_stats.cpu_pct
        elapsed_pct = obj.execution_stats.elapsed_pct
        elapsed_sec = obj.execution_stats.elapsed_sec
        elapsed_per_exec_sec = obj.execution_stats.elapsed_per_exec_sec

    # 根据 truncate_sql 参数决定是否截断
    if truncate_sql and len(obj.sql_text) > 500:
        sql_text = obj.sql_text[:500] + "..."
    else:
        sql_text = obj.sql_text

    return SQLObjectResponse(
        sql_id=obj.sql_id,
        sql_text=sql_text,
        schema=schema,
        source=obj.source,
        execution_stats=stats,
        has_execution_plan=obj.execution_plan is not None,
        cpu_pct=cpu_pct,
        elapsed_pct=elapsed_pct,
        elapsed_sec=elapsed_sec,
        elapsed_per_exec_sec=elapsed_per_exec_sec
    )


# ========== 路由 ==========

@router.post("/slow-sqls", response_model=List[SQLObjectResponse])
async def collect_slow_sqls(request: SlowSQLCollectionRequest):
    """
    自动采集慢SQL

    从v$sql中按资源消耗排序，获取Top N慢SQL。
    支持通过 db_source_id 指定数据源，不传则使用默认数据源。
    """
    try:
        # 创建动态客户端
        client = DynamicOracleClient()
        client.connect_to_source(request.db_source_id)

        try:
            # 创建使用动态客户端的采集器
            from app.oracle.collector import SQLCollector
            collector = SQLCollector(client)

            results = collector.collect_slow_sqls(
                top_n=request.top_n,
                cpu_threshold_ms=request.cpu_threshold_ms,
                elapsed_threshold_ms=request.elapsed_threshold_ms,
                buffer_gets_threshold=request.buffer_gets_threshold,
                exclude_system=request.exclude_system
            )

            # 获取执行计划
            for obj in results:
                if obj.sql_id:
                    try:
                        obj.execution_plan = collector.get_execution_plan(obj.sql_id)
                    except Exception as e:
                        logger.warning(f"获取执行计划失败 {obj.sql_id}: {e}")

            return [sql_object_to_response(r) for r in results]
        finally:
            client.close()

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"采集慢SQL失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"采集失败: {e}")

@router.post("/by-sql-id", response_model=SQLObjectResponse)
async def get_sql_by_id(request: SQLIdQueryRequest):
    """
    根据SQL_ID查询SQL

    查询顺序: 1. v$sql (实时缓存) 2. AWR历史数据
    支持通过 db_source_id 指定数据源，不传则使用默认数据源。
    """
    try:
        # 创建动态客户端
        client = DynamicOracleClient()
        client.connect_to_source(request.db_source_id)

        try:
            from app.oracle.collector import SQLCollector
            collector = SQLCollector(client)
            result = collector.get_sql_by_id(request.sql_id)

            if not result:
                raise HTTPException(
                    status_code=404,
                    detail=f"SQL_ID {request.sql_id} 在v$sql和AWR中都未找到"
                )

            # 获取执行计划
            if request.include_plan and result.sql_id:
                result.execution_plan = collector.get_execution_plan(result.sql_id)

            # 返回完整 SQL，不截断
            return sql_object_to_response(result, truncate_sql=False)
        finally:
            client.close()

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"SQL_ID查询失败: {e}")
        raise HTTPException(status_code=500, detail=f"查询失败: {e}")

@router.post("/upload-sql", response_model=SQLObjectResponse)
async def upload_sql(request: SQLUploadRequest):
    """
    上传SQL文本进行分析

    在测试库执行EXPLAIN PLAN获取执行计划。
    支持通过 db_source_id 指定数据源，不传则使用默认数据源。
    """
    try:
        # 创建动态客户端
        client = DynamicOracleClient()
        client.connect_to_source(request.db_source_id)

        try:
            from app.oracle.collector import SQLCollector
            collector = SQLCollector(client)

            # 生成执行计划
            plan = None
            if request.include_plan:
                plan = collector.explain_sql(request.sql_text)

            # 构建SQL对象
            sql_obj = SQLObject(
                sql_id=None,
                sql_text=request.sql_text,
                source="file_upload",
                execution_stats=None,
                execution_plan=plan
            )

            return sql_object_to_response(sql_obj, truncate_sql=False)
        finally:
            client.close()

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"SQL上传处理失败: {e}")
        raise HTTPException(status_code=400, detail=f"SQL处理失败: {e}")

@router.post("/upload-file", response_model=List[SQLObjectResponse])
async def upload_sql_file(
    file: UploadFile = File(..., description="SQL文件 (.sql, .txt)"),
    include_plan: bool = Form(True, description="是否获取执行计划"),
    db_source_id: Optional[str] = Form(None, description="数据源ID，不传则使用默认数据源")
):
    """
    上传SQL文件进行分析

    支持多行SQL，按分号分割。
    支持通过 db_source_id 指定数据源，不传则使用默认数据源。
    """
    # 检查文件类型
    allowed_extensions = {".sql", ".txt"}
    file_ext = file.filename.lower()
    if not any(file_ext.endswith(ext) for ext in allowed_extensions):
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型，请上传: {', '.join(allowed_extensions)}"
        )

    try:
        file_content = await file.read()
        text = file_content.decode("utf-8")

        # 分割SQL语句
        sql_statements = [s.strip() for s in text.split(";") if s.strip()]

        if not sql_statements:
            raise HTTPException(status_code=400, detail="文件中未找到有效的SQL语句")

        # 创建动态客户端
        client = DynamicOracleClient()
        client.connect_to_source(db_source_id)

        try:
            from app.oracle.collector import SQLCollector
            collector = SQLCollector(client)
            results = []

            for sql_text in sql_statements[:10]:  # 限制最多10条
                # 获取执行计划（失败不影响整体结果）
                plan = None
                if include_plan:
                    try:
                        plan = collector.explain_sql(sql_text)
                    except Exception as e:
                        logger.warning(f"生成执行计划失败: {e}")
                        plan = None

                sql_obj = SQLObject(
                    sql_id=None,
                    sql_text=sql_text,
                    source="file_upload",
                    execution_stats=None,
                    execution_plan=plan
                )
                results.append(sql_object_to_response(sql_obj, truncate_sql=False))

            return results
        finally:
            client.close()

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"文件上传处理失败: {e}")
        raise HTTPException(status_code=500, detail=f"文件处理失败: {e}")

@router.get("/metadata/{table_name}")
async def get_table_metadata(table_name: str, owner: Optional[str] = None):
    """
    获取表的元数据信息

    包含表信息、列信息、索引信息。
    """
    if not oracle_client.is_connected:
        raise HTTPException(status_code=503, detail="Oracle数据库未连接")

    try:
        collector = MetadataCollector(oracle_client)
        metadata = collector.get_table_metadata(table_name, owner)

        if not metadata:
            raise HTTPException(
                status_code=404,
                detail=f"表 {table_name} 未找到"
            )

        return {
            "table": {
                "name": metadata.table_info.table_name,
                "owner": metadata.table_info.owner,
                "num_rows": metadata.table_info.num_rows,
                "size_mb": metadata.table_info.table_size_mb,
            },
            "columns": [
                {
                    "name": c.column_name,
                    "type": c.data_type,
                    "nullable": c.nullable,
                }
                for c in metadata.columns
            ],
            "indexes": [
                {
                    "name": i.index_name,
                    "columns": i.columns,
                    "uniqueness": i.uniqueness,
                }
                for i in metadata.indexes
            ],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取元数据失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取元数据失败: {e}")
