"""
核心分析模块

提供 SQL 预处理、规则引擎和 LLM 分析功能。
"""

from app.core.preprocessing import (
    SQLStatement,
    SQLType,
    SQLParser,
    SQLNormalizer,
    SQLFormatter,
    preprocess_sql,
    format_sql,
    normalize_sql,
)

from app.core.rule_engine import (
    RuleEngine,
    SQLRule,
    RuleViolation,
    RuleCheckResult,
    RuleSeverity,
    RuleCategory,
    rule_engine,
)

from app.core.llm_analyzer import (
    LLMClient,
    LLMAnalysisResult,
    SQLAnalyzer,
    sql_analyzer,
)

__all__ = [
    # Preprocessing
    "SQLStatement",
    "SQLType",
    "SQLParser",
    "SQLNormalizer",
    "SQLFormatter",
    "preprocess_sql",
    "format_sql",
    "normalize_sql",
    # Rule Engine
    "RuleEngine",
    "SQLRule",
    "RuleViolation",
    "RuleCheckResult",
    "RuleSeverity",
    "RuleCategory",
    "rule_engine",
    # LLM Analyzer
    "LLMClient",
    "LLMAnalysisResult",
    "SQLAnalyzer",
    "sql_analyzer",
]
