"""
动态数据库连接管理

根据数据源ID动态创建数据库连接
"""

import logging
from typing import Optional, Dict, Any
from contextlib import contextmanager

from app.core.database import DBSourceManager, DBSource

logger = logging.getLogger(__name__)


class DynamicDBClient:
    """动态数据库客户端"""

    def __init__(self):
        self._connection = None
        self._source_id = None
        self._source = None

    def connect_to_source(self, source_id: str) -> bool:
        """
        连接到指定数据源

        Args:
            source_id: 数据源ID

        Returns:
            是否连接成功
        """
        source = DBSourceManager.get_by_id(source_id)
        if not source:
            raise ValueError(f"数据源不存在: {source_id}")

        self._source_id = source_id
        self._source = source

        if source.db_type == "oracle":
            return self._connect_oracle(source)
        else:
            raise ValueError(f"暂不支持的数据库类型: {source.db_type}")

    def _connect_oracle(self, source: DBSource) -> bool:
        """连接到Oracle数据库"""
        import oracledb

        try:
            if source.service_name:
                dsn = f"{source.host}:{source.port}/{source.service_name}"
            elif source.sid:
                dsn = f"{source.host}:{source.port}/{source.sid}"
            else:
                raise ValueError("Oracle连接需要SID或Service Name")

            self._connection = oracledb.connect(
                user=source.username,
                password=source.password,
                dsn=dsn
            )
            return True
        except Exception as e:
            logger.error(f"Oracle连接失败: {e}")
            raise

    @property
    def connection(self):
        """获取当前连接"""
        if self._connection is None:
            raise RuntimeError("未建立数据库连接，请先调用 connect_to_source()")
        return self._connection

    @property
    def is_connected(self) -> bool:
        """检查是否已连接"""
        try:
            if self._connection:
                # 尝试执行简单查询验证连接
                cursor = self._connection.cursor()
                cursor.execute("SELECT 1 FROM DUAL")
                cursor.fetchone()
                return True
        except Exception:
            pass
        return False

    def execute(self, sql: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """执行SQL"""
        cursor = self.connection.cursor()
        if params:
            cursor.execute(sql, params)
        else:
            cursor.execute(sql)
        return cursor

    def close(self):
        """关闭连接"""
        if self._connection:
            try:
                self._connection.close()
            except Exception as e:
                logger.warning(f"关闭连接时出错: {e}")
            finally:
                self._connection = None
                self._source_id = None
                self._source = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


@contextmanager
def get_db_client(source_id: Optional[str] = None):
    """
    获取数据库客户端的上下文管理器

    Args:
        source_id: 数据源ID，如果不传则使用默认数据源

    Yields:
        DynamicDBClient: 数据库客户端
    """
    if source_id is None:
        # 使用默认数据源
        source = DBSourceManager.get_default()
        if not source:
            raise ValueError("未指定数据源且没有配置默认数据源")
        source_id = source.id

    client = DynamicDBClient()
    try:
        client.connect_to_source(source_id)
        yield client
    finally:
        client.close()
