"""
SQL 分析 API 路由

提供 SQL 分析相关的 HTTP 接口:
1. 规则引擎分析
2. LLM 智能分析
3. 综合分析（规则 + LLM）
"""

import logging
from datetime import datetime
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, HTTPException, BackgroundTasks, Response
from pydantic import BaseModel, Field

from app.core import rule_engine, sql_analyzer, preprocess_sql
from app.core.pdf_exporter import pdf_exporter
from app.oracle.client import oracle_client, OracleConnectionError, OracleQueryError
from app.oracle.collector import SQLCollector
from app.core.dynamic_db_client import DynamicOracleClient
from app.core.database import DBSourceManager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/analyze", tags=["SQL分析"])


# ========== 数据模型 ==========

class AnalyzeRequest(BaseModel):
    """SQL 分析请求"""
    db_source_id: Optional[str] = Field(None, description="数据源ID，不传则使用默认数据源")
    sql_text: str = Field(..., min_length=1, description="SQL语句文本")
    sql_id: Optional[str] = Field(None, description="可选的SQL ID")
    use_llm: bool = Field(True, description="是否使用LLM分析")
    use_rules: bool = Field(True, description="是否使用规则引擎分析")
    include_plan: bool = Field(True, description="是否包含执行计划分析")


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


# ========== 辅助函数 ==========

def _get_execution_plan(sql_id: str, client=None) -> Optional[List[Dict]]:
    """获取 SQL 的执行计划"""
    # 使用传入的客户端或默认客户端
    if client is None:
        if not oracle_client.is_connected:
            return None
        client = oracle_client

    try:
        collector = SQLCollector(client)
        plan = collector.get_execution_plan(sql_id)
        return plan
    except Exception as e:
        logger.warning(f"获取执行计划失败: {e}")
        return None


def _get_table_metadata(tables: List[str], client=None) -> Dict[str, Any]:
    """获取表元数据"""
    # 使用传入的客户端或默认客户端
    if client is None:
        if not oracle_client.is_connected or not tables:
            return {}
        client = oracle_client
    elif not tables:
        return {}

    from app.oracle.metadata import MetadataCollector

    metadata = {}
    collector = MetadataCollector(client)

    for table in tables[:5]:  # 限制最多5张表
        try:
            meta = collector.get_table_metadata(table)
            if meta:
                metadata[table] = {
                    "row_count": meta.table_info.num_rows,
                    "size_mb": meta.table_info.table_size_mb,
                    "columns": [
                        {"name": c.column_name, "type": c.data_type}
                        for c in meta.columns
                    ],
                    "indexes": [
                        {"name": i.index_name, "columns": i.columns}
                        for i in meta.indexes
                    ]
                }
        except Exception as e:
            logger.warning(f"获取表 {table} 元数据失败: {e}")

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
async def analyze_sql(request: AnalyzeRequest):
    """
    单条 SQL 分析

    结合规则引擎和 LLM 对 SQL 进行全面分析。
    支持通过 db_source_id 指定数据源，不传则使用默认数据源。
    """
    # 创建动态客户端
    client = None
    try:
        client = DynamicOracleClient()
        client.connect_to_source(request.db_source_id)

        # 预处理 SQL
        try:
            parsed = preprocess_sql(request.sql_text)
        except Exception as e:
            logger.error(f"SQL 预处理失败: {e}")
            raise HTTPException(status_code=400, detail=f"SQL 解析失败: {e}")

        result = AnalysisResultResponse(
            sql_id=request.sql_id,
            sql_type=parsed.sql_type.value,
            tables=list(parsed.tables),
            rule_violations=[],
            recommendations=[]
        )

        # 规则引擎分析
        rule_result = None
        if request.use_rules:
            try:
                context = {}

                # 如果有 SQL ID，获取执行计划
                if request.include_plan and request.sql_id:
                    plan = _get_execution_plan(request.sql_id, client)
                    if plan:
                        context["execution_plan"] = plan

                # 获取表元数据
                if parsed.tables:
                    metadata = _get_table_metadata(list(parsed.tables), client)
                    if metadata:
                        context["table_metadata"] = metadata

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

        # LLM 分析
        if request.use_llm:
            try:
                # 准备执行计划和元数据
                execution_plan = None
                table_metadata = None

                if request.include_plan and request.sql_id:
                    execution_plan = _get_execution_plan(request.sql_id, client)

                if parsed.tables:
                    table_metadata = _get_table_metadata(list(parsed.tables), client)

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
                    execution_plan=execution_plan,
                    table_metadata=table_metadata,
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
    db_source_id: Optional[str] = None
):
    """
    通过 SQL_ID 分析 SQL

    自动从数据库获取 SQL 文本和执行计划进行分析。
    支持通过 db_source_id 指定数据源，不传则使用默认数据源。
    """
    try:
        # 创建动态客户端
        client = DynamicOracleClient()
        client.connect_to_source(db_source_id)

        try:
            from app.oracle.collector import SQLCollector
            collector = SQLCollector(client)
            sql_obj = collector.get_sql_by_id(sql_id)

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

            return await analyze_sql(request)
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
async def analyze_batch(request: BatchAnalyzeRequest):
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
async def toggle_rule(rule_id: str, enabled: bool):
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


@router.post("/export/pdf")
async def export_analysis_pdf(request: AnalyzeRequest):
    """
    导出分析结果为 PDF

    执行 SQL 分析并将结果导出为 PDF 报告。
    """
    try:
        # 执行分析
        result = await analyze_sql(request)

        # 转换为字典格式
        result_dict = {
            "sql_id": result.sql_id,
            "sql_type": result.sql_type,
            "sql_text": request.sql_text,
            "tables": result.tables,
            "rule_violations": [v.model_dump() for v in result.rule_violations],
            "llm_analysis": result.llm_analysis.model_dump() if result.llm_analysis else None,
            "recommendations": result.recommendations
        }

        # 生成 PDF
        pdf_data = pdf_exporter.export_analysis_report(result_dict)

        # 生成文件名
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        sql_id = result.sql_id or 'unknown'
        filename = f"sql_audit_report_{sql_id}_{timestamp}.pdf"

        return Response(
            content=pdf_data,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"PDF 导出失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"PDF 导出失败: {e}")


@router.post("/export/pdf/by-sql-id")
async def export_analysis_pdf_by_sql_id(
    sql_id: str,
    use_llm: bool = True,
    use_rules: bool = True
):
    """
    通过 SQL_ID 导出分析结果为 PDF

    自动从数据库获取 SQL 文本和执行计划进行分析并导出 PDF。
    """
    if not oracle_client.is_connected:
        raise HTTPException(status_code=503, detail="Oracle数据库未连接")

    try:
        collector = SQLCollector(oracle_client)
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

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"SQL_ID PDF 导出失败: {e}")
        raise HTTPException(status_code=500, detail=f"导出失败: {e}")
