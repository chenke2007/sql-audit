"""
Tests for Oracle Client Module
"""

import pytest
from unittest.mock import Mock, patch, MagicMock

from app.oracle.client import OracleClient, OracleConnectionError, OracleQueryError


class TestOracleClient:
    """OracleClient测试类"""

    def test_initial_state(self):
        """测试初始状态"""
        client = OracleClient()
        assert not client.is_connected
        assert client._pool is None

    @patch('app.oracle.client.oracledb')
    def test_initialize_success(self, mock_oracledb):
        """测试初始化成功"""
        # 模拟连接池
        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()

        mock_oracledb.create_pool.return_value = mock_pool
        mock_pool.acquire.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = (1,)

        client = OracleClient()

        with patch('app.oracle.client.settings') as mock_settings:
            mock_settings.oracle.host = "localhost"
            mock_settings.oracle.port = 1521
            mock_settings.oracle.service_name = "ORCL"
            mock_settings.oracle.username = "system"
            mock_settings.oracle.password = "password"
            mock_settings.oracle.min_connections = 2
            mock_settings.oracle.max_connections = 10

            result = client.initialize()

        assert result is True
        assert client.is_connected
        mock_oracledb.create_pool.assert_called_once()

    @patch('app.oracle.client.oracledb')
    def test_initialize_failure(self, mock_oracledb):
        """测试初始化失败"""
        mock_oracledb.create_pool.side_effect = Exception("Connection refused")

        client = OracleClient()

        with patch('app.oracle.client.settings') as mock_settings:
            mock_settings.oracle.host = "localhost"
            mock_settings.oracle.port = 1521
            mock_settings.oracle.service_name = "ORCL"
            mock_settings.oracle.username = "system"
            mock_settings.oracle.password = "password"
            mock_settings.oracle.min_connections = 2
            mock_settings.oracle.max_connections = 10

            with pytest.raises(OracleConnectionError):
                client.initialize()

        assert not client.is_connected

    def test_execute_without_connection(self):
        """测试未连接时执行查询"""
        client = OracleClient()

        with pytest.raises(OracleConnectionError):
            client.execute("SELECT 1 FROM DUAL")

    @patch('app.oracle.client.oracledb')
    def test_execute_success(self, mock_oracledb):
        """测试执行查询成功"""
        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()

        mock_oracledb.create_pool.return_value = mock_pool
        mock_pool.acquire.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [(1, 'test'), (2, 'test2')]

        client = OracleClient()

        with patch('app.oracle.client.settings') as mock_settings:
            mock_settings.oracle.host = "localhost"
            mock_settings.oracle.port = 1521
            mock_settings.oracle.service_name = "ORCL"
            mock_settings.oracle.username = "system"
            mock_settings.oracle.password = "password"
            mock_settings.oracle.min_connections = 2
            mock_settings.oracle.max_connections = 10

            client.initialize()
            results = client.execute("SELECT * FROM test")

        assert len(results) == 2
        assert results[0] == (1, 'test')
        mock_cursor.execute.assert_called_once_with("SELECT * FROM test")

    def test_close(self):
        """测试关闭连接池"""
        client = OracleClient()
        mock_pool = MagicMock()
        client._pool = mock_pool
        client._connected = True

        client.close()

        mock_pool.close.assert_called_once()
        assert not client.is_connected


class TestOracleCollector:
    """SQLCollector测试类"""

    def test_collect_slow_sqls(self):
        """测试采集慢SQL"""
        from app.oracle.collector import SQLCollector

        mock_client = Mock()
        mock_client.execute.return_value = [
            ('sql1', 'SELECT * FROM users', 100, 50000, 60000, 1000000, 1000, 5000, None),
            ('sql2', 'SELECT * FROM orders', 50, 30000, 40000, 800000, 500, 2000, None),
        ]

        collector = SQLCollector(mock_client)
        results = collector.collect_slow_sqls(top_n=10)

        assert len(results) == 2
        assert results[0].sql_id == 'sql1'
        assert results[0].execution_stats.cpu_time_ms == 50000
        mock_client.execute.assert_called_once()

    def test_get_sql_by_id_found_in_vsql(self):
        """测试从v$sql找到SQL"""
        from app.oracle.collector import SQLCollector

        mock_client = Mock()
        mock_client.execute.return_value = [
            ('abc123', 'SELECT * FROM users', 100, 5000, 6000, 10000, 100, 500, None),
        ]

        collector = SQLCollector(mock_client)
        result = collector.get_sql_by_id('abc123')

        assert result is not None
        assert result.sql_id == 'abc123'
        assert result.source == 'sql_id_query'

    def test_get_execution_plan(self):
        """测试获取执行计划"""
        from app.oracle.collector import SQLCollector, SQLPlan

        mock_client = Mock()
        plan_text = """
Plan hash value: 1234567890

| Id  | Operation         | Name  |
|   0 | SELECT STATEMENT  |       |
|   1 |  TABLE ACCESS FULL| USERS |
"""
        mock_client.execute.return_value = [
            ('abc123', 1234567890, plan_text),
        ]

        collector = SQLCollector(mock_client)
        plan = collector.get_execution_plan('abc123')

        assert plan is not None
        assert plan.sql_id == 'abc123'
        assert 'FULL' in plan.plan_text
