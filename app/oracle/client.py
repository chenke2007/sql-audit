"""
Oracle Client Module

提供Oracle数据库连接管理和查询执行功能。
使用 oracledb 驱动（纯Python，无需Oracle客户端安装）。
"""

import logging
from contextlib import contextmanager
from typing import Any, Dict, List, Optional, Tuple

import oracledb
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings

logger = logging.getLogger(__name__)


class OracleClientError(Exception):
    """Oracle客户端错误"""
    pass


class OracleConnectionError(OracleClientError):
    """连接错误"""
    pass


class OracleQueryError(OracleClientError):
    """查询错误"""
    pass


class OracleClient:
    """
    Oracle数据库客户端

    功能:
    - 连接池管理
    - SQL查询执行
    - 执行计划获取
    - 元数据查询
    """

    def __init__(self):
        self._pool: Optional[oracledb.ConnectionPool] = None
        self._connected = False

    def initialize(self) -> bool:
        """
        初始化连接池

        Returns:
            bool: 初始化是否成功
        """
        try:
            logger.info(f"正在连接Oracle: {settings.oracle.host}:{settings.oracle.port}/{settings.oracle.service_name}")

            self._pool = oracledb.create_pool(
                user=settings.oracle.username,
                password=settings.oracle.password,
                host=settings.oracle.host,
                port=settings.oracle.port,
                service_name=settings.oracle.service_name,
                min=settings.oracle.min_connections,
                max=settings.oracle.max_connections,
                increment=1
            )

            # 测试连接
            with self._acquire_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1 FROM DUAL")
                cursor.fetchone()

            self._connected = True
            logger.info("Oracle连接池初始化成功")
            return True

        except oracledb.Error as e:
            logger.error(f"Oracle连接失败: {e}")
            self._connected = False
            raise OracleConnectionError(f"无法连接到Oracle数据库: {e}")

    def close(self):
        """关闭连接池"""
        if self._pool:
            self._pool.close()
            self._connected = False
            logger.info("Oracle连接池已关闭")

    @contextmanager
    def _acquire_connection(self):
        """获取连接的上下文管理器"""
        if not self._pool:
            raise OracleConnectionError("连接池未初始化")

        conn = None
        try:
            conn = self._pool.acquire()
            yield conn
        finally:
            if conn:
                conn.close()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True
    )
    def execute(
        self,
        sql: str,
        params: Optional[Dict[str, Any]] = None,
        fetch_size: int = 1000
    ) -> List[Tuple]:
        """
        执行SQL查询

        Args:
            sql: SQL语句
            params: 查询参数
            fetch_size: 单次获取行数

        Returns:
            查询结果列表
        """
        if not self._connected:
            raise OracleConnectionError("未连接到数据库")

        try:
            with self._acquire_connection() as conn:
                cursor = conn.cursor()
                cursor.arraysize = fetch_size

                if params:
                    cursor.execute(sql, params)
                else:
                    cursor.execute(sql)

                results = cursor.fetchall()
                return results

        except oracledb.Error as e:
            logger.error(f"SQL执行失败: {sql[:100]}... 错误: {e}")
            raise OracleQueryError(f"查询执行失败: {e}")

    def execute_many(
        self,
        sql: str,
        params_list: List[Dict[str, Any]]
    ) -> int:
        """
        批量执行SQL（用于INSERT/UPDATE）

        Args:
            sql: SQL语句
            params_list: 参数列表

        Returns:
            影响的行数
        """
        if not self._connected:
            raise OracleConnectionError("未连接到数据库")

        try:
            with self._acquire_connection() as conn:
                cursor = conn.cursor()
                cursor.executemany(sql, params_list)
                conn.commit()
                return cursor.rowcount

        except oracledb.Error as e:
            logger.error(f"批量SQL执行失败: {e}")
            raise OracleQueryError(f"批量执行失败: {e}")

    def get_columns(self, sql: str) -> List[str]:
        """
        获取查询结果的列名

        Args:
            sql: SQL语句

        Returns:
            列名列表
        """
        if not self._connected:
            raise OracleConnectionError("未连接到数据库")

        try:
            with self._acquire_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(sql)
                # 获取列描述
                columns = [desc[0] for desc in cursor.description] if cursor.description else []
                return columns

        except oracledb.Error as e:
            logger.error(f"获取列名失败: {e}")
            raise OracleQueryError(f"获取列名失败: {e}")

    @property
    def is_connected(self) -> bool:
        """检查是否已连接"""
        return self._connected and self._pool is not None


# 全局客户端实例
oracle_client = OracleClient()
