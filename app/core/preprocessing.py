"""
SQL 预处理模块

对 SQL 语句进行规范化、格式化、提取关键信息，为后续分析做准备。
"""

import logging
import re
from dataclasses import dataclass, field
from typing import List, Optional, Set, Dict, Any
from enum import Enum

logger = logging.getLogger(__name__)


class SQLType(Enum):
    """SQL 语句类型"""
    SELECT = "SELECT"
    INSERT = "INSERT"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    MERGE = "MERGE"
    CREATE = "CREATE"
    ALTER = "ALTER"
    DROP = "DROP"
    UNKNOWN = "UNKNOWN"


@dataclass
class TableRef:
    """表引用信息"""
    name: str                          # 表名
    schema: Optional[str] = None       # schema/owner
    alias: Optional[str] = None        # 别名

    def __hash__(self):
        return hash((self.name.upper(), self.schema.upper() if self.schema else None))

    def __eq__(self, other):
        if isinstance(other, TableRef):
            return (self.name.upper() == other.name.upper() and
                    (self.schema or "").upper() == (other.schema or "").upper())
        return False

    def __repr__(self):
        if self.schema:
            return f"{self.schema}.{self.name}"
        return self.name

    def full_name(self) -> str:
        """返回完整的表名（含 schema）"""
        if self.schema:
            return f"{self.schema}.{self.name}"
        return self.name


@dataclass
class SQLStatement:
    """解析后的 SQL 语句对象"""
    original_sql: str
    normalized_sql: str
    sql_type: SQLType
    tables: Set[TableRef] = field(default_factory=set)
    columns: Set[str] = field(default_factory=set)
    where_conditions: List[str] = field(default_factory=list)
    join_conditions: List[str] = field(default_factory=list)
    order_by: List[str] = field(default_factory=list)
    group_by: List[str] = field(default_factory=list)
    has_subquery: bool = False
    has_function: bool = False
    parameters: List[str] = field(default_factory=list)


class SQLNormalizer:
    """SQL 规范化器"""

    # Oracle 保留关键字（大写）
    ORACLE_KEYWORDS = {
        'SELECT', 'FROM', 'WHERE', 'INSERT', 'UPDATE', 'DELETE', 'MERGE',
        'CREATE', 'ALTER', 'DROP', 'TABLE', 'INDEX', 'VIEW', 'SEQUENCE',
        'JOIN', 'INNER', 'OUTER', 'LEFT', 'RIGHT', 'FULL', 'ON', 'USING',
        'AND', 'OR', 'NOT', 'NULL', 'IS', 'IN', 'EXISTS', 'BETWEEN', 'LIKE',
        'ORDER', 'BY', 'GROUP', 'HAVING', 'ASC', 'DESC',
        'DISTINCT', 'ALL', 'AS', 'UNION', 'INTERSECT', 'MINUS',
        'SYSDATE', 'ROWNUM', 'ROWID', 'LEVEL', 'CONNECT', 'START', 'WITH',
        'DUAL', 'SYSTIMESTAMP', 'DBTIMEZONE', 'SESSIONTIMEZONE'
    }

    # 需要特别处理的函数
    SQL_FUNCTIONS = {
        'COUNT', 'SUM', 'AVG', 'MAX', 'MIN', 'NVL', 'NVL2', 'COALESCE',
        'DECODE', 'CASE', 'WHEN', 'THEN', 'ELSE', 'END',
        'SUBSTR', 'INSTR', 'TRIM', 'LTRIM', 'RTRIM', 'UPPER', 'LOWER',
        'TO_CHAR', 'TO_DATE', 'TO_NUMBER', 'ROUND', 'TRUNC',
        'LENGTH', 'REPLACE', 'TRANSLATE', 'LPAD', 'RPAD'
    }

    @staticmethod
    def normalize(sql: str) -> str:
        """
        规范化 SQL 语句

        - 统一转为大写（保留字符串内容）
        - 标准化空白字符
        - 移除多余空格
        - 标准化注释
        """
        if not sql or not sql.strip():
            return ""

        # 保存字符串字面量
        string_literals = []
        def save_string(match):
            string_literals.append(match.group(0))
            return f"__STR_{len(string_literals)-1}__"

        # 提取字符串字面量 (单引号)
        sql_with_placeholders = re.sub(r"'[^']*'", save_string, sql)

        # 标准化空白
        sql_with_placeholders = re.sub(r'\s+', ' ', sql_with_placeholders)
        sql_with_placeholders = sql_with_placeholders.strip()

        # 标准化关键字为大写
        def uppercase_keyword(match):
            word = match.group(0).upper()
            if word in SQLNormalizer.ORACLE_KEYWORDS or word in SQLNormalizer.SQL_FUNCTIONS:
                return word
            return match.group(0)

        # 匹配单词（包括下划线）
        sql_with_placeholders = re.sub(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', uppercase_keyword, sql_with_placeholders)

        # 移除单行注释
        sql_with_placeholders = re.sub(r'--[^\n]*', '', sql_with_placeholders)
        # 移除多行注释
        sql_with_placeholders = re.sub(r'/\*.*?\*/', '', sql_with_placeholders, flags=re.DOTALL)

        # 标准化空格
        sql_with_placeholders = re.sub(r'\s*,\s*', ', ', sql_with_placeholders)
        sql_with_placeholders = re.sub(r'\s*\(\s*', '(', sql_with_placeholders)
        sql_with_placeholders = re.sub(r'\s*\)\s*', ')', sql_with_placeholders)
        sql_with_placeholders = re.sub(r'\s+', ' ', sql_with_placeholders)
        sql_with_placeholders = sql_with_placeholders.strip()

        # 恢复字符串字面量
        for i, literal in enumerate(string_literals):
            sql_with_placeholders = sql_with_placeholders.replace(f"__STR_{i}__", literal, 1)

        return sql_with_placeholders

    @staticmethod
    def extract_bind_parameters(sql: str) -> List[str]:
        """提取绑定变量参数 (:param_name 或 ?)"""
        # Oracle 风格 :param_name
        named_params = re.findall(r':([a-zA-Z_][a-zA-Z0-9_]*)', sql)
        # JDBC 风格 ?
        positional_count = sql.count('?')
        params = [f":{p}" for p in named_params]
        if positional_count > 0:
            params.extend(['?'] * positional_count)
        return params


class SQLParser:
    """SQL 解析器 - 提取 SQL 结构信息"""

    @staticmethod
    def parse(sql: str) -> SQLStatement:
        """解析 SQL 语句"""
        original = sql.strip()
        normalized = SQLNormalizer.normalize(sql)

        sql_type = SQLParser._detect_sql_type(normalized)
        tables = SQLParser._extract_tables(normalized)
        columns = SQLParser._extract_columns(normalized)
        where_conditions = SQLParser._extract_where_conditions(normalized)
        join_conditions = SQLParser._extract_join_conditions(normalized)
        order_by = SQLParser._extract_order_by(normalized)
        group_by = SQLParser._extract_group_by(normalized)
        has_subquery = SQLParser._detect_subquery(normalized)
        has_function = SQLParser._detect_function(normalized)
        parameters = SQLNormalizer.extract_bind_parameters(original)

        return SQLStatement(
            original_sql=original,
            normalized_sql=normalized,
            sql_type=sql_type,
            tables=tables,
            columns=columns,
            where_conditions=where_conditions,
            join_conditions=join_conditions,
            order_by=order_by,
            group_by=group_by,
            has_subquery=has_subquery,
            has_function=has_function,
            parameters=parameters
        )

    @staticmethod
    def _detect_sql_type(sql: str) -> SQLType:
        """检测 SQL 类型"""
        upper_sql = sql.upper().strip()
        for sql_type in SQLType:
            if upper_sql.startswith(sql_type.value):
                return sql_type
        return SQLType.UNKNOWN

    @staticmethod
    def _extract_tables(sql: str) -> Set[TableRef]:
        """从 SQL 中提取表名（含 schema 和别名）"""
        tables = set()
        upper_sql = sql.upper()

        # FROM 子句: 支持 schema.table alias 格式
        # 匹配 FROM 后面的表列表，支持 schema.table alias 或 table alias
        from_pattern = re.compile(
            r'\bFROM\s+((?:[A-Z_][A-Z0-9_]*(?:\.[A-Z_][A-Z0-9_]*)?\s*(?:[A-Z_][A-Z0-9_]*)?\s*,\s*)*[A-Z_][A-Z0-9_]*(?:\.[A-Z_][A-Z0-9_]*)?\s*(?:[A-Z_][A-Z0-9_]*)?)',
            re.IGNORECASE
        )
        for match in from_pattern.finditer(upper_sql):
            table_list = match.group(1)
            # 按逗号分割多个表
            for table_entry in re.split(r'\s*,\s*', table_list):
                table_entry = table_entry.strip()
                if not table_entry or '(' in table_entry:
                    continue

                # 解析表名、schema 和别名
                parts = table_entry.split()
                table_with_schema = parts[0]
                alias = parts[1] if len(parts) > 1 and parts[1] not in SQLNormalizer.ORACLE_KEYWORDS else None

                # 处理 schema.table 格式
                if '.' in table_with_schema:
                    schema, table_name = table_with_schema.split('.', 1)
                    schema = schema.strip()
                    table_name = table_name.strip()
                else:
                    schema = None
                    table_name = table_with_schema.strip()

                # 过滤关键字
                if table_name not in SQLNormalizer.ORACLE_KEYWORDS and table_name != 'DUAL':
                    tables.add(TableRef(name=table_name, schema=schema, alias=alias))

        # JOIN 子句: 支持 schema.table alias 格式
        join_pattern = re.compile(
            r'\bJOIN\s+([A-Z_][A-Z0-9_]*(?:\.[A-Z_][A-Z0-9_]*)?)\s*(?:([A-Z_][A-Z0-9_]*)\s+)?(?:ON\b|USING\b|$)',
            re.IGNORECASE
        )
        for match in join_pattern.finditer(upper_sql):
            table_with_schema = match.group(1).strip()
            alias = match.group(2).strip() if match.group(2) else None

            if '.' in table_with_schema:
                schema, table_name = table_with_schema.split('.', 1)
                schema = schema.strip()
                table_name = table_name.strip()
            else:
                schema = None
                table_name = table_with_schema

            if table_name not in SQLNormalizer.ORACLE_KEYWORDS and table_name != 'DUAL':
                tables.add(TableRef(name=table_name, schema=schema, alias=alias))

        return tables

    @staticmethod
    def _extract_columns(sql: str) -> Set[str]:
        """提取 SELECT 中的列名"""
        columns = set()

        # 匹配 SELECT 和 FROM 之间的内容
        select_match = re.search(r'\bSELECT\s+(.*?)\s+FROM\b', sql, re.IGNORECASE | re.DOTALL)
        if select_match:
            select_part = select_match.group(1)
            # 分割列
            for col in re.split(r',\s*', select_part):
                col = col.strip()
                # 提取列名（去除别名和函数）
                col = re.sub(r'\s+AS\s+\w+', '', col, flags=re.IGNORECASE)
                col = col.strip()

                # 如果是 * 则跳过
                if col == '*':
                    continue

                # 提取最内层的列名
                if '.' in col:
                    col = col.split('.')[-1]

                # 去除函数调用
                col = re.sub(r'\w+\(([^)]+)\)', r'\1', col)
                col = col.strip('() ')

                if col and col not in SQLNormalizer.SQL_FUNCTIONS:
                    columns.add(col.upper())

        return columns

    @staticmethod
    def _extract_where_conditions(sql: str) -> List[str]:
        """提取 WHERE 子句中的条件"""
        conditions = []

        where_match = re.search(r'\bWHERE\s+(.*?)(?:\s+ORDER\s+BY|\s+GROUP\s+BY|\s+HAVING|\s*$)', sql, re.IGNORECASE | re.DOTALL)
        if where_match:
            where_clause = where_match.group(1).strip()
            # 按 AND/OR 分割条件（简单处理）
            for condition in re.split(r'\s+(?:AND|OR)\s+', where_clause, flags=re.IGNORECASE):
                condition = condition.strip()
                if condition:
                    conditions.append(condition)

        return conditions

    @staticmethod
    def _extract_join_conditions(sql: str) -> List[str]:
        """提取 JOIN 条件"""
        conditions = []

        # 匹配 ON 子句
        on_pattern = re.compile(r'\bON\s+(.+?)(?:\s+(?:LEFT|RIGHT|INNER|OUTER|JOIN|WHERE|ORDER|GROUP|HAVING)\s|\s*$)', re.IGNORECASE)
        for match in on_pattern.finditer(sql):
            condition = match.group(1).strip()
            if condition:
                conditions.append(condition)

        return conditions

    @staticmethod
    def _extract_order_by(sql: str) -> List[str]:
        """提取 ORDER BY 列"""
        columns = []

        order_match = re.search(r'\bORDER\s+BY\s+(.+?)(?:\s+LIMIT|\s+OFFSET|\s+FETCH|\s*$)', sql, re.IGNORECASE | re.DOTALL)
        if order_match:
            order_clause = order_match.group(1)
            for col in re.split(r',\s*', order_clause):
                col = col.strip()
                # 去除 ASC/DESC
                col = re.sub(r'\s+(?:ASC|DESC)\s*$', '', col, flags=re.IGNORECASE)
                if col:
                    columns.append(col.upper())

        return columns

    @staticmethod
    def _extract_group_by(sql: str) -> List[str]:
        """提取 GROUP BY 列"""
        columns = []

        group_match = re.search(r'\bGROUP\s+BY\s+(.+?)(?:\s+ORDER|\s+HAVING|\s*$)', sql, re.IGNORECASE | re.DOTALL)
        if group_match:
            group_clause = group_match.group(1)
            for col in re.split(r',\s*', group_clause):
                col = col.strip()
                if col:
                    columns.append(col.upper())

        return columns

    @staticmethod
    def _detect_subquery(sql: str) -> bool:
        """检测是否包含子查询"""
        # 简单检测：是否存在 (SELECT ...)
        return bool(re.search(r'\(\s*SELECT\s+', sql, re.IGNORECASE))

    @staticmethod
    def _detect_function(sql: str) -> bool:
        """检测是否使用了函数"""
        pattern = r'\b(' + '|'.join(SQLNormalizer.SQL_FUNCTIONS) + r')\s*\('
        return bool(re.search(pattern, sql, re.IGNORECASE))


class SQLFormatter:
    """SQL 格式化器 - 美化 SQL 输出"""

    KEYWORDS_TO_NEWLINE = {'FROM', 'WHERE', 'ORDER BY', 'GROUP BY', 'HAVING'}
    KEYWORDS_TO_INDENT = {'AND', 'OR'}

    @staticmethod
    def format(sql: str, indent_size: int = 4) -> str:
        """格式化 SQL 语句，添加换行和缩进"""
        normalized = SQLNormalizer.normalize(sql)
        if not normalized:
            return ""

        # 简单的格式化规则
        formatted = normalized

        # 在关键字前添加换行
        for keyword in SQLFormatter.KEYWORDS_TO_NEWLINE:
            formatted = re.sub(
                rf'\s*\b{keyword}\b',
                f'\n{keyword}',
                formatted,
                flags=re.IGNORECASE
            )

        # 处理 JOIN
        formatted = re.sub(
            r'\s*(LEFT|RIGHT|INNER|OUTER|FULL|CROSS)?\s*(JOIN)\b',
            r'\n\1 \2',
            formatted,
            flags=re.IGNORECASE
        )

        # 处理 AND/OR 缩进
        lines = formatted.split('\n')
        result = []
        for line in lines:
            stripped = line.strip()
            if re.match(r'^(AND|OR)\b', stripped, re.IGNORECASE):
                result.append(' ' * indent_size + stripped)
            else:
                result.append(line)

        return '\n'.join(result).strip()


def preprocess_sql(sql: str) -> SQLStatement:
    """
    预处理 SQL 语句的主入口

    Args:
        sql: 原始 SQL 语句

    Returns:
        SQLStatement: 解析后的 SQL 对象
    """
    return SQLParser.parse(sql)


def format_sql(sql: str, indent_size: int = 4) -> str:
    """格式化 SQL 语句"""
    return SQLFormatter.format(sql, indent_size)


def normalize_sql(sql: str) -> str:
    """规范化 SQL 语句"""
    return SQLNormalizer.normalize(sql)
