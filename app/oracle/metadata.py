"""
Oracle 元数据获取模块

获取表、索引、统计信息等元数据，用于 SQL 分析。
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from app.oracle.client import OracleClient, OracleQueryError

logger = logging.getLogger(__name__)


@dataclass
class TableInfo:
    """表信息"""
    table_name: str
    owner: str
    num_rows: Optional[int] = None
    last_analyzed: Optional[str] = None
    table_size_mb: Optional[float] = None


@dataclass
class IndexInfo:
    """索引信息"""
    index_name: str
    table_name: str
    owner: str
    columns: List[str] = field(default_factory=list)
    uniqueness: str = "NONUNIQUE"  # UNIQUE or NONUNIQUE
    index_type: str = "NORMAL"


@dataclass
class ColumnInfo:
    """列信息（含统计信息）"""
    column_name: str
    data_type: str
    nullable: bool = True
    data_length: Optional[int] = None
    num_distinct: Optional[int] = None
    density: Optional[float] = None
    num_nulls: Optional[int] = None
    last_analyzed: Optional[str] = None


@dataclass
class ConstraintInfo:
    """约束信息"""
    constraint_name: str
    constraint_type: str  # P = Primary Key, R = Foreign Key, U = Unique, C = Check
    columns: List[str] = field(default_factory=list)


@dataclass
class TableMetadata:
    """表完整元数据"""
    table_info: TableInfo
    columns: List[ColumnInfo] = field(default_factory=list)
    indexes: List[IndexInfo] = field(default_factory=list)
    constraints: List[ConstraintInfo] = field(default_factory=list)


class MetadataCollector:
    """
    元数据采集器

    负责从 Oracle 数据字典获取表、索引、统计信息等元数据。
    """

    def __init__(self, client: OracleClient):
        self.client = client

    def get_table_info(self, table_name: str, owner: Optional[str] = None) -> Optional[TableInfo]:
        """
        获取表基本信息

        Args:
            table_name: 表名
            owner: 所有者，默认查询所有用户

        Returns:
            表信息对象
        """
        sql = """
        SELECT
            t.table_name,
            t.owner,
            t.num_rows,
            TO_CHAR(t.last_analyzed, 'YYYY-MM-DD HH24:MI:SS') as last_analyzed,
            s.bytes / 1024 / 1024 as table_size_mb
        FROM all_tables t
        LEFT JOIN dba_segments s ON t.table_name = s.segment_name AND t.owner = s.owner
        WHERE t.table_name = :table_name
        """
        params = {"table_name": table_name.upper()}

        if owner:
            sql += " AND t.owner = :owner"
            params["owner"] = owner.upper()
        else:
            sql += " AND t.owner NOT IN ('SYS', 'SYSTEM', 'DBSNMP', 'SYSMAN', 'OUTLN')"

        try:
            results = self.client.execute(sql, params)
            if not results:
                return None

            row = results[0]
            return TableInfo(
                table_name=row[0],
                owner=row[1],
                num_rows=row[2],
                last_analyzed=row[3],
                table_size_mb=row[4]
            )
        except OracleQueryError as e:
            logger.error(f"获取表信息失败 {table_name}: {e}")
            return None

    def get_column_info(self, table_name: str, owner: Optional[str] = None) -> List[ColumnInfo]:
        """
        获取表的列信息（含统计信息）

        Args:
            table_name: 表名
            owner: 所有者

        Returns:
            列信息列表
        """
        # 主查询：从 all_tab_columns 获取基本列信息
        sql = """
        SELECT
            c.column_name,
            c.data_type,
            c.nullable,
            c.data_length,
            s.num_distinct,
            s.density,
            s.num_nulls,
            TO_CHAR(s.last_analyzed, 'YYYY-MM-DD HH24:MI:SS') as last_analyzed
        FROM all_tab_columns c
        LEFT JOIN all_tab_col_statistics s
            ON c.table_name = s.table_name
            AND c.column_name = s.column_name
            AND c.owner = s.owner
        WHERE c.table_name = :table_name
        """
        params = {"table_name": table_name.upper()}

        if owner:
            sql += " AND c.owner = :owner"
            params["owner"] = owner.upper()
        else:
            sql += " AND c.owner NOT IN ('SYS', 'SYSTEM', 'DBSNMP', 'SYSMAN', 'OUTLN')"

        sql += " ORDER BY c.column_id"

        try:
            results = self.client.execute(sql, params)
            columns = []
            for row in results:
                columns.append(ColumnInfo(
                    column_name=row[0],
                    data_type=row[1],
                    nullable=row[2] == 'Y',
                    data_length=row[3],
                    num_distinct=row[4],
                    density=row[5],
                    num_nulls=row[6],
                    last_analyzed=row[7]
                ))
            return columns
        except OracleQueryError as e:
            logger.error(f"获取列信息失败 {table_name}: {e}")
            return []

    def get_index_info(self, table_name: str, owner: Optional[str] = None) -> List[IndexInfo]:
        """
        获取表的索引信息

        Args:
            table_name: 表名
            owner: 所有者

        Returns:
            索引信息列表
        """
        # 先获取索引基本信息
        sql = """
        SELECT
            i.index_name,
            i.table_name,
            i.owner,
            i.uniqueness,
            i.index_type
        FROM all_indexes i
        WHERE i.table_name = :table_name
        """
        params = {"table_name": table_name.upper()}

        if owner:
            sql += " AND i.table_owner = :owner"
            params["owner"] = owner.upper()
        else:
            sql += " AND i.table_owner NOT IN ('SYS', 'SYSTEM', 'DBSNMP', 'SYSMAN', 'OUTLN')"

        try:
            results = self.client.execute(sql, params)
            indexes = []

            for row in results:
                index_name = row[0]
                idx_owner = row[2]

                # 获取索引列
                columns = self._get_index_columns(index_name, idx_owner)

                indexes.append(IndexInfo(
                    index_name=index_name,
                    table_name=row[1],
                    owner=idx_owner,
                    columns=columns,
                    uniqueness=row[3],
                    index_type=row[4]
                ))

            return indexes
        except OracleQueryError as e:
            logger.error(f"获取索引信息失败 {table_name}: {e}")
            return []

    def _get_index_columns(self, index_name: str, owner: str) -> List[str]:
        """获取索引的列列表"""
        sql = """
        SELECT column_name
        FROM all_ind_columns
        WHERE index_name = :index_name AND index_owner = :owner
        ORDER BY column_position
        """
        try:
            results = self.client.execute(sql, {
                "index_name": index_name,
                "owner": owner
            })
            return [row[0] for row in results]
        except OracleQueryError:
            return []

    def get_schemas(self) -> List[str]:
        """
        获取当前用户可访问的所有 schema（owner）列表

        Returns:
            schema 名称列表（按字母排序）
        """
        sql = """
        SELECT DISTINCT username
        FROM all_users
        WHERE username NOT IN ('SYS', 'SYSTEM', 'DBSNMP', 'SYSMAN', 'OUTLN',
                               'ORDSYS', 'ORDPLUGINS', 'CTXSYS', 'ANONYMOUS',
                               'EXFSYS', 'MDSYS', 'WMSYS', 'XDB', 'ORDDATA')
        ORDER BY username
        """
        try:
            results = self.client.execute(sql)
            schemas = [row[0] for row in results]
            if schemas:
                return schemas
        except Exception as e:
            logger.warning(f"从 all_users 获取 schema 列表失败: {e}")

        # Fallback: 返回当前连接用户作为 schema
        try:
            results = self.client.execute("SELECT USER FROM DUAL")
            if results:
                return [results[0][0]]
        except Exception as e:
            logger.error(f"获取 schema 列表 fallback 失败: {e}")

        return []

    def get_constraint_info(self, table_name: str, owner: Optional[str] = None) -> List[ConstraintInfo]:
        """
        获取表的约束信息

        Args:
            table_name: 表名
            owner: 所有者

        Returns:
            约束信息列表
        """
        sql = """
        SELECT
            c.constraint_name,
            c.constraint_type,
            cc.column_name
        FROM all_constraints c
        JOIN all_cons_columns cc
            ON c.constraint_name = cc.constraint_name
            AND c.owner = cc.owner
        WHERE c.table_name = :table_name
          AND c.constraint_type IN ('P', 'U', 'R')
        """
        params = {"table_name": table_name.upper()}

        if owner:
            sql += " AND c.owner = :owner"
            params["owner"] = owner.upper()
        else:
            sql += " AND c.owner NOT IN ('SYS', 'SYSTEM', 'DBSNMP', 'SYSMAN', 'OUTLN')"

        sql += " ORDER BY c.constraint_name, cc.position"

        try:
            results = self.client.execute(sql, params)
            constraints = {}
            for row in results:
                constraint_name = row[0]
                constraint_type = row[1]
                column_name = row[2]

                if constraint_name not in constraints:
                    constraints[constraint_name] = ConstraintInfo(
                        constraint_name=constraint_name,
                        constraint_type=constraint_type,
                        columns=[]
                    )
                constraints[constraint_name].columns.append(column_name)

            return list(constraints.values())
        except OracleQueryError as e:
            logger.error(f"获取约束信息失败 {table_name}: {e}")
            return []

    def get_table_metadata(self, table_name: str, owner: Optional[str] = None) -> Optional[TableMetadata]:
        """
        获取表的完整元数据

        Args:
            table_name: 表名
            owner: 所有者

        Returns:
            表完整元数据
        """
        table_info = self.get_table_info(table_name, owner)
        if not table_info:
            return None

        columns = self.get_column_info(table_name, owner)
        indexes = self.get_index_info(table_name, owner)
        constraints = self.get_constraint_info(table_name, owner)

        return TableMetadata(
            table_info=table_info,
            columns=columns,
            indexes=indexes,
            constraints=constraints
        )

    def extract_tables_from_sql(self, sql_text: str) -> Set[str]:
        """
        从 SQL 文本中提取表名（简化版本）

        Args:
            sql_text: SQL 语句

        Returns:
            表名集合
        """
        import re

        # 简单的正则提取，实际项目中可能需要更复杂的 SQL 解析
        tables = set()

        # FROM 子句
        from_pattern = re.compile(r'\bFROM\s+(\w+)', re.IGNORECASE)
        tables.update(from_pattern.findall(sql_text))

        # JOIN 子句
        join_pattern = re.compile(r'\bJOIN\s+(\w+)', re.IGNORECASE)
        tables.update(join_pattern.findall(sql_text))

        # 去掉 Oracle 关键字
        oracle_keywords = {'DUAL', 'SYSDATE', 'ROWNUM', 'LEVEL', 'CONNECT'}
        tables = tables - oracle_keywords

        return tables

    def get_metadata_for_sql(self, sql_text: str) -> Dict[str, TableMetadata]:
        """
        获取 SQL 涉及的所有表的元数据

        Args:
            sql_text: SQL 语句

        Returns:
            表名到元数据的映射
        """
        table_names = self.extract_tables_from_sql(sql_text)
        metadata = {}

        for table_name in table_names:
            table_meta = self.get_table_metadata(table_name)
            if table_meta:
                metadata[table_name.upper()] = table_meta

        return metadata
