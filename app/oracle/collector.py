"""
SQL Collector Module

从Oracle数据库采集慢SQL和执行计划。
支持3种输入方式:
1. 自动采集: 从v$sql扫描慢SQL
2. SQL_ID查询: 根据sql_id查询特定SQL
3. 文件上传: 用户上传SQL文本（在analyzer中处理）
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Tuple

from app.oracle.client import OracleClient, OracleQueryError

logger = logging.getLogger(__name__)


@dataclass
class SQLExecutionStats:
    """SQL执行统计信息"""
    sql_id: str
    executions: int
    cpu_time_ms: float
    elapsed_time_ms: float
    buffer_gets: int
    disk_reads: int
    rows_processed: int
    last_active_time: Optional[datetime] = None


@dataclass
class SQLPlan:
    """SQL执行计划"""
    sql_id: str
    plan_hash_value: str
    plan_text: str
    operations: List[dict]  # 结构化的执行计划操作


@dataclass
class SQLObject:
    """统一SQL对象 - 分析引擎的标准输入"""
    sql_id: Optional[str]
    sql_text: str
    source: str  # 'auto_collect', 'sql_id_query', 'file_upload'
    execution_stats: Optional[SQLExecutionStats] = None
    execution_plan: Optional[SQLPlan] = None
    metadata: Optional[dict] = None  # 表/索引元数据


class SQLCollector:
    """
    SQL采集器

    负责从Oracle数据库采集SQL和执行计划。
    """

    def __init__(self, client: OracleClient):
        self.client = client

    def collect_slow_sqls(
        self,
        top_n: int = 20,
        cpu_threshold_ms: int = 10000,
        elapsed_threshold_ms: int = 10000,
        buffer_gets_threshold: int = 100000,
        exclude_system: bool = True
    ) -> List[SQLObject]:
        """
        自动采集慢SQL

        从v$sql中按资源消耗排序，获取Top N慢SQL。
        默认过滤掉数据库系统自身执行的SQL。

        Args:
            top_n: 获取前N条
            cpu_threshold_ms: CPU时间阈值（毫秒）
            elapsed_threshold_ms: 执行时间阈值（毫秒）
            buffer_gets_threshold: 逻辑读阈值
            exclude_system: 是否排除系统SQL

        Returns:
            SQL对象列表
        """
        if exclude_system:
            # 排除系统用户的SQL和系统内部SQL
            sql = """
            SELECT
                s.sql_id,
                s.sql_text,
                s.executions,
                s.cpu_time / 1000 as cpu_time_ms,
                s.elapsed_time / 1000 as elapsed_time_ms,
                s.buffer_gets,
                s.disk_reads,
                s.rows_processed,
                s.last_active_time
            FROM v$sql s
            WHERE (s.cpu_time > :cpu_threshold
               OR s.elapsed_time > :elapsed_threshold
               OR s.buffer_gets > :buffer_gets_threshold)
              AND s.parsing_schema_name NOT IN (
                  'SYS', 'SYSTEM', 'DBSNMP', 'SYSMAN', 'OUTLN', 'MGMT_VIEW',
                  'MDSYS', 'ORDSYS', 'EXFSYS', 'WMSYS', 'APPQOSSYS', 'XDB',
                  'ANONYMOUS', 'XS$NULL', 'ORDDATA', 'ORDPLUGINS', 'SI_INFORMTN_SCHEMA',
                  'OLAPSYS', 'OWBSYS', 'OWBSYS_AUDIT', 'APEX_PUBLIC_USER',
                  'APEX_030200', 'FLOWS_FILES', 'SQLTXPLAIN', 'SQLTXADMIN'
              )
              AND s.sql_text NOT LIKE '%dbms_%'
              AND s.sql_text NOT LIKE '%DBMS_%'
              AND s.sql_text NOT LIKE '%sys.%'
              AND s.sql_text NOT LIKE '%SYS.%'
              AND s.sql_text NOT LIKE '%wri$_%'
              AND s.sql_text NOT LIKE '%WRI$_%'
              AND s.sql_text NOT LIKE '%wrr$_%'
              AND s.sql_text NOT LIKE '%WRR$_%'
              AND s.sql_text NOT LIKE '%optstat%'
              AND s.sql_text NOT LIKE '%OPTSTAT%'
              AND s.sql_text NOT LIKE '%wrh$_%'
              AND s.sql_text NOT LIKE '%WRH$_%'
              AND s.sql_text NOT LIKE '%v_$%'
              AND s.sql_text NOT LIKE '%V_$%'
              AND s.sql_text NOT LIKE '%x_$%'
              AND s.sql_text NOT LIKE '%X_$%'
              AND s.sql_text NOT LIKE '%prvt_%'
              AND s.sql_text NOT LIKE '%PRVT_%'
              AND s.sql_text NOT LIKE '%sqlt$%'
              AND s.sql_text NOT LIKE '%SQLT$%'
              AND s.command_type != 47  -- PL/SQL execute
            ORDER BY s.cpu_time DESC
            FETCH FIRST :top_n ROWS ONLY
            """
        else:
            # 不排除系统SQL（原始查询）
            sql = """
            SELECT
                sql_id,
                sql_text,
                executions,
                cpu_time / 1000 as cpu_time_ms,
                elapsed_time / 1000 as elapsed_time_ms,
                buffer_gets,
                disk_reads,
                rows_processed,
                last_active_time
            FROM v$sql
            WHERE cpu_time > :cpu_threshold
               OR elapsed_time > :elapsed_threshold
               OR buffer_gets > :buffer_gets_threshold
            ORDER BY cpu_time DESC
            FETCH FIRST :top_n ROWS ONLY
            """

        try:
            results = self.client.execute(
                sql,
                {
                    "cpu_threshold": cpu_threshold_ms * 1000,  # 转换为微秒
                    "elapsed_threshold": elapsed_threshold_ms * 1000,
                    "buffer_gets_threshold": buffer_gets_threshold,
                    "top_n": top_n
                }
            )

            sql_objects = []
            for row in results:
                sql_obj = self._build_sql_object(row, source='auto_collect')
                sql_objects.append(sql_obj)

            logger.info(f"采集到 {len(sql_objects)} 条慢SQL (系统SQL已过滤: {exclude_system})")
            return sql_objects

        except OracleQueryError as e:
            logger.error(f"采集慢SQL失败: {e}")
            raise

    def get_sql_by_id(self, sql_id: str) -> Optional[SQLObject]:
        """
        根据SQL_ID查询SQL

        查询顺序:
        1. v$sql (实时缓存)
        2. DBA_HIST_SQLSTAT/AWR (历史数据)

        Args:
            sql_id: SQL标识符

        Returns:
            SQL对象，未找到返回None
        """
        # 先查v$sql
        sql_obj = self._query_vsql_by_id(sql_id)
        if sql_obj:
            return sql_obj

        # 再查AWR
        sql_obj = self._query_awr_by_id(sql_id)
        if sql_obj:
            return sql_obj

        logger.warning(f"SQL_ID {sql_id} 在v$sql和AWR中都未找到")
        return None

    def _query_vsql_by_id(self, sql_id: str) -> Optional[SQLObject]:
        """从v$sql查询"""
        sql = """
        SELECT
            sql_id,
            sql_text,
            executions,
            cpu_time / 1000 as cpu_time_ms,
            elapsed_time / 1000 as elapsed_time_ms,
            buffer_gets,
            disk_reads,
            rows_processed,
            last_active_time
        FROM v$sql
        WHERE sql_id = :sql_id
        """

        try:
            results = self.client.execute(sql, {"sql_id": sql_id})
            if results:
                return self._build_sql_object(results[0], source='sql_id_query')
            return None
        except OracleQueryError:
            return None

    def _query_awr_by_id(self, sql_id: str) -> Optional[SQLObject]:
        """从AWR历史表查询"""
        # 注意: 需要DBA_HIST_SQLSTAT的访问权限
        sql = """
        SELECT
            s.sql_id,
            t.sql_text,
            s.executions_total as executions,
            s.cpu_time_total / 1000 as cpu_time_ms,
            s.elapsed_time_total / 1000 as elapsed_time_ms,
            s.buffer_gets_total as buffer_gets,
            s.disk_reads_total as disk_reads,
            s.rows_processed_total as rows_processed,
            NULL as last_active_time
        FROM dba_hist_sqlstat s
        JOIN dba_hist_sqltext t ON s.sql_id = t.sql_id
        WHERE s.sql_id = :sql_id
        ORDER BY s.snap_id DESC
        FETCH FIRST 1 ROWS ONLY
        """

        try:
            results = self.client.execute(sql, {"sql_id": sql_id})
            if results:
                return self._build_sql_object(results[0], source='sql_id_query_awr')
            return None
        except OracleQueryError:
            # 可能没有AWR权限
            return None

    def get_execution_plan(self, sql_id: str) -> Optional[SQLPlan]:
        """
        获取SQL的执行计划

        使用DBMS_XPLAN.DISPLAY_CURSOR获取真实执行计划。

        Args:
            sql_id: SQL标识符

        Returns:
            执行计划对象
        """
        sql = """
        SELECT
            sql_id,
            plan_hash_value,
            DBMS_XPLAN.DISPLAY_CURSOR(sql_id, NULL, 'ALLSTATS LAST') as plan_text
        FROM v$sql
        WHERE sql_id = :sql_id
        AND ROWNUM = 1
        """

        try:
            results = self.client.execute(sql, {"sql_id": sql_id})
            if not results:
                return None

            row = results[0]
            # 处理 DbObject 类型，转换为字符串
            plan_text_raw = row[2]
            if plan_text_raw is not None:
                if hasattr(plan_text_raw, 'read'):
                    # CLOB 对象
                    plan_text = plan_text_raw.read()
                else:
                    plan_text = str(plan_text_raw)
            else:
                plan_text = ""

            plan = SQLPlan(
                sql_id=row[0],
                plan_hash_value=str(row[1]) if row[1] else "",
                plan_text=plan_text,
                operations=self._parse_plan_text(plan_text)
            )
            return plan

        except OracleQueryError as e:
            logger.error(f"获取执行计划失败 {sql_id}: {e}")
            return None

    def explain_sql(self, sql_text: str) -> Optional[SQLPlan]:
        """
        为SQL文本生成执行计划（EXPLAIN PLAN）

        用于用户上传的SQL，在测试库生成执行计划。

        Args:
            sql_text: SQL语句

        Returns:
            执行计划对象
        """
        try:
            # 生成唯一的计划标识
            plan_id = f"AUDIT_{hash(sql_text) & 0xFFFFFFFF:08X}"

            # 执行EXPLAIN PLAN
            explain_sql = f"EXPLAIN PLAN SET STATEMENT_ID = '{plan_id}' FOR {sql_text}"
            self.client.execute(explain_sql)

            # 获取执行计划
            plan_sql = f"""
            SELECT
                '{plan_id}' as sql_id,
                NULL as plan_hash_value,
                DBMS_XPLAN.DISPLAY(NULL, '{plan_id}', 'ALL') as plan_text
            FROM DUAL
            """

            results = self.client.execute(plan_sql)
            if not results:
                return None

            row = results[0]
            plan = SQLPlan(
                sql_id="USER_UPLOAD",
                plan_hash_value="",
                plan_text=row[2] if row[2] else "",
                operations=self._parse_plan_text(row[2]) if row[2] else []
            )
            return plan

        except OracleQueryError as e:
            logger.error(f"生成执行计划失败: {e}")
            return None

    def _build_sql_object(self, row: Tuple, source: str) -> SQLObject:
        """从查询结果构建SQL对象"""
        sql_id = row[0]
        sql_text = row[1]

        stats = SQLExecutionStats(
            sql_id=sql_id,
            executions=row[2] or 0,
            cpu_time_ms=row[3] or 0,
            elapsed_time_ms=row[4] or 0,
            buffer_gets=row[5] or 0,
            disk_reads=row[6] or 0,
            rows_processed=row[7] or 0,
            last_active_time=row[8]
        )

        return SQLObject(
            sql_id=sql_id,
            sql_text=sql_text,
            source=source,
            execution_stats=stats,
            execution_plan=None,  # 延迟加载
            metadata=None
        )

    def _parse_plan_text(self, plan_text: str) -> List[dict]:
        """
        解析执行计划文本为结构化数据

        这是一个简化版本，后续可以扩展更复杂的解析。
        """
        operations = []
        if not plan_text:
            return operations

        lines = plan_text.split('\n')
        for line in lines:
            line = line.strip()
            if not line or line.startswith('---') or line.startswith('Plan'):
                continue

            # 简单的启发式解析
            if 'TABLE ACCESS' in line or 'INDEX' in line:
                op_type = 'TABLE_ACCESS' if 'TABLE ACCESS' in line else 'INDEX'
                operations.append({
                    'type': op_type,
                    'detail': line,
                    'full_scan': 'FULL' in line
                })

        return operations
