"""
动态数据库客户端

为现有的 Oracle 采集器和分析器提供动态数据源支持
"""

import logging
from typing import Optional, Dict, Any, List, Tuple
from contextlib import contextmanager

import oracledb

from app.core.database import DBSourceManager, DBSource

logger = logging.getLogger(__name__)


class DynamicOracleClient:
    """
    动态 Oracle 客户端

    兼容现有 OracleClient 接口，但支持动态切换数据源
    """

    def __init__(self):
        self._connection: Optional[oracledb.Connection] = None
        self._source: Optional[DBSource] = None
        self._source_id: Optional[str] = None

    def connect_to_source(self, source_id: Optional[str] = None) -> bool:
        """
        连接到指定数据源

        Args:
            source_id: 数据源ID，None则使用默认数据源

        Returns:
            是否连接成功
        """
        if source_id is None:
            source = DBSourceManager.get_default()
            if not source:
                raise ValueError("未指定数据源且没有配置默认数据源")
        else:
            source = DBSourceManager.get_by_id(source_id)
            if not source:
                raise ValueError(f"数据源不存在: {source_id}")

        # 关闭现有连接
        if self._connection:
            self.close()

        self._source = source
        self._source_id = source.id

        # 创建连接
        try:
            if source.service_name:
                dsn = f"{source.host}:{source.port}/{source.service_name}"
            elif source.sid:
                dsn = f"{source.host}:{source.port}/{source.sid}"
            else:
                raise ValueError("Oracle 连接需要 SID 或 Service Name")

            self._connection = oracledb.connect(
                user=source.username,
                password=source.password,
                dsn=dsn
            )

            logger.info(f"已连接到数据源: {source.name} ({source.host}:{source.port})")
            return True

        except Exception as e:
            logger.error(f"连接数据源失败: {e}")
            raise

    def close(self):
        """关闭连接"""
        if self._connection:
            try:
                self._connection.close()
            except Exception as e:
                logger.warning(f"关闭连接时出错: {e}")
            finally:
                self._connection = None
                self._source = None
                self._source_id = None

    @property
    def is_connected(self) -> bool:
        """检查是否已连接"""
        try:
            if self._connection:
                cursor = self._connection.cursor()
                cursor.execute("SELECT 1 FROM DUAL")
                cursor.fetchone()
                return True
        except Exception:
            pass
        return False

    @property
    def connection(self) -> oracledb.Connection:
        """获取当前连接"""
        if not self._connection:
            raise RuntimeError("未建立数据库连接")
        return self._connection

    @contextmanager
    def _acquire_connection(self):
        """获取连接的上下文管理器"""
        if not self._connection:
            raise RuntimeError("未建立数据库连接，请先调用 connect_to_source()")
        yield self._connection

    def execute_query(
        self,
        sql: str,
        params: Optional[Dict[str, Any]] = None,
        fetch_size: int = 1000
    ) -> List[Dict[str, Any]]:
        """执行查询"""
        with self._acquire_connection() as conn:
            cursor = conn.cursor()
            try:
                if params:
                    cursor.execute(sql, params)
                else:
                    cursor.execute(sql)

                # 获取列名
                columns = [desc[0].lower() for desc in cursor.description] if cursor.description else []

                # 获取结果
                rows = cursor.fetchmany(fetch_size)
                results = []
                for row in rows:
                    row_dict = {}
                    for i, col in enumerate(columns):
                        row_dict[col] = row[i]
                    results.append(row_dict)

                return results
            finally:
                cursor.close()

    def execute_query_one(
        self,
        sql: str,
        params: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """执行查询，返回单行结果"""
        results = self.execute_query(sql, params, fetch_size=1)
        return results[0] if results else None

    def execute_non_query(self, sql: str, params: Optional[Dict[str, Any]] = None) -> int:
        """执行非查询语句"""
        with self._acquire_connection() as conn:
            cursor = conn.cursor()
            try:
                if params:
                    cursor.execute(sql, params)
                else:
                    cursor.execute(sql)
                conn.commit()
                return cursor.rowcount
            finally:
                cursor.close()

    def execute(self, sql: str, params: Optional[Dict[str, Any]] = None, fetch_size: int = 1000):
        """
        执行查询（兼容 OracleClient 接口）

        返回原始行元组列表，与 OracleClient.execute 保持一致。
        SQLCollector 通过索引访问列。

        Args:
            sql: SQL 语句
            params: 查询参数
            fetch_size: 单次获取行数

        Returns:
            查询结果元组列表
        """
        with self._acquire_connection() as conn:
            cursor = conn.cursor()
            cursor.arraysize = fetch_size
            try:
                if params:
                    cursor.execute(sql, params)
                else:
                    cursor.execute(sql)
                return cursor.fetchall()
            finally:
                cursor.close()

    def get_execution_plan(self, sql_id: str) -> Optional[Dict[str, Any]]:
        """获取SQL执行计划"""
        try:
            # 获取执行计划
            plan_sql = """
                SELECT plan_table_output
                FROM TABLE(DBMS_XPLAN.DISPLAY_CURSOR(:sql_id, NULL, 'ALLSTATS LAST'))
            """
            rows = self.execute_query(plan_sql, {"sql_id": sql_id})

            if not rows:
                return None

            plan_text = "\n".join([row["plan_table_output"] for row in rows])

            return {
                "sql_id": sql_id,
                "plan_text": plan_text,
                "plan_rows": [row["plan_table_output"] for row in rows]
            }

        except Exception as e:
            logger.warning(f"获取执行计划失败 {sql_id}: {e}")
            return None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
