"""
SQL 规则引擎

基于预定义规则对 SQL 进行静态分析，检测常见问题：
- 缺失索引
- 全表扫描风险
- 隐式转换
- 低效写法
- 等等
"""

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Any, Set
from abc import ABC, abstractmethod

from app.core.preprocessing import SQLStatement, SQLType, SQLParser

logger = logging.getLogger(__name__)


class RuleSeverity(Enum):
    """规则严重程度"""
    CRITICAL = "critical"      # 严重问题，必须修复
    HIGH = "high"              # 高风险，建议修复
    MEDIUM = "medium"          # 中风险，可以优化
    LOW = "low"                # 低风险，参考建议
    INFO = "info"              # 信息提示


class RuleCategory(Enum):
    """规则类别"""
    INDEX = "index"            # 索引相关
    QUERY_STRUCTURE = "query"  # 查询结构
    PERFORMANCE = "perf"       # 性能相关
    SECURITY = "security"      # 安全相关
    BEST_PRACTICE = "practice" # 最佳实践


@dataclass
class RuleViolation:
    """规则违规记录"""
    rule_id: str
    rule_name: str
    category: RuleCategory
    severity: RuleSeverity
    message: str
    suggestion: str
    location: Optional[str] = None  # 问题位置描述
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RuleCheckResult:
    """规则检查结果"""
    sql_id: Optional[str]
    violations: List[RuleViolation] = field(default_factory=list)
    summary: Dict[str, int] = field(default_factory=dict)

    def add_violation(self, violation: RuleViolation):
        self.violations.append(violation)
        # 更新统计
        key = violation.severity.value
        self.summary[key] = self.summary.get(key, 0) + 1


class SQLRule(ABC):
    """SQL 规则基类"""

    def __init__(
        self,
        rule_id: str,
        name: str,
        description: str,
        category: RuleCategory,
        severity: RuleSeverity,
        enabled: bool = True
    ):
        self.rule_id = rule_id
        self.name = name
        self.description = description
        self.category = category
        self.severity = severity
        self.enabled = enabled

    @abstractmethod
    def check(self, sql: SQLStatement, context: Optional[Dict] = None) -> Optional[RuleViolation]:
        """
        检查 SQL 是否违反此规则

        Args:
            sql: 解析后的 SQL 语句
            context: 额外上下文（如元数据、执行计划等）

        Returns:
            违规记录，如果没有违规则返回 None
        """
        pass

    def is_applicable(self, sql: SQLStatement) -> bool:
        """判断该规则是否适用于此 SQL 类型"""
        return True


# ==================== 具体规则实现 ====================

class SelectStarRule(SQLRule):
    """禁止 SELECT * 规则"""

    def __init__(self):
        super().__init__(
            rule_id="R001",
            name="避免 SELECT *",
            description="SELECT * 会导致不必要的列传输，增加网络和内存开销",
            category=RuleCategory.BEST_PRACTICE,
            severity=RuleSeverity.MEDIUM
        )

    def is_applicable(self, sql: SQLStatement) -> bool:
        return sql.sql_type == SQLType.SELECT

    def check(self, sql: SQLStatement, context: Optional[Dict] = None) -> Optional[RuleViolation]:
        if re.search(r'\bSELECT\s+\*', sql.normalized_sql, re.IGNORECASE):
            return RuleViolation(
                rule_id=self.rule_id,
                rule_name=self.name,
                category=self.category,
                severity=self.severity,
                message="检测到 SELECT *，建议明确指定所需列",
                suggestion="列出具体需要的列名，避免传输不必要的数据，减少内存和网络开销"
            )
        return None


class MissingWhereRule(SQLRule):
    """UPDATE/DELETE 缺少 WHERE 子句规则"""

    def __init__(self):
        super().__init__(
            rule_id="R002",
            name="缺少 WHERE 子句",
            description="UPDATE 或 DELETE 语句缺少 WHERE 子句可能导致全表更新/删除",
            category=RuleCategory.SECURITY,
            severity=RuleSeverity.CRITICAL
        )

    def is_applicable(self, sql: SQLStatement) -> bool:
        return sql.sql_type in (SQLType.UPDATE, SQLType.DELETE)

    def check(self, sql: SQLStatement, context: Optional[Dict] = None) -> Optional[RuleViolation]:
        if not re.search(r'\bWHERE\b', sql.normalized_sql, re.IGNORECASE):
            return RuleViolation(
                rule_id=self.rule_id,
                rule_name=self.name,
                category=self.category,
                severity=self.severity,
                message=f"{sql.sql_type.value} 语句缺少 WHERE 子句",
                suggestion="添加 WHERE 子句限定影响范围，或在 WHERE 1=1 中明确说明需要全表操作"
            )
        return None


class ImplicitConversionRule(SQLRule):
    """隐式类型转换检测规则"""

    # 常见的隐式转换模式
    IMPLICIT_PATTERNS = [
        # 数字列与字符串比较
        (r'\w+_ID\s*=\s*[\'"]\d+[\'"]', "ID 列与字符串值比较"),
        (r'\w+_ID\s*=\s*\w+\s*\|\|\s*[\'"]', "ID 列与拼接字符串比较"),
        # 日期列与字符串比较
        (r'DATE\w*\s*[=<>]\s*[\'"]\d{4}-\d{2}-\d{2}[\'"]', "日期列与字符串直接比较"),
        # 函数导致索引失效
        (r'UPPER\s*\(\s*\w+\s*\)\s*=', "对列使用 UPPER 函数会导致索引失效"),
        (r'LOWER\s*\(\s*\w+\s*\)\s*=', "对列使用 LOWER 函数会导致索引失效"),
        (r'TRUNC\s*\(\s*\w+\s*\)', "对列使用 TRUNC 函数会导致索引失效"),
    ]

    def __init__(self):
        super().__init__(
            rule_id="R003",
            name="隐式类型转换",
            description="隐式类型转换或函数作用于列会导致索引失效",
            category=RuleCategory.PERFORMANCE,
            severity=RuleSeverity.HIGH
        )

    def check(self, sql: SQLStatement, context: Optional[Dict] = None) -> Optional[RuleViolation]:
        violations = []

        for pattern, desc in self.IMPLICIT_PATTERNS:
            if re.search(pattern, sql.normalized_sql, re.IGNORECASE):
                violations.append(desc)

        if violations:
            return RuleViolation(
                rule_id=self.rule_id,
                rule_name=self.name,
                category=self.category,
                severity=self.severity,
                message=f"检测到可能的隐式转换或函数作用于列: {', '.join(violations[:2])}",
                suggestion="避免对索引列使用函数，使用绑定变量确保类型匹配，日期使用 TO_DATE 函数"
            )
        return None


class LikePrefixRule(SQLRule):
    """LIKE 前模糊匹配检测"""

    def __init__(self):
        super().__init__(
            rule_id="R004",
            name="LIKE 前模糊匹配",
            description="LIKE '%xxx' 前模糊匹配无法使用索引",
            category=RuleCategory.PERFORMANCE,
            severity=RuleSeverity.HIGH
        )

    def check(self, sql: SQLStatement, context: Optional[Dict] = None) -> Optional[RuleViolation]:
        # 检测 LIKE '%...' 模式
        if re.search(r"LIKE\s+[\'\"]%", sql.normalized_sql, re.IGNORECASE):
            return RuleViolation(
                rule_id=self.rule_id,
                rule_name=self.name,
                category=self.category,
                severity=self.severity,
                message="检测到 LIKE 前模糊匹配 (LIKE '%xxx')",
                suggestion="前模糊匹配无法使用索引，考虑: 1) 使用后模糊匹配 LIKE 'xxx%' 2) 使用反向索引 3) 使用 Oracle Text 全文检索"
            )
        return None


class InClauseCountRule(SQLRule):
    """IN 子句元素数量检测"""

    def __init__(self, max_count: int = 1000):
        super().__init__(
            rule_id="R005",
            name="IN 子句元素过多",
            description="IN 子句包含过多元素会影响性能",
            category=RuleCategory.PERFORMANCE,
            severity=RuleSeverity.MEDIUM
        )
        self.max_count = max_count

    def check(self, sql: SQLStatement, context: Optional[Dict] = None) -> Optional[RuleViolation]:
        # 统计 IN 子句中的元素数量
        in_matches = re.findall(r'IN\s*\(([^)]+)\)', sql.normalized_sql, re.IGNORECASE)

        for match in in_matches:
            # 简单统计逗号分隔的元素
            items = [x.strip() for x in match.split(',') if x.strip()]
            if len(items) > self.max_count:
                return RuleViolation(
                    rule_id=self.rule_id,
                    rule_name=self.name,
                    category=self.category,
                    severity=self.severity,
                    message=f"IN 子句包含 {len(items)} 个元素，超过建议的 {self.max_count} 个",
                    suggestion="大量 IN 元素应考虑: 1) 使用临时表存储值 2) 使用 EXISTS 子查询 3) 分批次处理"
                )
        return None


class NotEqualRule(SQLRule):
    """不等号性能检测"""

    def __init__(self):
        super().__init__(
            rule_id="R006",
            name="不等号操作符",
            description="<> 或 != 操作符在某些情况下会导致索引扫描",
            category=RuleCategory.PERFORMANCE,
            severity=RuleSeverity.LOW
        )

    def check(self, sql: SQLStatement, context: Optional[Dict] = None) -> Optional[RuleViolation]:
        if re.search(r'\w+\s*(<>|!=)', sql.normalized_sql):
            return RuleViolation(
                rule_id=self.rule_id,
                rule_name=self.name,
                category=self.category,
                severity=self.severity,
                message="检测到不等号操作符 (<> 或 !=)",
                suggestion="不等号可能导致索引扫描，考虑是否能改写为 OR 条件或使用其他优化策略"
            )
        return None


class CartesianJoinRule(SQLRule):
    """笛卡尔积检测"""

    def __init__(self):
        super().__init__(
            rule_id="R007",
            name="笛卡尔积风险",
            description="多表连接缺少连接条件可能产生笛卡尔积",
            category=RuleCategory.PERFORMANCE,
            severity=RuleSeverity.HIGH
        )

    def is_applicable(self, sql: SQLStatement) -> bool:
        return len(sql.tables) >= 2 and sql.sql_type == SQLType.SELECT

    def check(self, sql: SQLStatement, context: Optional[Dict] = None) -> Optional[RuleViolation]:
        # 如果有多表但没有 JOIN 或 WHERE 连接条件
        table_count = len(sql.tables)

        # 统计 JOIN 关键字数量
        join_count = len(re.findall(r'\bJOIN\b', sql.normalized_sql, re.IGNORECASE))

        # 统计 WHERE 条件数量
        has_where = bool(sql.where_conditions)

        # 如果表数量 > JOIN 数量 + 1，可能缺少连接条件
        if table_count >= 2 and join_count < table_count - 1 and not has_where:
            table_names = [t.full_name() for t in sql.tables]
            return RuleViolation(
                rule_id=self.rule_id,
                rule_name=self.name,
                category=self.category,
                severity=self.severity,
                message=f"检测到 {table_count} 张表连接但缺少连接条件",
                suggestion="多表查询应明确指定连接条件，避免产生笛卡尔积导致性能问题",
                metadata={"tables": table_names}
            )
        return None


class SubqueryPerformanceRule(SQLRule):
    """子查询性能检测"""

    def __init__(self):
        super().__init__(
            rule_id="R008",
            name="关联子查询",
            description="关联子查询可能导致性能问题",
            category=RuleCategory.PERFORMANCE,
            severity=RuleSeverity.MEDIUM
        )

    def check(self, sql: SQLStatement, context: Optional[Dict] = None) -> Optional[RuleViolation]:
        if not sql.has_subquery:
            return None

        # 简单检测：如果 WHERE 中有子查询，提醒可能的问题
        if re.search(r'\bWHERE\s+.*\(\s*SELECT', sql.normalized_sql, re.IGNORECASE):
            return RuleViolation(
                rule_id=self.rule_id,
                rule_name=self.name,
                category=self.category,
                severity=self.severity,
                message="WHERE 子句中包含子查询",
                suggestion="考虑将子查询改写为 JOIN，或使用 EXISTS/NOT EXISTS 替代 IN/NOT IN"
            )
        return None


class OrderByIndexRule(SQLRule):
    """ORDER BY 索引检测"""

    def __init__(self):
        super().__init__(
            rule_id="R009",
            name="ORDER BY 无索引",
            description="ORDER BY 列没有索引会导致排序操作",
            category=RuleCategory.INDEX,
            severity=RuleSeverity.LOW
        )

    def is_applicable(self, sql: SQLStatement) -> bool:
        return bool(sql.order_by) and sql.sql_type == SQLType.SELECT

    def check(self, sql: SQLStatement, context: Optional[Dict] = None) -> Optional[RuleViolation]:
        # 如果有上下文中的索引信息，可以检查是否有覆盖 ORDER BY 的索引
        if context and 'indexes' in context:
            indexes = context.get('indexes', [])
            order_columns = set(sql.order_by)

            # 检查是否有索引覆盖 ORDER BY 列
            for idx in indexes:
                idx_columns = set(col.upper() for col in idx.get('columns', []))
                if order_columns.issubset(idx_columns):
                    return None  # 有索引覆盖

            return RuleViolation(
                rule_id=self.rule_id,
                rule_name=self.name,
                category=self.category,
                severity=self.severity,
                message=f"ORDER BY 列 {sql.order_by} 可能没有合适的索引",
                suggestion="考虑在 ORDER BY 列上创建索引以避免排序操作",
                metadata={"order_by": sql.order_by}
            )
        return None


class IndexMissingRule(SQLRule):
    """缺失索引检测（基于执行计划）"""

    def __init__(self):
        super().__init__(
            rule_id="R010",
            name="缺失索引建议",
            description="根据 WHERE 条件列建议可能的索引",
            category=RuleCategory.INDEX,
            severity=RuleSeverity.MEDIUM
        )

    def check(self, sql: SQLStatement, context: Optional[Dict] = None) -> Optional[RuleViolation]:
        if not sql.where_conditions:
            return None

        # 提取 WHERE 条件中的列
        where_columns = set()
        for condition in sql.where_conditions:
            # 简单提取列名（等号左边的部分）
            match = re.match(r'([A-Z_][A-Z0-9_]*)\s*[=<>]', condition.strip())
            if match:
                where_columns.add(match.group(1))

        if not where_columns:
            return None

        # 如果有执行计划上下文，检查是否发生了全表扫描
        if context and 'execution_plan' in context:
            plan = context.get('execution_plan', {})
            # 兼容 dict 格式（统一后的格式）和旧格式
            operations = plan.get('operations', []) if isinstance(plan, dict) else plan
            full_scans = [op for op in operations if 'TABLE ACCESS FULL' in str(op)]

            if full_scans and where_columns:
                return RuleViolation(
                    rule_id=self.rule_id,
                    rule_name=self.name,
                    category=self.category,
                    severity=self.severity,
                    message=f"WHERE 条件列 {list(where_columns)} 可能缺少索引，导致全表扫描",
                    suggestion=f"考虑在列 {list(where_columns)} 上创建索引",
                    metadata={"where_columns": list(where_columns), "full_scans": len(full_scans)}
                )

        return None


# ==================== 规则引擎 ====================

class RuleEngine:
    """SQL 规则引擎"""

    # 内置规则列表
    DEFAULT_RULES: List[SQLRule] = [
        SelectStarRule(),
        MissingWhereRule(),
        ImplicitConversionRule(),
        LikePrefixRule(),
        InClauseCountRule(),
        NotEqualRule(),
        CartesianJoinRule(),
        SubqueryPerformanceRule(),
        OrderByIndexRule(),
        IndexMissingRule(),
    ]

    def __init__(self, rules: Optional[List[SQLRule]] = None):
        self.rules = rules or self.DEFAULT_RULES.copy()
        self._rules_by_id: Dict[str, SQLRule] = {r.rule_id: r for r in self.rules}

    def add_rule(self, rule: SQLRule):
        """添加自定义规则"""
        self.rules.append(rule)
        self._rules_by_id[rule.rule_id] = rule

    def remove_rule(self, rule_id: str):
        """移除规则"""
        self.rules = [r for r in self.rules if r.rule_id != rule_id]
        self._rules_by_id.pop(rule_id, None)

    def enable_rule(self, rule_id: str):
        """启用规则"""
        if rule_id in self._rules_by_id:
            self._rules_by_id[rule_id].enabled = True

    def disable_rule(self, rule_id: str):
        """禁用规则"""
        if rule_id in self._rules_by_id:
            self._rules_by_id[rule_id].enabled = False

    def analyze(
        self,
        sql_text: str,
        sql_id: Optional[str] = None,
        context: Optional[Dict] = None
    ) -> RuleCheckResult:
        """
        分析 SQL 语句

        Args:
            sql_text: SQL 语句文本
            sql_id: 可选的 SQL ID
            context: 额外上下文（如元数据、执行计划等）

        Returns:
            RuleCheckResult: 检查结果
        """
        result = RuleCheckResult(sql_id=sql_id)

        try:
            # 解析 SQL
            sql = SQLParser.parse(sql_text)

            # 应用所有启用的规则
            for rule in self.rules:
                if not rule.enabled:
                    continue

                if not rule.is_applicable(sql):
                    continue

                try:
                    violation = rule.check(sql, context)
                    if violation:
                        result.add_violation(violation)
                except Exception as e:
                    logger.warning(f"规则 {rule.rule_id} 检查失败: {e}")

        except Exception as e:
            logger.error(f"SQL 解析失败: {e}")
            # 添加解析错误作为信息级别违规
            result.add_violation(RuleViolation(
                rule_id="PARSE_ERROR",
                rule_name="SQL Parse Error",
                category=RuleCategory.QUERY_STRUCTURE,
                severity=RuleSeverity.INFO,
                message=f"SQL 解析失败: {e}",
                suggestion="请检查 SQL 语法是否正确"
            ))

        return result

    def analyze_batch(
        self,
        sql_list: List[Dict[str, Any]],
        context_provider: Optional[callable] = None
    ) -> List[RuleCheckResult]:
        """
        批量分析 SQL

        Args:
            sql_list: SQL 列表，每项包含 'sql_text', 'sql_id' 等
            context_provider: 可选的上下文提供函数

        Returns:
            List[RuleCheckResult]: 检查结果列表
        """
        results = []
        for item in sql_list:
            sql_text = item.get('sql_text', '')
            sql_id = item.get('sql_id')

            # 获取上下文
            context = None
            if context_provider:
                context = context_provider(item)

            result = self.analyze(sql_text, sql_id, context)
            results.append(result)

        return results


# 全局规则引擎实例
rule_engine = RuleEngine()
