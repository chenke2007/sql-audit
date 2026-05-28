"""
SQL 分析 API 路由

提供 SQL 分析相关的 HTTP 接口:
1. 规则引擎分析
2. LLM 智能分析
3. 综合分析（规则 + LLM）
"""

import asyncio
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, HTTPException, BackgroundTasks, Response, Depends
from pydantic import BaseModel, Field

from app.core import rule_engine, sql_analyzer, preprocess_sql
from app.core.rbac import get_current_user, require_permission
from app.core.database import DBSourceManager
from app.exporters import registry
from app.oracle.client import oracle_client, OracleConnectionError, OracleQueryError
from app.oracle.collector import SQLCollector
from app.core.dynamic_db_client import DynamicOracleClient
from app.api.routes.analysis_history import save_analysis_history

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/analyze", tags=["SQL分析"])


# ========== 数据模型 ==========

class AnalyzeRequest(BaseModel):
    """SQL 分析请求"""
    db_source_id: Optional[str] = Field(None, description="数据源ID，不传则使用默认数据源")
    schema_name: Optional[str] = Field(None, alias="schema", description="Schema/Owner，不传则使用SQL中指定的schema")
    sql_text: str = Field(..., min_length=1, description="SQL语句文本")
    sql_id: Optional[str] = Field(None, description="可选的SQL ID")
    use_llm: bool = Field(True, description="是否使用LLM分析")
    use_rules: bool = Field(True, description="是否使用规则引擎分析")
    include_plan: bool = Field(True, description="是否包含执行计划分析")
    existing_result: Optional[Dict[str, Any]] = Field(None, description="已有的分析结果，传入则直接使用而非重新分析")


class RuleViolationResponse(BaseModel):
    """规则违规响应"""
    rule_id: str
    rule_name: str
    category: str
    severity: str
    message: str
    suggestion: str
    location: Optional[str] = None


class LLMAnalysisResponse(BaseModel):
    """LLM 分析响应"""
    summary: str
    issues: List[Dict[str, Any]] = []
    optimization_suggestions: List[str] = []
    rewrite_suggestions: List[str] = []
    index_suggestions: List[Dict[str, Any]] = []
    confidence: str


class AnalysisResultResponse(BaseModel):
    """分析结果响应"""
    sql_id: Optional[str]
    sql_text: Optional[str] = None
    sql_type: str
    tables: List[str]
    risk_level: Optional[str] = None  # CRITICAL, HIGH, MEDIUM, LOW
    rule_violations: List[RuleViolationResponse] = []
    llm_analysis: Optional[LLMAnalysisResponse] = None
    recommendations: List[Dict[str, Any]] = []


class BatchAnalyzeRequest(BaseModel):
    """批量分析请求"""
    sql_list: List[AnalyzeRequest]


class BatchAnalyzeResponse(BaseModel):
    """批量分析响应"""
    results: List[AnalysisResultResponse]
    summary: Dict[str, int]


class ExportRequest(AnalyzeRequest):
    """导出请求 - 继承分析请求，增加格式参数"""
    format: str = Field("pdf", description="导出格式: pdf, html, markdown")


# ========== 辅助函数 ==========

def _get_execution_plan(sql_id: str, client=None) -> Optional[Dict[str, Any]]:
    """获取 SQL 的执行计划（从 v$sql 缓存中获取真实执行计划）"""
    # 使用传入的客户端或默认客户端
    if client is None:
        if not oracle_client.is_connected:
            return None
        client = oracle_client

    try:
        collector = SQLCollector(client)
        plan = collector.get_execution_plan(sql_id)
        if plan:
            return {
                "sql_id": plan.sql_id,
                "plan_hash_value": plan.plan_hash_value,
                "plan_text": plan.plan_text,
                "operations": plan.operations
            }
        return None
    except Exception as e:
        logger.warning(f"获取执行计划失败: {e}")
        return None


def _explain_sql(sql_text: str, client=None) -> Optional[Dict[str, Any]]:
    """通过 EXPLAIN PLAN 为 SQL 文本生成执行计划"""
    # 使用传入的客户端或默认客户端
    if client is None:
        if not oracle_client.is_connected:
            return None
        client = oracle_client

    try:
        collector = SQLCollector(client)
        plan = collector.explain_sql(sql_text)
        if plan:
            return {
                "sql_id": plan.sql_id,
                "plan_hash_value": plan.plan_hash_value,
                "plan_text": plan.plan_text,
                "operations": plan.operations
            }
        return None
    except Exception as e:
        logger.warning(f"通过 EXPLAIN PLAN 生成执行计划失败: {e}")
        return None


def _get_table_metadata(tables, schema: Optional[str] = None, client=None) -> Dict[str, Any]:
    """获取表元数据

    Args:
        tables: 表引用列表 (TableRef 或 str)
        schema: 默认 schema，当表没有指定 schema 时使用
        client: 数据库客户端
    """
    # 使用传入的客户端或默认客户端
    if client is None:
        if not oracle_client.is_connected or not tables:
            return {}
        client = oracle_client
    elif not tables:
        return {}

    from app.oracle.metadata import MetadataCollector
    from app.core.preprocessing import TableRef

    metadata = {}
    collector = MetadataCollector(client)

    for table_ref in tables[:5]:  # 限制最多5张表
        try:
            # 处理 TableRef 或字符串
            if isinstance(table_ref, TableRef):
                table_name = table_ref.name
                table_schema = table_ref.schema or schema
            else:
                table_name = table_ref
                table_schema = schema

            meta = collector.get_table_metadata(table_name, owner=table_schema)
            if meta:
                key = f"{table_schema}.{table_name}" if table_schema else table_name
                metadata[key] = {
                    "table_name": meta.table_info.table_name,
                    "owner": meta.table_info.owner,
                    "row_count": meta.table_info.num_rows,
                    "size_mb": meta.table_info.table_size_mb,
                    "last_analyzed": meta.table_info.last_analyzed,
                    "columns": [
                        {"name": c.column_name, "type": c.data_type,
                         "nullable": c.nullable, "data_length": c.data_length,
                         "num_distinct": c.num_distinct, "density": c.density,
                         "num_nulls": c.num_nulls, "last_analyzed": c.last_analyzed}
                        for c in meta.columns
                    ],
                    "indexes": [
                        {"name": i.index_name, "columns": i.columns,
                         "uniqueness": i.uniqueness, "index_type": i.index_type}
                        for i in meta.indexes
                    ],
                    "constraints": [
                        {"name": c.constraint_name, "type": c.constraint_type,
                         "columns": c.columns}
                        for c in meta.constraints
                    ]
                }
        except Exception as e:
            logger.warning(f"获取表 {table_ref} 元数据失败: {e}")

    return metadata


def _calculate_risk_level(violations, llm_analysis) -> str:
    """计算风险等级"""
    severity_scores = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    max_score = 0

    # 检查规则违规
    for v in violations:
        score = severity_scores.get(v.severity.lower(), 0)
        max_score = max(max_score, score)

    # 检查 LLM 分析的问题
    if llm_analysis and hasattr(llm_analysis, 'issues') and llm_analysis.issues:
        for issue in llm_analysis.issues:
            severity = issue.get("severity", "").lower() if isinstance(issue, dict) else getattr(issue, 'severity', '').lower()
            score = severity_scores.get(severity, 0)
            max_score = max(max_score, score)

    # 映射风险等级
    if max_score >= 4:
        return "CRITICAL"
    elif max_score >= 3:
        return "HIGH"
    elif max_score >= 2:
        return "MEDIUM"
    else:
        return "LOW"


# ========== 路由 ==========

@router.post("/single", response_model=AnalysisResultResponse)
async def analyze_sql(
    request: AnalyzeRequest,
    current_user: dict = Depends(require_permission("analysis:execute"))
):
    """
    单条 SQL 分析

    结合规则引擎和 LLM 对 SQL 进行全面分析。
    支持通过 db_source_id 指定数据源，不传则使用默认数据源。
    """
    # 检查数据源权限
    if request.db_source_id:
        from app.core.rbac import has_datasource_permission
        if not has_datasource_permission(current_user["id"], request.db_source_id):
            raise HTTPException(status_code=403, detail="没有权限使用此数据源")

    # 创建动态客户端
    client = None
    try:
        client = DynamicOracleClient()

        # 连接数据库（异步线程 + 超时，防止阻塞事件循环）
        try:
            await asyncio.wait_for(
                asyncio.to_thread(client.connect_to_source, request.db_source_id, timeout=8),
                timeout=10
            )
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="连接数据源超时，请检查网络或数据源配置")

        # 预处理 SQL
        try:
            parsed = preprocess_sql(request.sql_text)
        except Exception as e:
            logger.error(f"SQL 预处理失败: {e}")
            raise HTTPException(status_code=400, detail=f"SQL 解析失败: {e}")

        result = AnalysisResultResponse(
            sql_id=request.sql_id,
            sql_text=request.sql_text,
            sql_type=parsed.sql_type.value,
            tables=[t.full_name() for t in parsed.tables],
            rule_violations=[],
            recommendations=[]
        )

        # ===== 统一获取执行计划和表元数据（只获取一次，供规则引擎和 LLM 共用）=====
        shared_execution_plan = None
        shared_table_metadata = None

        if request.include_plan:
            def _fetch_plan():
                if request.sql_id:
                    return _get_execution_plan(request.sql_id, client)
                else:
                    return _explain_sql(request.sql_text, client)

            try:
                shared_execution_plan = await asyncio.wait_for(
                    asyncio.to_thread(_fetch_plan),
                    timeout=10
                )
            except asyncio.TimeoutError:
                logger.warning("获取执行计划超时")

        if parsed.tables:
            def _fetch_metadata():
                return _get_table_metadata(
                    list(parsed.tables), schema=request.schema_name, client=client
                )

            try:
                shared_table_metadata = await asyncio.wait_for(
                    asyncio.to_thread(_fetch_metadata),
                    timeout=10
                )
            except asyncio.TimeoutError:
                logger.warning("获取表元数据超时")

        # 规则引擎分析
        rule_result = None
        if request.use_rules:
            try:
                context = {}
                if shared_execution_plan:
                    context["execution_plan"] = shared_execution_plan
                if shared_table_metadata:
                    context["table_metadata"] = shared_table_metadata

                rule_result = rule_engine.analyze(request.sql_text, request.sql_id, context)

                # 转换违规记录
                for v in rule_result.violations:
                    result.rule_violations.append(RuleViolationResponse(
                        rule_id=v.rule_id,
                        rule_name=v.rule_name,
                        category=v.category.value,
                        severity=v.severity.value,
                        message=v.message,
                        suggestion=v.suggestion,
                        location=v.location
                    ))

            except Exception as e:
                logger.error(f"规则引擎分析失败: {e}")

        # LLM 分析（直接复用已获取的执行计划和元数据，避免重复查询）
        if request.use_llm:
            try:
                # 准备规则结果
                rule_result_dict = None
                if rule_result:
                    rule_result_dict = {
                        "violations": [
                            {
                                "rule_name": v.rule_name,
                                "category": v.category.value,
                                "severity": v.severity.value,
                                "message": v.message,
                                "suggestion": v.suggestion
                            }
                            for v in rule_result.violations
                        ]
                    }

                analysis = await sql_analyzer.analyze(
                    sql_text=request.sql_text,
                    sql_id=request.sql_id,
                    execution_plan=shared_execution_plan,
                    table_metadata=shared_table_metadata,
                    rule_result=rule_result_dict
                )

                llm_data = analysis.get("llm_analysis", {})
                result.llm_analysis = LLMAnalysisResponse(
                    summary=llm_data.get("summary", ""),
                    issues=llm_data.get("issues", []),
                    optimization_suggestions=llm_data.get("optimization_suggestions", []),
                    rewrite_suggestions=llm_data.get("rewrite_suggestions", []),
                    index_suggestions=llm_data.get("index_suggestions", []),
                    confidence=llm_data.get("confidence", "medium")
                )

                # 合并推荐
                result.recommendations = analysis.get("combined_recommendations", [])

            except Exception as e:
                logger.error(f"LLM 分析失败: {e}")
                # LLM 失败时不阻断，返回规则引擎结果

        # 计算风险等级
        result.risk_level = _calculate_risk_level(result.rule_violations, result.llm_analysis)

        # 保存分析历史
        try:
            await save_analysis_history(
                user_id=current_user["id"],
                db_source_id=request.db_source_id,
                schema=request.schema_name,
                sql_text=request.sql_text,
                sql_id=request.sql_id,
                input_mode="sql_text",
                result=result.model_dump() if hasattr(result, "model_dump") else result.__dict__,
                risk_level=result.risk_level
            )
        except Exception as e:
            logger.warning(f"保存分析历史失败: {e}")

        return result

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        if client:
            client.close()


@router.post("/by-sql-id")
async def analyze_by_sql_id(
    sql_id: str,
    use_llm: bool = True,
    db_source_id: Optional[str] = None,
    current_user: dict = Depends(require_permission("analysis:execute"))
):
    """
    通过 SQL_ID 分析 SQL

    自动从数据库获取 SQL 文本和执行计划进行分析。
    支持通过 db_source_id 指定数据源，不传则使用默认数据源。
    """
    # 检查数据源权限
    if db_source_id:
        from app.core.rbac import has_datasource_permission
        if not has_datasource_permission(current_user["id"], db_source_id):
            raise HTTPException(status_code=403, detail="没有权限使用此数据源")

    try:
        # 创建动态客户端
        client = DynamicOracleClient()

        # 连接数据库（异步线程 + 超时）
        try:
            await asyncio.wait_for(
                asyncio.to_thread(client.connect_to_source, db_source_id, timeout=8),
                timeout=10
            )
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="连接数据源超时，请检查网络或数据源配置")

        try:
            from app.oracle.collector import SQLCollector
            collector = SQLCollector(client)

            # 获取 SQL（异步线程 + 超时）
            def _fetch_sql():
                return collector.get_sql_by_id(sql_id)

            try:
                sql_obj = await asyncio.wait_for(
                    asyncio.to_thread(_fetch_sql),
                    timeout=10
                )
            except asyncio.TimeoutError:
                raise HTTPException(status_code=504, detail="查询 SQL 信息超时，请检查网络或数据源配置")

            if not sql_obj:
                raise HTTPException(
                    status_code=404,
                    detail=f"SQL_ID {sql_id} 未找到"
                )

            # 调用单条分析
            request = AnalyzeRequest(
                db_source_id=db_source_id,
                sql_text=sql_obj.sql_text,
                sql_id=sql_id,
                use_llm=use_llm,
                include_plan=True
            )

            result = await analyze_sql(request, current_user)

            # 保存分析历史
            try:
                await save_analysis_history(
                    user_id=current_user["id"],
                    db_source_id=db_source_id,
                    schema=None,
                    sql_text=sql_obj.sql_text,
                    sql_id=sql_id,
                    input_mode="sql_id",
                    result=result.model_dump() if hasattr(result, "model_dump") else result.__dict__,
                    risk_level=result.risk_level
                )
            except Exception as e:
                logger.warning(f"保存分析历史失败: {e}")

            return result
        finally:
            client.close()

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"SQL_ID 分析失败: {e}")
        raise HTTPException(status_code=500, detail=f"分析失败: {e}")

@router.post("/batch", response_model=BatchAnalyzeResponse)
async def analyze_batch(
    request: BatchAnalyzeRequest,
    current_user: dict = Depends(require_permission("analysis:execute"))
):
    """
    批量 SQL 分析

    同时分析多条 SQL，返回汇总结果。
    """
    results = []
    summary = {"total": 0, "critical": 0, "high": 0, "medium": 0, "low": 0}

    for item in request.sql_list[:20]:  # 限制最多20条
        try:
            result = await analyze_sql(item)
            results.append(result)

            # 统计
            summary["total"] += 1
            for v in result.rule_violations:
                severity = v.severity
                if severity in summary:
                    summary[severity] += 1

        except Exception as e:
            logger.error(f"批量分析中某条 SQL 失败: {e}")
            # 继续处理下一条

    return BatchAnalyzeResponse(results=results, summary=summary)


@router.get("/rules")
async def list_rules():
    """
    列出所有可用的分析规则
    """
    rules = []
    for rule in rule_engine.rules:
        rules.append({
            "rule_id": rule.rule_id,
            "name": rule.name,
            "description": rule.description,
            "category": rule.category.value,
            "severity": rule.severity.value,
            "enabled": rule.enabled
        })

    return {"rules": rules, "total": len(rules)}


@router.post("/rules/{rule_id}/toggle")
async def toggle_rule(
    rule_id: str,
    enabled: bool,
    current_user: dict = Depends(require_permission("analysis:execute"))
):
    """
    启用/禁用规则
    """
    if rule_id not in [r.rule_id for r in rule_engine.rules]:
        raise HTTPException(status_code=404, detail=f"规则 {rule_id} 不存在")

    if enabled:
        rule_engine.enable_rule(rule_id)
    else:
        rule_engine.disable_rule(rule_id)

    return {"rule_id": rule_id, "enabled": enabled}


@router.get("/export/formats")
async def list_export_formats():
    """
    列出所有可用的导出格式
    """
    return {"formats": registry.list_formats()}


@router.post("/export")
async def export_analysis(
    request: ExportRequest,
    current_user: dict = Depends(require_permission("analysis:execute"))
):
    """
    统一导出接口 - 支持 PDF、HTML、Markdown 格式

    通过 format 参数指定导出格式。
    如果请求中包含 existing_result，则直接使用该结果生成报告。
    """
    try:
        # 获取导出器
        exporter = registry.get(request.format)
        if not exporter:
            available = registry.list_formats()
            raise HTTPException(
                status_code=400,
                detail=f"不支持的导出格式: {request.format}。可用格式: {[f['name'] for f in available]}"
            )

        # 准备分析结果字典
        if request.existing_result:
            result_dict = {
                "sql_id": request.existing_result.get("sql_id"),
                "sql_type": request.existing_result.get("sql_type", "N/A"),
                "sql_text": request.sql_text,
                "tables": request.existing_result.get("tables", []),
                "rule_violations": request.existing_result.get("rule_violations", []),
                "llm_analysis": request.existing_result.get("llm_analysis"),
                "recommendations": request.existing_result.get("recommendations", [])
            }
            sql_id = result_dict["sql_id"] or 'unknown'
        else:
            result = await analyze_sql(request)
            result_dict = {
                "sql_id": result.sql_id,
                "sql_type": result.sql_type,
                "sql_text": request.sql_text,
                "tables": result.tables,
                "rule_violations": [v.model_dump() for v in result.rule_violations],
                "llm_analysis": result.llm_analysis.model_dump() if result.llm_analysis else None,
                "recommendations": result.recommendations
            }
            sql_id = result.sql_id or 'unknown'

        # 执行导出
        export_result = registry.export(request.format, result_dict)
        filename = export_result.generate_filename(sql_id)

        return Response(
            content=export_result.content,
            media_type=export_result.content_type,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error(f"导出失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"导出失败: {e}")


@router.post("/export/pdf")
async def export_analysis_pdf(
    request: AnalyzeRequest,
    current_user: dict = Depends(require_permission("analysis:execute"))
):
    """
    导出分析结果为 PDF（兼容旧接口）

    此接口保留用于向后兼容，内部调用统一导出接口。
    """
    try:
        export_request = ExportRequest(**request.model_dump(), format="pdf")
        return await export_analysis(export_request)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"PDF 导出兼容层失败: {e}")
        raise HTTPException(status_code=500, detail=f"PDF 导出失败: {e}")


@router.post("/export/pdf/by-sql-id")
async def export_analysis_pdf_by_sql_id(
    sql_id: str,
    use_llm: bool = True,
    use_rules: bool = True,
    db_source_id: Optional[str] = None,
    current_user: dict = Depends(require_permission("analysis:execute"))
):
    """
    通过 SQL_ID 导出分析结果为 PDF

    自动从数据库获取 SQL 文本和执行计划进行分析并导出 PDF。
    支持通过 db_source_id 指定数据源，不传则使用默认数据源。
    """
    client = None
    try:
        client = DynamicOracleClient()
        client.connect_to_source(db_source_id)

        collector = SQLCollector(client)
        sql_obj = collector.get_sql_by_id(sql_id)

        if not sql_obj:
            raise HTTPException(
                status_code=404,
                detail=f"SQL_ID {sql_id} 未找到"
            )

        # 调用单条分析
        request = AnalyzeRequest(
            sql_text=sql_obj.sql_text,
            sql_id=sql_id,
            use_llm=use_llm,
            use_rules=use_rules,
            include_plan=True
        )

        return await export_analysis_pdf(request)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"SQL_ID PDF 导出失败: {e}")
        raise HTTPException(status_code=500, detail=f"导出失败: {e}")
    finally:
        if client:
            client.close()
