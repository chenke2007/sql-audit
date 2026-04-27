"""
LLM SQL 分析模块

使用大语言模型对 SQL 进行深度分析，提供：
- 性能优化建议
- 重写建议
- 索引建议
- 问题解释
"""

import logging
import json
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings
from app.core.preprocessing import SQLStatement, format_sql

logger = logging.getLogger(__name__)


@dataclass
class LLMAnalysisResult:
    """LLM 分析结果"""
    sql_id: Optional[str]
    summary: str = ""                    # 总体评价
    issues: List[Dict] = field(default_factory=list)        # 发现的问题
    optimization_suggestions: List[str] = field(default_factory=list)  # 优化建议
    rewrite_suggestions: List[str] = field(default_factory=list)       # 重写建议
    index_suggestions: List[Dict] = field(default_factory=list)        # 索引建议
    confidence: str = "medium"           # 置信度: low/medium/high
    raw_response: str = ""               # 原始响应


class LLMClient:
    """LLM API 客户端"""

    def __init__(self):
        self.config = settings.llm
        self.client = httpx.AsyncClient(
            timeout=60.0,
            headers={"Authorization": f"Bearer {self.config.api_key}"}
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True
    )
    async def analyze_sql(
        self,
        sql_text: str,
        sql_id: Optional[str] = None,
        execution_plan: Optional[List[Dict]] = None,
        table_metadata: Optional[Dict] = None,
        rule_violations: Optional[List[Dict]] = None
    ) -> LLMAnalysisResult:
        """
        使用 LLM 分析 SQL

        Args:
            sql_text: SQL 语句
            sql_id: 可选的 SQL ID
            execution_plan: 可选的执行计划
            table_metadata: 可选的表元数据
            rule_violations: 可选的规则违规记录

        Returns:
            LLMAnalysisResult: 分析结果
        """
        # 构建提示词
        prompt = self._build_analysis_prompt(
            sql_text, execution_plan, table_metadata, rule_violations
        )

        try:
            response = await self.client.post(
                f"{self.config.base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {self.config.api_key}", "Content-Type": "application/json"},
                json={
                    "model": self.config.model_name,
                    "messages": [
                        {"role": "system", "content": self._get_system_prompt()},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.3,
                    "max_tokens": 4096
                }
            )
            response.raise_for_status()

            data = response.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")

            # 解析响应
            result = self._parse_response(sql_id, content)
            result.raw_response = content
            return result

        except httpx.HTTPStatusError as e:
            logger.error(f"LLM API HTTP 错误: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"LLM API 调用失败: {e}")
            raise

    def _get_system_prompt(self) -> str:
        """获取系统提示词"""
        return """你是一位资深的 Oracle/MySQL 数据库专家，专注于 SQL 性能优化。

你的任务是分析 SQL 语句，识别性能问题，并提供具体、可执行的优化建议。

## 分析维度
1. 执行效率：是否存在全表扫描、索引失效等问题
2. 写法优化：是否可以使用更高效的写法
3. 索引建议：哪些列需要创建索引，必须提供具体的创建索引 SQL 语句
4. 重写建议：如何改写 SQL 以获得更好的性能

## 重要规则（基于元数据）
- 检查表中是否已存在相同或类似的索引，避免建议重复创建
- 基于 num_distinct（列区分度）评估索引价值：
  - num_distinct 高（接近行数）= 高选择性，适合建索引
  - num_distinct 低（如性别只有2种值）= 低选择性，不适合单独建索引
- 基于 density 评估：density 越低表示选择性越高
- 检查 WHERE 条件列是否已有索引覆盖
- 检查 ORDER BY 列是否可利用现有索引避免排序
- 主键列和唯一约束列已有索引，无需重复建议

## 索引建议要求（非常重要）
- 必须提供具体的 CREATE INDEX 语句
- 索引命名规范：idx_表名_列名
- 考虑复合索引的最左前缀原则
- 不要建议在低选择性列（num_distinct < 10 或 density > 0.1）上单独建索引
- 如果表已有类似索引，明确指出并建议修改而非新建

## 输出要求
- 使用中文回复
- 提供具体、可执行的建议，不要泛泛而谈
- 所有建议必须包含可直接执行的 SQL 语句
- 如果发现问题，说明原因和影响
- 给出改写后的 SQL 示例

## 输出格式（必须是有效的 JSON）
{
    "summary": "总体评价（1-2句话）",
    "issues": [
        {"severity": "high/medium/low", "description": "问题描述", "impact": "性能影响"}
    ],
    "optimization_suggestions": ["建议1（包含具体SQL）", "建议2（包含具体SQL）"],
    "rewrite_suggestions": ["改写后的SQL1", "改写后的SQL2"],
    "index_suggestions": [
        {
            "table": "表名",
            "columns": ["列1", "列2"],
            "sql": "CREATE INDEX idx_表名_列1_列2 ON 表名(列1, 列2);",
            "reason": "建议原因",
            "estimate_benefit": "预计收益（如：查询性能提升50%）",
            "note": "注意：该表已有索引 idx_xxx 覆盖部分列，建议扩展而非新建"
        }
    ],
    "confidence": "high/medium/low"
}"""

    def _format_table_metadata(self, table_metadata: Dict) -> str:
        """将表元数据格式化为易读的文本"""
        text = "\n## 数据库元数据（来自真实数据源，请基于此进行分析）\n\n"

        for table_key, meta in table_metadata.items():
            text += f"### 表：{table_key}\n"
            text += f"- 行数：{meta.get('row_count', '未知')} 行"
            last_analyzed = meta.get('last_analyzed')
            if last_analyzed:
                text += f"，最近统计时间：{last_analyzed}"
            text += "\n"

            # 列信息
            columns = meta.get('columns', [])
            if columns:
                text += "- 列信息：\n"
                text += "  | 列名 | 类型 | 可空 | NDV | Density | 空值数 |\n"
                text += "  |------|------|------|-----|---------|--------|\n"
                for col in columns:
                    ndv = col.get('num_distinct', 'N/A')
                    density = col.get('density', 'N/A')
                    nulls = col.get('num_nulls', 'N/A')
                    nullable = 'Y' if col.get('nullable') else 'N'
                    text += f"  | {col['name']} | {col['type']} | {nullable} | {ndv} | {density} | {nulls} |\n"

            # 已有索引
            indexes = meta.get('indexes', [])
            if indexes:
                text += "- 已有索引：\n"
                for idx in indexes:
                    uniq = '唯一' if idx.get('uniqueness') == 'UNIQUE' else '非唯一'
                    text += f"  - {idx['name']} ({uniq})：{', '.join(idx.get('columns', []))}\n"
            else:
                text += "- 已有索引：无\n"

            # 约束
            constraints = meta.get('constraints', [])
            if constraints:
                text += "- 约束：\n"
                for cons in constraints:
                    type_map = {'P': '主键', 'U': '唯一', 'R': '外键'}
                    ctype = type_map.get(cons.get('type'), cons.get('type'))
                    text += f"  - {cons['name']} ({ctype})：{', '.join(cons.get('columns', []))}\n"

            text += "\n"

        return text

    def _build_analysis_prompt(
        self,
        sql_text: str,
        execution_plan: Optional[List[Dict]] = None,
        table_metadata: Optional[Dict] = None,
        rule_violations: Optional[List[Dict]] = None
    ) -> str:
        """构建分析提示词"""
        formatted_sql = format_sql(sql_text)

        # 限制SQL长度，避免超出模型上下文窗口
        MAX_SQL_LENGTH = 3000
        sql_truncated = False
        if len(formatted_sql) > MAX_SQL_LENGTH:
            formatted_sql = formatted_sql[:MAX_SQL_LENGTH] + "\n-- ... [SQL已截断，原长度: " + str(len(formatted_sql)) + " 字符]"
            sql_truncated = True

        prompt = f"""请分析以下 SQL 语句的性能：

## SQL 语句
```sql
{formatted_sql}
```
"""
        if sql_truncated:
            prompt += """
注意：此SQL语句较长，仅显示了前3000字符。请基于可见部分进行分析，重点关注SQL结构和潜在性能问题。
"""

        # 添加执行计划信息
        if execution_plan:
            prompt += f"""
## 执行计划
```json
{json.dumps(execution_plan, indent=2, ensure_ascii=False)[:2000]}
```
"""

        # 添加表元数据
        if table_metadata:
            prompt += self._format_table_metadata(table_metadata)


        # 添加规则违规信息
        if rule_violations:
            prompt += f"""
## 静态分析发现的问题
```json
{json.dumps(rule_violations, indent=2, ensure_ascii=False)[:1000]}
```
"""

        prompt += """
请按照系统提示中指定的 JSON 格式返回分析结果。
"""

        return prompt

    def _parse_response(self, sql_id: Optional[str], content: str) -> LLMAnalysisResult:
        """解析 LLM 响应"""
        result = LLMAnalysisResult(sql_id=sql_id)

        try:
            # 尝试提取 JSON
            json_match = self._extract_json(content)
            if json_match:
                data = json.loads(json_match)

                result.summary = data.get("summary", "")
                result.issues = data.get("issues", [])
                result.optimization_suggestions = data.get("optimization_suggestions", [])
                result.rewrite_suggestions = data.get("rewrite_suggestions", [])
                result.index_suggestions = data.get("index_suggestions", [])
                result.confidence = data.get("confidence", "medium")

                # 验证索引建议格式
                logger.info(f"LLM 返回的 index_suggestions: {result.index_suggestions}")
                for idx in result.index_suggestions:
                    logger.info(f"处理索引建议: {idx}")
                    if not idx.get("sql"):
                        logger.warning(f"索引建议缺少 sql 字段: {idx}")
                        # 尝试自动生成 SQL
                        table = idx.get("table", "")
                        columns = idx.get("columns", [])
                        if table and columns:
                            col_str = "_".join(columns)
                            idx["sql"] = f"CREATE INDEX idx_{table}_{col_str} ON {table}({', '.join(columns)});"
                            logger.info(f"自动生成索引 SQL: {idx['sql']}")
                        else:
                            logger.warning(f"无法生成 SQL，缺少 table 或 columns: table={table}, columns={columns}")
                    else:
                        logger.info(f"索引建议已有 sql 字段: {idx.get('sql')}")
            else:
                # 无法解析 JSON，将原始响应作为总结
                result.summary = content[:500] + "..." if len(content) > 500 else content
                result.confidence = "low"

        except json.JSONDecodeError as e:
            logger.warning(f"LLM 响应 JSON 解析失败: {e}")
            result.summary = content[:500] + "..." if len(content) > 500 else content
            result.confidence = "low"

        return result

    def _extract_json(self, text: str) -> Optional[str]:
        """从文本中提取 JSON"""
        # 尝试找到 JSON 代码块
        import re

        # 匹配 ```json ... ``` 格式
        json_block = re.search(r'```json\s*(.*?)```', text, re.DOTALL)
        if json_block:
            return json_block.group(1).strip()

        # 匹配 ``` ... ``` 格式
        code_block = re.search(r'```\s*(\{.*?\})\s*```', text, re.DOTALL)
        if code_block:
            return code_block.group(1).strip()

        # 尝试找到最外层的大括号内容
        try:
            start = text.find('{')
            end = text.rfind('}')
            if start >= 0 and end > start:
                return text[start:end+1]
        except:
            pass

        return None

    async def close(self):
        """关闭客户端"""
        await self.client.aclose()


class SQLAnalyzer:
    """SQL 分析器 - 结合规则和 LLM 分析"""

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm = llm_client or LLMClient()

    async def analyze(
        self,
        sql_text: str,
        sql_id: Optional[str] = None,
        execution_plan: Optional[List[Dict]] = None,
        table_metadata: Optional[Dict] = None,
        rule_result: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        综合分析 SQL

        结合规则引擎结果和 LLM 分析，提供完整的优化建议。
        """
        # 准备规则违规信息
        rule_violations = None
        if rule_result and 'violations' in rule_result:
            rule_violations = [
                {
                    "rule": v.get("rule_name"),
                    "severity": v.get("severity"),
                    "message": v.get("message")
                }
                for v in rule_result.get("violations", [])
            ]

        # 调用 LLM 分析
        try:
            llm_result = await self.llm.analyze_sql(
                sql_text=sql_text,
                sql_id=sql_id,
                execution_plan=execution_plan,
                table_metadata=table_metadata,
                rule_violations=rule_violations
            )
        except Exception as e:
            import traceback
            logger.error(f"LLM 分析失败: {e}")
            logger.error(f"LLM 错误详情: {traceback.format_exc()}")
            # 检查是否是SQL过长导致的错误
            if len(sql_text) > 5000:
                summary_msg = "SQL语句过长，LLM分析无法完成。请参考规则引擎结果，或尝试分段分析。"
            else:
                summary_msg = "LLM 分析暂时不可用，请参考规则引擎结果"
            llm_result = LLMAnalysisResult(
                sql_id=sql_id,
                summary=summary_msg,
                confidence="low"
            )

        # 合并结果
        return {
            "sql_id": sql_id,
            "rule_summary": rule_result.get("summary", {}) if rule_result else {},
            "llm_analysis": {
                "summary": llm_result.summary,
                "issues": llm_result.issues,
                "optimization_suggestions": llm_result.optimization_suggestions,
                "rewrite_suggestions": llm_result.rewrite_suggestions,
                "index_suggestions": llm_result.index_suggestions,
                "confidence": llm_result.confidence
            },
            "combined_recommendations": self._merge_recommendations(
                rule_result.get("violations", []) if rule_result else [],
                llm_result
            )
        }

    def _merge_recommendations(
        self,
        violations: List[Dict],
        llm_result: LLMAnalysisResult
    ) -> List[Dict]:
        """合并规则引擎和 LLM 的推荐"""
        recommendations = []

        # 添加规则违规作为高优先级推荐
        for v in violations:
            if v.get("severity") in ["critical", "high"]:
                recommendations.append({
                    "source": "rule_engine",
                    "priority": "high",
                    "category": v.get("category"),
                    "title": v.get("rule_name"),
                    "description": v.get("message"),
                    "suggestion": v.get("suggestion")
                })

        # 添加 LLM 建议
        for issue in llm_result.issues:
            recommendations.append({
                "source": "llm",
                "priority": issue.get("severity", "medium"),
                "category": "llm_analysis",
                "title": "AI 发现的问题",
                "description": issue.get("description", ""),
                "impact": issue.get("impact", "")
            })

        # 添加索引建议
        for idx in llm_result.index_suggestions:
            recommendations.append({
                "source": "llm",
                "priority": "medium",
                "category": "index",
                "title": f"建议在表 {idx.get('table')} 上创建索引",
                "description": f"列: {', '.join(idx.get('columns', []))}",
                "reason": idx.get("reason", "")
            })

        return recommendations


# 全局分析器实例
sql_analyzer = SQLAnalyzer()
